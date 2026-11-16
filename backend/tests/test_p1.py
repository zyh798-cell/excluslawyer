"""P1 各模块单测：合同风险扫描 / 类案参考 / 时效追踪 / 多模态路由。"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.models.schemas import CaseSearchRequest, ContractScanRequest
from app.rag.embedder import HashingEmbedder
from app.rag.retriever import Retriever
from app.rag.vector_store import NumpyVectorStore
from app.services.cases_service import CaseSearchService
from app.services.contract_service import (
    ContractScanService,
    annotate_clause,
    split_clauses,
)
from app.services.multimodal_service import MultimodalService, route_content
from app.services.statute_service import build_statute_timeline
from scripts.ingest_cn import ingest_seed


def _make_retriever() -> Retriever:
    emb = HashingEmbedder(dim=128)
    store = NumpyVectorStore(path=None)
    ingest_seed(emb, store)
    return Retriever(emb, store)


# ---------- P1-5 合同风险扫描 ----------


SAMPLE_CONTRACT = """教育培训服务协议
第一条 服务内容
甲方为乙方提供职业培训课程，课程费用人民币30000元。
第二条 退费规则
乙方缴费后概不退款，一切损失均由乙方承担，甲方享有最终解释权。
第三条 违约责任
乙方逾期付款的，每日按未付款项的千分之五支付违约金。
第四条 保密义务
乙方对课程内容承担永久保密义务。
第五条 服务期限
课程自2025年1月1日起，甲方尽快安排授课，验收合格即完成服务。
"""


def test_clause_split():
    clauses = split_clauses(SAMPLE_CONTRACT)
    assert len(clauses) >= 5, f"应切出 5 条以上条款，实际 {len(clauses)}"
    assert clauses[0][0].startswith("第一条")


def test_red_flags_detected():
    ann = annotate_clause(1, "第二条", "乙方缴费后概不退款，一切损失均由乙方承担，甲方享有最终解释权。")
    assert ann.severity == "risky"
    types = " ".join(h.rule.risk_type for h in ann.hits)
    assert "单方" in types or "无限" in types or "排除" in types


def test_penalty_yellow():
    ann = annotate_clause(2, "第三条", "乙方逾期付款的，每日按未付款项的千分之五支付违约金。")
    assert ann.severity == "warn"
    assert any("违约金" in h.rule.risk_type for h in ann.hits)


def test_clean_clause_green():
    ann = annotate_clause(3, "第三条", "甲方应于每月5日前向乙方提供上月服务报告。")
    assert ann.severity == "ok"
    assert ann.hits == []


def test_full_scan_summary_and_citations():
    svc = ContractScanService(_make_retriever())
    resp = svc.scan(SAMPLE_CONTRACT)
    assert resp.summary["risky"] >= 1, "退费条款应命中红色风险"
    assert resp.summary["warn"] >= 2
    assert resp.summary["ok"] >= 1
    risky = [c for c in resp.clauses if c.risk_level == "risky"]
    assert all(c.explanation and c.suggestion for c in risky), "红条款必须给理由和修改建议"
    assert resp.citations, "风险应挂载对应法条"


# ---------- P1-6 类案参考 ----------


def test_case_search_labor():
    svc = CaseSearchService()
    resp = svc.search(CaseSearchRequest(query="公司没签劳动合同，要求二倍工资赔偿"))
    assert resp.cases, "劳动争议查询应命中类案"
    assert resp.result_distribution
    assert 0 <= resp.support_rate <= 1


def test_case_distribution_sums():
    svc = CaseSearchService()
    resp = svc.search(CaseSearchRequest(query="违约金过高请求调减", top_k=5))
    assert sum(resp.result_distribution.values()) == len(resp.cases)


def test_case_cause_filter():
    svc = CaseSearchService()
    resp = svc.search(CaseSearchRequest(query="赔偿", cause="劳动争议"))
    assert all("劳动争议" in c.cause for c in resp.cases)


# ---------- P1-7 时效追踪 ----------


def test_statute_timeline_with_revisions():
    svc = _make_retriever()
    payload = svc.store.get("CN-XF-264")
    tl = build_statute_timeline("CN-XF-264", payload)
    assert tl.revisions, "刑法264条应带修订 diff"
    assert "旧法" in tl.advice or "修订" in tl.advice or "核对" in tl.advice
    assert tl.revisions[0].old_excerpt and tl.revisions[0].new_excerpt


def test_statute_timeline_effective_no_warning():
    svc = _make_retriever()
    payload = svc.store.get("CN-MINFA-577")
    tl = build_statute_timeline("CN-MINFA-577", payload)
    assert tl.status == "effective"
    assert "废止" not in tl.advice


# ---------- P1-8 多模态路由 ----------


def test_route_contract():
    assert route_content("本合同由甲方乙方签署，违约金十万元") == "contract"


def test_route_accident():
    assert route_content("交通事故现场照片，交警出具责任认定书") == "accident"


def test_route_medical():
    assert route_content("医院出具的诊断证明和医疗费票据") == "medical"


def test_route_chat():
    assert route_content("微信聊天记录截图，对方转账2000元") == "chat"


def test_multimodal_degrades_gracefully_without_ocr():
    """无 OCR 后端时必须如实降级，不得假装识别成功。"""
    svc = MultimodalService(ContractScanService(_make_retriever()))
    result = svc.analyze(b"\x89PNG fake image bytes")
    if result.get("ok") is False:
        assert "OCR" in result["error"] or "paddleocr" in result["error"]
        assert result["route"] == "none"
