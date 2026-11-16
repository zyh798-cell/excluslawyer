# -*- coding: utf-8 -*-
"""模拟法庭庭审状态机组装：条件边 + 中断恢复。

阶段流：create_case → fix_facts → file_complaint → evidence_review
[→ human_confirm（时效风险人工确认）] → debate(×N 轮，每轮 interrupt)
→ closing(interrupt) → adjudicate。

- checkpointer=None：一次性执行（测试/无中断场景）
- checkpointer=MemorySaver()/SqliteSaver()：支持 interrupt()/Command(resume=...)
"""
from __future__ import annotations

from pathlib import Path

from langgraph.graph import END, START, StateGraph

from app.rag.retriever import Retriever

from .trial_nodes import TrialGraphDeps, make_trial_nodes
from .trial_state import TrialState

# 状态里携带的 pydantic 类型（checkpoint msgpack 允许清单）
_SERDE_TYPES = (
    "CalcItem", "Citation", "EvidenceReview", "Fact", "FactSet",
    "JurisdictionRule", "LimitationRisk", "NliResult", "OpinionSection",
    "StatuteRevision", "TimelineCard", "TrialClaim", "TrialComplaint",
    "TrialEvent", "TrialTurn", "TrialVerdict", "TrialVerdictItem",
)


def make_trial_checkpointer(db_path: Path | None = None):
    """庭审 checkpointer：SqliteSaver（跨重启持久化）优先，MemorySaver 兜底。

    serde 允许 app.models.schemas 下的 pydantic 类型，消除 msgpack 反序列化告警。
    """
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[("app.models.schemas", t) for t in _SERDE_TYPES]
    )
    if db_path is not None:
        try:
            import sqlite3

            from langgraph.checkpoint.sqlite import SqliteSaver

            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            return SqliteSaver(conn, serde=serde)
        except Exception:  # noqa: BLE001
            pass
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver(serde=serde)


def _after_create(state: TrialState) -> str:
    return "end_refused" if state.get("status") == "refused" else "fix_facts"


def _after_complaint(state: TrialState) -> str:
    return (
        "end_insufficient"
        if state.get("status") == "insufficient_evidence"
        else "evidence_review"
    )


def _after_evidence(state: TrialState) -> str:
    """时效风险高且开启人工确认 → 挂起；否则直接辩论。"""
    limitation = state.get("limitation")
    if (
        state.get("interrupt_on_limitation")
        and limitation is not None
        and limitation.risk_level == "expired"
    ):
        return "human_confirm"
    return "debate"


def _after_human(state: TrialState) -> str:
    return "end_insufficient" if state.get("status") == "insufficient_evidence" else "debate"


def _after_debate(state: TrialState, *, max_rounds: int) -> str:
    return "debate" if int(state.get("debate_round") or 0) < max_rounds else "closing"


def build_trial_graph(retriever: Retriever, *, checkpointer=None, max_rounds: int = 3):
    """编译庭审状态机。"""
    deps = TrialGraphDeps(retriever=retriever, max_rounds=max_rounds)
    nodes = make_trial_nodes(deps)
    g = StateGraph(TrialState)

    for name, fn in nodes.items():
        g.add_node(name, fn)

    g.add_edge(START, "create_case")
    g.add_conditional_edges(
        "create_case",
        _after_create,
        {"end_refused": "end_refused", "fix_facts": "fix_facts"},
    )
    g.add_edge("fix_facts", "file_complaint")
    g.add_conditional_edges(
        "file_complaint",
        _after_complaint,
        {"end_insufficient": "end_insufficient", "evidence_review": "evidence_review"},
    )
    g.add_conditional_edges(
        "evidence_review",
        _after_evidence,
        {"human_confirm": "human_confirm", "debate": "debate"},
    )
    g.add_conditional_edges(
        "human_confirm",
        _after_human,
        {"end_insufficient": "end_insufficient", "debate": "debate"},
    )
    g.add_conditional_edges(
        "debate",
        lambda s: _after_debate(s, max_rounds=max_rounds),
        {"debate": "debate", "closing": "closing"},
    )
    g.add_edge("closing", "adjudicate")
    g.add_edge("adjudicate", END)
    g.add_edge("end_refused", END)
    g.add_edge("end_insufficient", END)

    return g.compile(checkpointer=checkpointer)
