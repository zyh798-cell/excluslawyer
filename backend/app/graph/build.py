# -*- coding: utf-8 -*-
"""状态机组装：条件边 + 中断恢复（MemorySaver）。"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.rag.retriever import Retriever

from .nodes import GraphDeps, make_nodes
from .state import LegalConsultState


def _after_intake(state: LegalConsultState) -> str:
    return "end_refused" if state.get("status") == "refused" else "structure_facts"


def _after_retrieve(state: LegalConsultState) -> str:
    return "end_insufficient" if state.get("evidence_gate") == "insufficient" else "generate_draft"


def _route_after_nli(state: LegalConsultState) -> str:
    """降级且开人工确认 → 挂起；否则按需走对抗审查或直接出稿。"""
    nli = state.get("nli")
    if nli is not None and nli.status == "degraded" and state.get("interrupt_on_degraded"):
        return "human_confirm"
    return "adversarial_review" if state.get("adversarial") else "finalize"


def _after_human(state: LegalConsultState) -> str:
    if state.get("human_decision") == "reject":
        return "end_insufficient"
    return "adversarial_review" if state.get("adversarial") else "finalize"


def build_graph(retriever: Retriever, *, checkpointer=None):
    """编译咨询状态机。

    - checkpointer=None：一次性执行（无中断恢复）
    - checkpointer=MemorySaver()：可 interrupt()/resume（人工确认挂起）
    """
    nodes = make_nodes(GraphDeps(retriever=retriever))
    g = StateGraph(LegalConsultState)

    for name, fn in nodes.items():
        g.add_node(name, fn)

    # 终态汇合点（不走 finalize——refused/insufficient 无引用可算置信度）
    g.add_node("end_refused", lambda s: {"trace": ["END(refused)"]})
    g.add_node("end_insufficient", lambda s: {"trace": ["END(insufficient_evidence)"]})

    g.add_edge(START, "intake")
    g.add_conditional_edges(
        "intake",
        _after_intake,
        {"end_refused": "end_refused", "structure_facts": "structure_facts"},
    )
    g.add_edge("structure_facts", "retrieve")
    g.add_conditional_edges(
        "retrieve",
        _after_retrieve,
        {"end_insufficient": "end_insufficient", "generate_draft": "generate_draft"},
    )
    g.add_edge("generate_draft", "nli_verify")
    g.add_conditional_edges(
        "nli_verify",
        _route_after_nli,
        {
            "human_confirm": "human_confirm",
            "adversarial_review": "adversarial_review",
            "finalize": "finalize",
        },
    )
    g.add_conditional_edges(
        "human_confirm",
        _after_human,
        {
            "end_insufficient": "end_insufficient",
            "adversarial_review": "adversarial_review",
            "finalize": "finalize",
        },
    )
    g.add_edge("adversarial_review", "finalize")
    g.add_edge("finalize", END)
    g.add_edge("end_refused", END)
    g.add_edge("end_insufficient", END)

    return g.compile(checkpointer=checkpointer)
