# -*- coding: utf-8 -*-
"""裁判小结 NLI 一致性回归（遗留项 1）。

覆盖两个场景：
1. 小结复述所引法条关键要件/关键词后，结论-依据一致性校验通过（不再降级）；
2. 校验不通过（degraded）时必须标注"证据不足"，不得静默放行。
"""
from __future__ import annotations

from app.config import settings
from app.models.schemas import (
    TRIAL_DISCLAIMER,
    Citation,
    FactSet,
    LimitationRisk,
    NliResult,
    TrialClaim,
    TrialComplaint,
)
from app.services.trial_flow_service import build_verdict

_STATUTE_TEXT = (
    "当事人一方不履行合同义务或者履行合同义务不符合约定的，"
    "应当承担继续履行、采取补救措施或者赔偿损失等违约责任。"
)


def _citation() -> Citation:
    return Citation(
        statute_id="CN-MINFA-577",
        law_title="中华人民共和国民法典",
        article_no="第五百七十七条",
        text=_STATUTE_TEXT,
        score=0.9,
    )


def _complaint(cites: list[Citation]) -> TrialComplaint:
    return TrialComplaint(
        party="原告",
        claims=[
            TrialClaim(
                text="要求买方支付拖欠货款并承担违约责任",
                relief="支付货款 10 万元",
                citations=cites,
                support="supported",
                holes=[],
                risks=[],
            )
        ],
        citations=cites,
        grounded=True,
    )


def _build(monkeypatch, complaint: TrialComplaint):
    """隔离外部服务（KG/Compare），单测只验证小结模板与 NLI 分支。"""

    class _Disabled:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("disabled in unit test")

    monkeypatch.setattr("app.services.kg_service.KgService", _Disabled)
    monkeypatch.setattr("app.services.compare_service.CompareService", _Disabled)
    return build_verdict(
        complaint=complaint,
        reviews=[],
        limitation=LimitationRisk(),
        debate_turns=[],
        facts=FactSet(facts=[], timeline=[]),
        case_description="买方拖欠货款合同纠纷",
        jurisdiction="CN",
        retriever=None,
    )


def test_verdict_summary_restates_statute_keywords_and_passes_nli(monkeypatch):
    """小结复述法条关键词后通过一致性校验（遗留项 1 主场景）。"""
    verdict = _build(monkeypatch, _complaint([_citation()]))

    # 免责声明仍强制前置
    assert verdict.overall.startswith(TRIAL_DISCLAIMER)
    # 小结包含要件复述段，且复述了所引法条的关键要件与关键词
    assert "裁判要件复述" in verdict.overall
    for kw in ("第五百七十七条", "不履行合同义务", "违约责任"):
        assert kw in verdict.overall, f"小结未复述法条关键词：{kw}"

    # 复述后一致性校验通过：不再降级，且词面重叠达阈值
    assert verdict.nli is not None, "有引用时必须执行 NLI 校验"
    assert verdict.nli.status != "degraded", f"复述关键词后不应降级：{verdict.nli}"
    assert verdict.nli.score >= settings.nli_threshold
    # 未降级不得出现降级标注
    assert "引用支撑校验降级" not in verdict.overall


def test_verdict_nli_degraded_marks_insufficient_not_silent(monkeypatch):
    """校验不通过仍须标注证据不足，不得静默放行（保留 degraded 降级分支）。"""

    def _fake_degraded(answer: str, citations: list) -> NliResult:
        return NliResult(status="degraded", score=0.21, reason="词面重叠仅 21%")

    monkeypatch.setattr("app.services.ask_service.nli_check", _fake_degraded)
    verdict = _build(monkeypatch, _complaint([_citation()]))

    assert verdict.nli is not None and verdict.nli.status == "degraded"
    # 不得静默放行：overall 必须带证据不足标注，且免责声明仍前置
    assert "证据不足" in verdict.overall
    assert "引用支撑校验降级" in verdict.overall
    assert verdict.overall.startswith(TRIAL_DISCLAIMER), "免责声明仍强制前置"
    # 风险提示同步标注
    assert any("NLI 校验降级" in note for note in verdict.risk_notes)
    # 降级不阻断输出：小结主体仍在
    assert "模拟裁判小结" in verdict.overall
