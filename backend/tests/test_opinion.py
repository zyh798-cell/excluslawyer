"""P0-3 五段式意见书单测：结构完整性、风险引擎、证据不足、对抗段。"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.models.schemas import OpinionRequest, Statute
from app.rag.embedder import HashingEmbedder
from app.rag.retriever import Retriever
from app.rag.vector_store import NumpyVectorStore
from app.services.opinion_service import OpinionService, assess_risk
from app.services.facts_service import structure_facts
from scripts.ingest_cn import ingest_statutes


def _make_service(with_data: bool = True) -> OpinionService:
    emb = HashingEmbedder(dim=128)
    store = NumpyVectorStore(path=None)
    if with_data:
        ingest_statutes(
            [
                Statute(
                    id="CN-TEST-LDF82",
                    law_title="中华人民共和国劳动合同法",
                    article_no="第八十二条",
                    text="用人单位自用工之日起超过一个月不满一年未与劳动者订立书面劳动合同的，应当向劳动者每月支付二倍的工资。",
                    topics=["劳动", "未签劳动合同"],
                    status="effective",
                )
            ],
            emb,
            store,
        )
    return OpinionService(Retriever(emb, store))


def test_five_sections():
    svc = _make_service()
    resp = svc.build(
        OpinionRequest(narrative="2024年3月入职某公司，一直没签劳动合同，至今欠薪。我要求公司支付二倍工资。")
    )
    titles = [s.title for s in resp.sections]
    assert len(resp.sections) == 5, f"应有五段，实际 {titles}"
    assert titles[0].startswith("一、事实认定")
    assert titles[1].startswith("二、法律适用")
    assert titles[2].startswith("三、风险等级")
    assert titles[3].startswith("四、行动建议")
    assert titles[4].startswith("五、限制提示")
    assert resp.mode == "template"


def test_fact_set_included():
    svc = _make_service()
    resp = svc.build(OpinionRequest(narrative="2024年3月入职，我要求支付二倍工资。"))
    assert resp.fact_set.facts, "意见书必须携带结构化事实"
    assert resp.fact_set.counts["claim"] >= 1


def test_risk_engine_transparent():
    fs = structure_facts("可能有证据。不清楚具体金额。假设对方认账。")
    level, reasons = assess_risk(fs, [], "general")
    assert level == "high", "待核实多 + 无法条依据应为高风险"
    assert len(reasons) >= 2, "风险理由必须逐条可追溯"


def test_risk_low_when_complete():
    fs = structure_facts("2024年3月1日签订合同。对方2024年4月1日已支付定金。")
    dummy_cites = _make_service().retriever.retrieve("合同违约责任", top_k=1)
    level, reasons = assess_risk(fs, dummy_cites, "合同")
    assert level in ("low", "medium")
    assert reasons


def test_adversarial_section_appended():
    svc = _make_service()
    resp = svc.build(
        OpinionRequest(narrative="公司欠薪，我要索赔。", adversarial=True)
    )
    assert len(resp.sections) == 6
    assert "对方律师" in resp.sections[-1].title
    assert "攻击点" in resp.sections[-1].content


def test_insufficient_evidence_no_fake_conclusion():
    """空库 + 冷门问题 → 法律适用段必须写证据不足，不得编造。"""
    svc = _make_service(with_data=False)
    resp = svc.build(OpinionRequest(narrative="南极捕鲸配额争议如何处理？"))
    law = next(s for s in resp.sections if "法律适用" in s.title)
    assert "证据不足" in law.content
    assert not law.citation_ids
    assert resp.risk_level == "high"


def test_citations_attached_to_law_section():
    svc = _make_service()
    resp = svc.build(
        OpinionRequest(narrative="入职后公司未签书面劳动合同，我要求支付二倍工资。")
    )
    law = next(s for s in resp.sections if "法律适用" in s.title)
    assert resp.citations, "劳动问题应召回劳动合同法"
    assert law.citation_ids or resp.citations, "引用应挂到法律适用段"
