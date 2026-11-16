# -*- coding: utf-8 -*-
"""模拟法庭庭审状态机的共享状态定义。

阶段（Phase）：create_case → fix_facts → file_complaint → evidence_review
→ debate(×3 轮) → closing → adjudicate。
"""
from __future__ import annotations

import operator
from typing import Annotated, Literal, Optional, TypedDict

from app.graph.state import _keep_latest
from app.models.schemas import (
    EvidenceReview,
    FactSet,
    LimitationRisk,
    TrialComplaint,
    TrialEvent,
    TrialTurn,
    TrialVerdict,
)


class TrialState(TypedDict, total=False):
    # ---- 入参 ----
    session_id: str
    case_description: str
    user_role: Literal["plaintiff", "defendant"]
    jurisdiction: str
    language: str
    top_k: int
    claims_input: list[dict]      # TrialClaimInput 序列化
    evidences_input: list[dict]   # TrialEvidenceInput 序列化
    interrupt_on_limitation: bool  # 时效风险高时是否挂起人工确认

    # ---- 中断恢复入参（也可直接放 state） ----
    statement: str   # 辩论发言
    closing: str     # 总结陈词
    decision: str    # 人工裁决 approve / reject

    # ---- 过程 ----
    trace: Annotated[list[str], operator.add]          # 全链路可观测
    events: Annotated[list[TrialEvent], operator.add]  # 滚动庭审记录
    facts: Annotated[Optional[FactSet], _keep_latest]
    complaint: Annotated[Optional[TrialComplaint], _keep_latest]
    evidence_reviews: Annotated[Optional[list[EvidenceReview]], _keep_latest]
    limitation: Annotated[Optional[LimitationRisk], _keep_latest]
    debate_turns: Annotated[list[TrialTurn], operator.add]  # 每轮追加
    debate_round: Annotated[Optional[int], _keep_latest]
    closing_text: Annotated[Optional[str], _keep_latest]
    verdict: Annotated[Optional[TrialVerdict], _keep_latest]
    phase: Annotated[Optional[str], _keep_latest]
    pending: Annotated[Optional[str], _keep_latest]  # 下一步待输入提示

    # ---- 终态 ----
    status: Annotated[
        Optional[
            Literal["refused", "insufficient_evidence", "awaiting_input", "done"]
        ],
        _keep_latest,
    ]
