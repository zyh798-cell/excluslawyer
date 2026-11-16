# -*- coding: utf-8 -*-
"""模拟法庭庭审状态机节点工厂。

每个节点输出 trace / events 追加段，状态合并规则见 trial_state.py。
四大铁律：
1. 主张必挂现行法条（检索不足→证据不足，禁止编造）；
2. 双视角对抗（对方律师视角自动打漏洞）；
3. 时效联动（时效计算器 + 法条关联）；
4. 多法域（裁判支持跨法域对照）。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.llm import LLMConfig, generate
from app.core.security import scan_untrusted, wrap_untrusted
from app.models.schemas import (
    FactSet,
    LimitationRisk,
    TrialClaimInput,
    TrialComplaint,
    TrialEvent,
    TrialEvidenceInput,
    TrialTurn,
)
from app.rag.retriever import Retriever
from app.services.facts_service import structure_facts
from app.services.opinion_service import _detect_topic
from app.services.trial_flow_service import (
    _fact_holes,
    build_complaint,
    build_verdict,
    review_evidences,
)

from .trial_state import TrialState

MAX_ROUNDS = 3


@dataclass
class TrialGraphDeps:
    retriever: Retriever
    max_rounds: int = MAX_ROUNDS


def make_trial_nodes(deps: TrialGraphDeps) -> dict:
    def create_case(state: TrialState) -> dict:
        """案件创建：注入检测（任何输入命中即拒答短路）。"""
        texts = [state.get("case_description", "")]
        texts += [c.get("text", "") for c in state.get("claims_input") or []]
        texts += [
            f"{e.get('title', '')} {e.get('description', '')}"
            for e in state.get("evidences_input") or []
        ]
        for t in texts:
            scan = scan_untrusted(t)
            if not scan.safe:
                return {
                    "trace": ["create_case(refused)"],
                    "status": "refused",
                    "phase": "create_case",
                    "events": [
                        TrialEvent(
                            phase="create_case",
                            kind="info",
                            role="system",
                            title="已拒绝立案",
                            content=f"⛔ {scan.detail}",
                        )
                    ],
                }
        n_claims = len(state.get("claims_input") or [])
        n_evi = len(state.get("evidences_input") or [])
        return {
            "trace": [f"create_case(ok, claims={n_claims}, evidences={n_evi})"],
            "phase": "create_case",
            "events": [
                TrialEvent(
                    phase="create_case",
                    kind="info",
                    role="clerk",
                    title="案件受理",
                    content=f"案件已登记，当事人主张 {n_claims} 项、在案证据 {n_evi} 项。",
                )
            ],
        }

    def fix_facts(state: TrialState) -> dict:
        """事实固定：结构化事实 + 法官归纳争议焦点。"""
        facts = structure_facts(state["case_description"])
        topic = _detect_topic(state["case_description"])
        focus: list[str] = []
        if facts.counts.get("to_verify", 0):
            focus.append("待核实事实的证明责任分配")
        if facts.counts.get("claim", 0):
            focus.append("主张事实与诉求的依据")
        if topic == "劳动":
            focus.append("劳动关系成立与否及工资标准的认定")
        elif topic == "合同":
            focus.append("违约行为、损失范围及可预见性的认定")
        elif topic == "侵权":
            focus.append("过错、因果关系及损害后果的认定")
        focus.append("诉讼/仲裁时效")
        focus_txt = "；".join(focus)
        return {
            "trace": [
                f"fix_facts({len(facts.facts)} facts, "
                f"confirmed={facts.counts.get('confirmed', 0)}, "
                f"to_verify={facts.counts.get('to_verify', 0)})"
            ],
            "phase": "fix_facts",
            "facts": facts,
            "events": [
                TrialEvent(
                    phase="fix_facts",
                    kind="info",
                    role="clerk",
                    title="事实固定",
                    content=(
                        f"已固定事实 {len(facts.facts)} 项"
                        f"（已确认 {facts.counts.get('confirmed', 0)} / "
                        f"待核实 {facts.counts.get('to_verify', 0)} / "
                        f"假设 {facts.counts.get('assumption', 0)} / "
                        f"主张 {facts.counts.get('claim', 0)}）。"
                    ),
                ),
                TrialEvent(
                    phase="fix_facts",
                    kind="info",
                    role="judge",
                    title="争议焦点归纳",
                    content=f"本庭归纳争议焦点：{focus_txt}。请双方围绕焦点举证、质证、辩论。",
                ),
            ],
        }

    def file_complaint(state: TrialState) -> dict:
        """提交诉状：逐项主张检索挂条（铁律 1）+ 对方律师视角（铁律 2）。"""
        claims = [TrialClaimInput.model_validate(c) for c in state.get("claims_input") or []]
        facts = state.get("facts")
        if facts is None:
            facts = structure_facts(state["case_description"])
        complaint = build_complaint(
            claims=claims,
            facts=facts,
            case_description=state["case_description"],
            jurisdiction=state.get("jurisdiction", "CN"),
            retriever=deps.retriever,
            top_k=state.get("top_k", 5),
            user_role=state.get("user_role", "plaintiff"),
        )
        n_supported = sum(1 for c in complaint.claims if c.support != "insufficient")
        n_insuf = sum(1 for c in complaint.claims if c.support == "insufficient")

        if not complaint.claims or not complaint.grounded:
            # 铁律 1：全程无任何法条依据 → 证据不足短路，不出具裁判
            return {
                "trace": [
                    f"file_complaint({len(complaint.claims)} claims, 0 grounded)"
                ],
                "phase": "file_complaint",
                "complaint": complaint,
                "status": "insufficient_evidence",
                "events": [
                    TrialEvent(
                        phase="file_complaint",
                        kind="info",
                        role="clerk",
                        title="诉状审查",
                        content=(
                            "各项主张均未检索到可支撑的现行法条依据，"
                            "按证据不足处理，拒绝在无依据的情况下出具裁判。"
                        ),
                    )
                ],
            }

        return {
            "trace": [
                f"file_complaint({len(complaint.claims)} claims, "
                f"{n_supported} grounded, {n_insuf} insufficient)"
            ],
            "phase": "file_complaint",
            "complaint": complaint,
            "events": [
                TrialEvent(
                    phase="file_complaint",
                    kind="info",
                    role="clerk",
                    title="诉状提交",
                    content=(
                        f"共 {len(complaint.claims)} 项主张："
                        f"有法条依据 {n_supported} 项、证据不足 {n_insuf} 项。"
                    ),
                    citation_ids=[c.statute_id for c in complaint.citations[:8]],
                ),
                TrialEvent(
                    phase="file_complaint",
                    kind="info",
                    role="opponent",
                    title="对方律师视角",
                    content=complaint.opposition_summary,
                ),
            ],
        }

    def evidence_review(state: TrialState) -> dict:
        """举证质证：证据-要件匹配 + 证明力 + 瑕疵 + 时效联动（铁律 3）。"""
        evidences = [
            TrialEvidenceInput.model_validate(e) for e in state.get("evidences_input") or []
        ]
        facts = state.get("facts")
        if facts is None:
            facts = structure_facts(state["case_description"])
        complaint = state.get("complaint")
        if complaint is None:
            complaint = build_complaint(
                claims=[],
                facts=facts,
                case_description=state["case_description"],
                jurisdiction=state.get("jurisdiction", "CN"),
                retriever=deps.retriever,
                top_k=state.get("top_k", 5),
                user_role=state.get("user_role", "plaintiff"),
            )
        reviews, limitation = review_evidences(
            evidences=evidences,
            facts=facts,
            complaint=complaint,
            case_description=state["case_description"],
            jurisdiction=state.get("jurisdiction", "CN"),
            retriever=deps.retriever,
        )
        events = [
            TrialEvent(
                phase="evidence_review",
                kind="evidence",
                role="clerk",
                title="举证质证",
                content=(
                    f"在案证据 {len(reviews)} 项完成质证："
                    + "；".join(
                        f"{r.title}（证明力 {'强' if r.probative_strength == 'strong' else '中' if r.probative_strength == 'medium' else '弱'}"
                        + (f"，瑕疵 {len(r.defects)} 处" if r.defects else "")
                        + "）"
                        for r in reviews
                    )
                ),
            ),
            TrialEvent(
                phase="evidence_review",
                kind="limitation",
                role="clerk",
                title="时效联动",
                content=limitation.summary or "时效检查未执行",
                citation_ids=[c.statute_id for c in limitation.citations],
            ),
        ]
        return {
            "trace": [
                f"evidence_review({len(reviews)} evidences, "
                f"limitation={limitation.risk_level})"
            ],
            "phase": "evidence_review",
            "evidence_reviews": reviews,
            "limitation": limitation,
            "events": events,
        }

    def human_confirm(state: TrialState):
        """时效风险挂起人工确认（interrupt）：approve=继续审理 / reject=终止推演。"""
        from langgraph.types import interrupt

        limitation = state.get("limitation")
        decision = interrupt(
            {
                "phase": "human_confirm",
                "prompt": (
                    f"时效联动提示：{limitation.summary if limitation else ''}。"
                    "是否继续审理？approve=继续 / reject=终止推演"
                ),
            }
        )
        if str(decision).lower() in ("reject", "rejected", "no"):
            return {
                "trace": ["human_confirm(reject)"],
                "phase": "human_confirm",
                "status": "insufficient_evidence",
                "events": [
                    TrialEvent(
                        phase="human_confirm",
                        kind="info",
                        role="system",
                        title="人工确认",
                        content="时效风险过高，经人工确认终止本次推演。",
                    )
                ],
            }
        return {
            "trace": ["human_confirm(approve)"],
            "phase": "human_confirm",
            "events": [
                TrialEvent(
                    phase="human_confirm",
                    kind="info",
                    role="system",
                    title="人工确认",
                    content="已确认时效风险，继续审理。",
                )
            ],
        }

    def debate(state: TrialState) -> dict:
        """法庭辩论：每次执行一轮（interrupt 等待发言 → 反驳 → 评析）。"""
        from langgraph.types import interrupt

        round_no = int(state.get("debate_round") or 0) + 1
        statement = interrupt(
            {
                "phase": "debate",
                "round": round_no,
                "prompt": f"法庭辩论第 {round_no}/{deps.max_rounds} 轮，请发表你的意见……",
            }
        )
        statement = str(statement or "").strip()
        user_role = "原告" if state.get("user_role", "plaintiff") == "plaintiff" else "被告"
        turns: list[TrialTurn] = [
            TrialTurn(role="user", round=round_no, content=statement)
        ]

        complaint = state.get("complaint")
        reviews = state.get("evidence_reviews") or []
        limitation = state.get("limitation")
        topic = _detect_topic(state["case_description"])

        # 对方律师反驳：LLM 可用走 LLM，否则规则版（法条均来自检索结果）
        cfg = LLMConfig.from_settings()
        opponent_text = None
        if cfg.available:
            cites = "\n".join(
                f"[{c.statute_id}] {c.law_title}{c.article_no}：{c.text[:80]}"
                for c in (complaint.citations[:4] if complaint else [])
            )
            opponent_text = generate(
                _OPPONENT_SYS,
                (
                    f"{wrap_untrusted(state['case_description'], '案情')}\n\n"
                    f"{wrap_untrusted(cites, '相关法条（只能引用这些）')}\n\n"
                    f"{wrap_untrusted(statement, f'{user_role}第{round_no}轮发言')}"
                ),
                cfg,
            )
        turns.append(
            TrialTurn(
                role="opponent",
                round=round_no,
                content=opponent_text
                or _opponent_rebuttal(complaint, reviews, limitation, statement, round_no),
            )
        )

        events = [
            TrialEvent(
                phase="debate",
                kind="turn",
                role="user",
                title=f"{user_role}（第 {round_no} 轮）",
                content=statement,
            ),
            TrialEvent(
                phase="debate",
                kind="turn",
                role="opponent",
                title=f"对方律师（第 {round_no} 轮）",
                content=turns[-1].content,
            ),
        ]

        if round_no >= deps.max_rounds:
            return {
                "trace": [f"debate(round={round_no}, final)"],
                "phase": "debate",
                "debate_round": round_no,
                "debate_turns": turns,
                "events": events,
            }

        judge_text = _judge_comment(state.get("facts"), round_no)
        turns.append(TrialTurn(role="judge", round=round_no, content=judge_text))
        events.append(
            TrialEvent(
                phase="debate",
                kind="turn",
                role="judge",
                title=f"法官（第 {round_no} 轮评析）",
                content=judge_text,
            )
        )
        return {
            "trace": [f"debate(round={round_no})"],
            "phase": "debate",
            "debate_round": round_no,
            "debate_turns": turns,
            "events": events,
        }

    def closing(state: TrialState) -> dict:
        """总结陈词：当事人陈词 + 法官小结双方立场（挂引用）。"""
        from langgraph.types import interrupt

        text = interrupt(
            {
                "phase": "closing",
                "prompt": "进入总结陈词阶段，请发表你的总结陈词……",
            }
        )
        text = str(text or "").strip()
        complaint = state.get("complaint")
        citation_ids = [c.statute_id for c in (complaint.citations[:8] if complaint else [])]
        summary = _closing_summary(complaint, state.get("limitation"))
        return {
            "trace": ["closing(ok)"],
            "phase": "closing",
            "closing_text": text,
            "events": [
                TrialEvent(phase="closing", kind="turn", role="user", title="总结陈词", content=text),
                TrialEvent(
                    phase="closing",
                    kind="info",
                    role="judge",
                    title="双方立场小结",
                    content=summary,
                    citation_ids=citation_ids,
                ),
            ],
        }

    def adjudicate(state: TrialState) -> dict:
        """模拟裁判：强制前置免责 + 逐条理由 + 法条溯源 + 判例 + 跨法域（铁律 4）。"""
        facts = state.get("facts")
        if facts is None:
            facts = structure_facts(state["case_description"])
        complaint = state.get("complaint")
        if complaint is None:
            complaint = TrialComplaint(claims=[], grounded=False)
        verdict = build_verdict(
            complaint=complaint,
            reviews=state.get("evidence_reviews") or [],
            limitation=state.get("limitation") or LimitationRisk(),
            debate_turns=state.get("debate_turns") or [],
            facts=facts,
            case_description=state["case_description"],
            jurisdiction=state.get("jurisdiction", "CN"),
            retriever=deps.retriever,
        )
        decisions = {d: sum(1 for i in verdict.items if i.decision == d) for d in ("支持", "部分支持", "驳回")}
        return {
            "trace": [
                f"adjudicate(items={len(verdict.items)}, "
                f"support={decisions['支持']}, partial={decisions['部分支持']}, "
                f"reject={decisions['驳回']})"
            ],
            "phase": "adjudicate",
            "verdict": verdict,
            "status": "done",
            "events": [
                TrialEvent(
                    phase="adjudicate",
                    kind="verdict",
                    role="judge",
                    title="模拟裁判",
                    content=verdict.overall,
                    citation_ids=[c.statute_id for c in verdict.citations[:8]],
                )
            ],
        }

    def end_refused(state: TrialState) -> dict:
        return {
            "trace": ["END(refused)"],
            "phase": "create_case",
            "status": "refused",
        }

    def end_insufficient(state: TrialState) -> dict:
        return {
            "trace": ["END(insufficient_evidence)"],
            "status": "insufficient_evidence",
            "events": [
                TrialEvent(
                    phase=state.get("phase") or "file_complaint",
                    kind="info",
                    role="system",
                    title="审理终结",
                    content="【证据不足】现有法条库未检索到可支撑的依据，拒绝在无依据的情况下生成结论。",
                )
            ],
        }

    return {
        "create_case": create_case,
        "fix_facts": fix_facts,
        "file_complaint": file_complaint,
        "evidence_review": evidence_review,
        "human_confirm": human_confirm,
        "debate": debate,
        "closing": closing,
        "adjudicate": adjudicate,
        "end_refused": end_refused,
        "end_insufficient": end_insufficient,
    }


# ---- 规则版辩论话术（法条引用只来自检索结果，杜绝编造） ----


def _opponent_rebuttal(complaint, reviews, limitation, statement: str, round_no: int) -> str:
    lines = [f"对方律师（第 {round_no} 轮反驳）："]
    points: list[str] = []
    if complaint is not None:
        for c in complaint.claims:
            points.extend(c.holes[:1])
            points.extend(c.risks[:1])
    points.extend(d for r in reviews for d in r.defects[:1])
    seen: set[str] = set()
    uniq = []
    for p in points:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    for i, p in enumerate(uniq[:4], 1):
        lines.append(f"{i}. {p}")
    if limitation and limitation.risk_level in ("expired", "warning"):
        cites = "、".join(f"[{c.statute_id}]" for c in limitation.citations[:2])
        lines.append(f"【时效抗辩】{limitation.summary} {cites}".rstrip())
    if len(lines) == 1:
        lines.append("1. 对方所述事实缺乏客观证据佐证，请求法庭不予采信。")
    lines.append(f"（针对你本轮发言「{statement[:24]}…」，我方坚持上述抗辩；引用仅限已挂载法条。）")
    return "\n".join(lines)


def _judge_comment(facts: FactSet | None, round_no: int) -> str:
    f = facts.counts if facts else {}
    return (
        f"法官（第 {round_no} 轮评析）：本案已确认事实 {f.get('confirmed', 0)} 项、"
        f"待核实 {f.get('to_verify', 0)} 项、主张 {f.get('claim', 0)} 项。"
        "主张积极事实的一方承担举证责任，未能举证的承担不利后果。下一轮请就对方观点逐项回应。"
    )


def _closing_summary(complaint, limitation) -> str:
    n = len(complaint.claims) if complaint else 0
    grounded = sum(1 for c in (complaint.claims if complaint else []) if c.support != "insufficient")
    text = (
        f"法官（立场小结）：主张方共提出 {n} 项主张，其中 {grounded} 项挂载了现行法条依据；"
        "对方就证据、时效与因果关系提出抗辩。"
    )
    if limitation and limitation.risk_level in ("expired", "warning"):
        text += f"特别提示：{limitation.summary}"
    text += "本庭将依据在案证据与所引法条作模拟裁判，结论不具法律效力。"
    return text


_OPPONENT_SYS = """你是模拟法庭中的对方律师。任务：针对对方当事人的发言做有力、专业的反驳。
要求：1) 只围绕证据、时效、因果关系、可预见性、过错相抵、程序等法定抗辩点展开；
2) 引用法条只能使用给定清单中的编号，格式 [CIT-id]，绝不编造法条或案情；
3) 语言犀利但专业，中文输出。"""
