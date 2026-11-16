# -*- coding: utf-8 -*-
"""状态机节点工厂：make_nodes(deps) 返回纯函数 state -> updates。

每个节点输出 trace 追加段，状态合并规则见 state.py。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.llm import LLMConfig, extractive_answer, generate
from app.core.prompts import SYSTEM_PROMPT, build_user_prompt
from app.core.security import scan_untrusted
from app.models.schemas import NliResult
from app.rag.retriever import Retriever
from app.services.ask_service import nli_check
from app.services.facts_service import structure_facts
from app.services.opinion_service import _adversarial_view, _detect_topic

from .state import LegalConsultState


@dataclass
class GraphDeps:
    retriever: Retriever


def make_nodes(deps: GraphDeps) -> dict:
    def intake(state: LegalConsultState) -> dict:
        """注入/拒答检测。命中即短路到 refused 终态。"""
        scan = scan_untrusted(state["question"])
        if not scan.safe:
            return {
                "trace": ["intake(refused)"],
                "status": "refused",
                "answer": f"⛔ 已拒绝作答：{scan.detail}",
                "citations": [],
                "confidence": 0.0,
            }
        return {"trace": ["intake(ok)"]}

    def structure_facts_node(state: LegalConsultState) -> dict:
        facts = structure_facts(state["question"])
        n_claims = sum(1 for f in facts.facts if f.fact_type == "claim")
        return {
            "trace": [f"structure_facts({len(facts.facts)} facts, {n_claims} claims)"],
            "facts": facts,
        }

    def retrieve(state: LegalConsultState) -> dict:
        """检索 + 质量闸门。空证据 → insufficient_evidence（铁律 1：不幻觉）。"""
        citations = deps.retriever.retrieve(
            state["question"],
            top_k=state.get("top_k", 5),
            jurisdiction=state.get("jurisdiction", "CN"),
        )
        if not citations:
            return {
                "trace": ["retrieve(0 hits)"],
                "citations": [],
                "evidence_gate": "insufficient",
                "status": "insufficient_evidence",
                "answer": (
                    "【证据不足】现有法条库未检索到可支撑本问题的现行法条，"
                    "拒绝在无依据的情况下生成结论。可尝试换用更贴近法条术语的表述，"
                    "或确认该问题是否属于本法域现行法调整范围。"
                ),
                "confidence": 0.0,
            }
        return {
            "trace": [f"retrieve({len(citations)} hits, top={citations[0].score:.3f})"],
            "citations": citations,
            "evidence_gate": "pass",
        }

    def generate_draft(state: LegalConsultState) -> dict:
        """LLM 生成（服务端配置时）→ 否则演示模式摘录式回答。"""
        from app.config import settings

        citations = state.get("citations") or []
        cfg = LLMConfig(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )
        user_prompt = build_user_prompt(
            state["question"], citations, adversarial=state.get("adversarial", False)
        )
        answer = generate(SYSTEM_PROMPT, user_prompt, cfg)
        mode = "server"
        if answer is None:
            answer = extractive_answer(state["question"], citations)
            mode = "extractive"
        return {
            "trace": [f"generate_draft({mode})"],
            "draft_answer": answer,
            "answer_mode": mode,
        }

    def nli_verify(state: LegalConsultState) -> dict:
        answer = state.get("draft_answer") or ""
        citations = state.get("citations") or []
        nli: NliResult = nli_check(answer, citations)
        if nli.status == "degraded":
            answer = (
                "⚠️【引用支撑不足·已降级】以下结论与所引法条的蕴含关系校验未通过，"
                "请谨慎采信：\n\n" + answer
            )
        return {"trace": [f"nli_verify({nli.status}, {nli.score})"], "nli": nli, "answer": answer}

    def human_confirm(state: LegalConsultState):
        """人工确认挂起点（interrupt）：NLI 降级且开启人工确认时暂停图执行。

        恢复时传入 human_decision: 'approve' | 'reject'。
        """
        from langgraph.types import interrupt

        nli = state.get("nli")
        decision = interrupt(
            {
                "question": state["question"],
                "nli": nli.model_dump() if nli else None,
                "draft_answer": state.get("draft_answer"),
                "prompt": "NLI 校验降级，请人工裁决：approve=带降级警示出稿 / reject=退回不出结论",
            }
        )
        if str(decision).lower() in ("reject", "rejected", "no"):
            return {
                "trace": ["human_confirm(reject)"],
                "human_decision": "reject",
                "status": "insufficient_evidence",
                "answer": (
                    "【证据不足·人工驳回】结论与所引法条的一致性校验未通过且经人工驳回，不出具结论。"
                ),
                "confidence": 0.0,
            }
        return {"trace": ["human_confirm(approve)"], "human_decision": "approve"}

    def adversarial_review(state: LegalConsultState) -> dict:
        """铁律 2：对方律师视角找漏洞（adversarial=True 时启用）。"""
        facts = state.get("facts")
        if facts is None:
            return {"trace": ["adversarial_review(skip: no facts)"]}
        notes = _adversarial_view(facts, _detect_topic(state["question"]))
        return {"trace": ["adversarial_review(ok)"], "adversarial_notes": notes}

    def finalize(state: LegalConsultState) -> dict:
        """汇总终态：置信度 = 检索得分×0.7 + NLI 得分×0.3（与 /api/ask 口径一致）。"""
        citations = state.get("citations") or []
        nli = state.get("nli")
        top_score = citations[0].score if citations else 0.0
        nli_score = nli.score if nli else 0.0
        confidence = round(min(1.0, top_score * 0.7 + nli_score * 0.3), 3)

        answer = state.get("answer") or state.get("draft_answer") or ""
        if state.get("adversarial_notes"):
            answer += "\n\n———【对方律师视角】———\n" + state["adversarial_notes"]

        status = state.get("status") or "done"
        if status == "done" and nli and nli.status == "degraded":
            status = "degraded"
        return {
            "trace": [f"finalize({status}, conf={confidence})"],
            "confidence": confidence,
            "answer": answer,
            "status": status,
        }

    return {
        "intake": intake,
        "structure_facts": structure_facts_node,
        "retrieve": retrieve,
        "generate_draft": generate_draft,
        "nli_verify": nli_verify,
        "human_confirm": human_confirm,
        "adversarial_review": adversarial_review,
        "finalize": finalize,
    }
