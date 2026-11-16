# -*- coding: utf-8 -*-
"""咨询状态机的共享状态定义。"""
from __future__ import annotations

import operator
from typing import Annotated, Literal, Optional, TypedDict

from app.models.schemas import Citation, FactSet, NliResult, OpinionResponse


def _keep_latest(a, b):
    """覆盖式合并（后写入者生效）；None 表示不更新。"""
    return b if b is not None else a


class LegalConsultState(TypedDict, total=False):
    # ---- 入参 ----
    question: str
    jurisdiction: str
    language: str
    top_k: int
    adversarial: bool
    # 人工确认开关：NLI 降级时是否挂起等待人工（interrupt）
    interrupt_on_degraded: bool

    # ---- 过程 ----
    # 节点访问轨迹（追加式）—— 状态机透明性
    trace: Annotated[list[str], operator.add]
    facts: Annotated[Optional[FactSet], _keep_latest]
    citations: Annotated[Optional[list[Citation]], _keep_latest]
    evidence_gate: Annotated[Optional[Literal["pass", "insufficient"]], _keep_latest]
    draft_answer: Annotated[Optional[str], _keep_latest]
    answer_mode: Annotated[Optional[str], _keep_latest]  # server / extractive
    nli: Annotated[Optional[NliResult], _keep_latest]
    adversarial_notes: Annotated[Optional[str], _keep_latest]
    opinion: Annotated[Optional[OpinionResponse], _keep_latest]
    # human_confirm 的人工裁决：approve / reject
    human_decision: Annotated[Optional[str], _keep_latest]

    # ---- 终态 ----
    status: Annotated[
        Optional[Literal["refused", "insufficient_evidence", "degraded", "done"]],
        _keep_latest,
    ]
    answer: Annotated[Optional[str], _keep_latest]
    confidence: Annotated[Optional[float], _keep_latest]
