"""P2 模块单测：模拟法庭 / 知识图谱 / 计算器 / 多法域对比。"""

import sys
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.models.schemas import CalcRequest, CompareRequest, TrialStartRequest, TrialTurnRequest
from app.rag.embedder import HashingEmbedder
from app.rag.retriever import Retriever
from app.rag.vector_store import NumpyVectorStore
from app.services.calculator_service import CalculatorService
from app.services.compare_service import CompareService
from app.services.kg_service import KgService
from app.services.trial_service import TrialService
from scripts.ingest_cn import ingest_seed


def _make_retriever() -> Retriever:
    emb = HashingEmbedder(dim=128)
    store = NumpyVectorStore(path=None)
    ingest_seed(emb, store)
    return Retriever(emb, store)


# ---------- P2-9 模拟法庭 ----------


def test_trial_start_opens_with_judge_and_opponent():
    svc = TrialService(_make_retriever())
    s = svc.start(TrialStartRequest(case_description="公司拖欠我工资三个月，我要求支付并索赔。", user_role="plaintiff"))
    roles = [t.role for t in s.turns]
    assert roles == ["judge", "opponent"]
    assert s.status == "ongoing" and s.round == 1
    assert "争议焦点" in s.turns[0].content


def test_trial_three_rounds_then_verdict():
    svc = TrialService(_make_retriever())
    s = svc.start(TrialStartRequest(case_description="公司没签劳动合同，拖欠工资，我要求二倍工资。"))
    for i in range(3):
        s = svc.turn(TrialTurnRequest(session_id=s.id, user_statement=f"第{i+1}轮：我有工资流水为证。"))
    assert s.status == "closed"
    last = s.turns[-1]
    assert last.role == "judge" and "模拟判决" in last.content
    assert "不具" in last.content or "不构成法律意见" in last.content  # 免责声明必须有


def test_trial_opponent_uses_legal_defenses():
    svc = TrialService(_make_retriever())
    s = svc.start(TrialStartRequest(case_description="两年前的欠款，现在要求还款。"))
    s = svc.turn(TrialTurnRequest(session_id=s.id, user_statement="对方欠我钱没还。"))
    opp = next(t for t in s.turns if t.role == "opponent" and t.round == 1)
    assert "抗辩" in opp.content or "驳回" in opp.content


def test_trial_unknown_session_raises():
    svc = TrialService(_make_retriever())
    try:
        svc.turn(TrialTurnRequest(session_id="nonexistent", user_statement="x"))
        assert False, "应抛 KeyError"
    except KeyError:
        pass


# ---------- P2-10 知识图谱 ----------


def test_kg_breach_elements():
    resp = KgService().query("违约责任的构成要件是什么")
    assert resp.matched_node and resp.matched_node.name == "违约责任"
    assert "违约行为" in resp.answer and "损害后果" in resp.answer
    assert resp.statute_ids, "应挂出依据条文"


def test_kg_multi_hop_statutes():
    resp = KgService().query("违约责任")
    assert any("CN-MINFA-577" in sid or "CN-MINFA-584" in sid for sid in resp.statute_ids)
    assert len(resp.paths) >= 2, "多跳至少展开两条路径"


def test_kg_limitation():
    resp = KgService().query("诉讼时效多久")
    assert "三年" in resp.answer or "CN-MINFA-188" in resp.statute_ids


def test_kg_unknown_concept():
    resp = KgService().query("量子通信频谱许可的行政程序")
    assert resp.matched_node is None
    assert "未命中" in resp.answer


# ---------- P2-11 计算器 ----------


def test_economic_compensation_normal():
    r = CalculatorService().calculate(
        CalcRequest(calc_type="economic_compensation", params={"years": 3.5, "monthly_salary": 10000})
    )
    # 3.5年 → 4年折算（7个月≥6个月进1年）→ 40000
    assert r.total == 40000
    assert "CN-LDF-47" in r.basis


def test_economic_compensation_cap():
    r = CalculatorService().calculate(
        CalcRequest(
            calc_type="economic_compensation",
            params={"years": 15, "monthly_salary": 50000, "region_avg_salary": 10000},
        )
    )
    # 3倍封顶=30000，年限封顶12年 → 360000
    assert r.total == 360000


def test_double_wage():
    r = CalculatorService().calculate(
        CalcRequest(calc_type="double_wage", params={"monthly_salary": 8000, "months_uncovered": 7})
    )
    assert r.total == 56000


def test_personal_injury_disability():
    r = CalculatorService().calculate(
        CalcRequest(
            calc_type="personal_injury",
            params={"medical": 30000, "lost_income": 20000, "disability_level": 10, "annual_income": 50000},
        )
    )
    # 30000+20000+50000*20*0.1 = 150000
    assert r.total == 150000


def test_liquidated_damages_too_high():
    r = CalculatorService().calculate(
        CalcRequest(calc_type="liquidated_damages", params={"agreed_penalty": 200000, "actual_loss": 100000})
    )
    assert r.total == 130000  # 调减到损失*1.3
    assert "CN-MINFA-585" in r.basis


def test_limitation_check_expired():
    r = CalculatorService().calculate(
        CalcRequest(calc_type="limitation_check", params={"damage_date": "2019-01-01", "known_date": "2019-01-01"})
    )
    assert any("届满" in i.note for i in r.items)


# ---------- P2-12 多法域对比 ----------


def test_compare_limitation_topic():
    resp = CompareService().compare(CompareRequest(query="诉讼时效是多久"))
    assert resp.topic == "诉讼时效"
    codes = {row.jurisdiction for row in resp.rows}
    assert codes == {"CN", "JP", "KR", "SG"}
    assert resp.takeaway


def test_compare_filter_jurisdictions():
    resp = CompareService().compare(CompareRequest(query="违约金过高怎么调减", jurisdictions=["CN", "SG"]))
    assert {row.jurisdiction for row in resp.rows} == {"CN", "SG"}


def test_compare_unknown_topic():
    resp = CompareService().compare(CompareRequest(query="外星人合同效力"))
    assert resp.topic == "未匹配主题"
    assert not resp.rows


def test_compare_cause_filter_excludes_foreign_limitation_rows():
    """按案由过滤：合同案件不得混入劳动仲裁时效条目（遗留项 2）。"""
    resp = CompareService().compare(CompareRequest(query="诉讼时效"), causes=["合同"])
    blob = "；".join(r.statute_ref + r.rule_summary for r in resp.rows)
    assert "劳动" not in blob, f"合同案由混入劳动条目：{blob}"
    # 通用时效条目保留（铁律 3 时效联动）
    assert any("第一百八十八条" in r.statute_ref for r in resp.rows)


def test_compare_cause_filter_keeps_matching_cause_rows():
    """劳动案由保留劳动仲裁时效条目，且通用条目仍在。"""
    resp = CompareService().compare(CompareRequest(query="诉讼时效"), causes=["劳动"])
    refs = "；".join(r.statute_ref for r in resp.rows)
    assert "劳动争议调解仲裁法" in refs
    assert "第一百八十八条" in refs


def test_compare_cause_filter_none_keeps_all():
    """API 默认（causes=None）不过滤，行为不变。"""
    resp = CompareService().compare(CompareRequest(query="诉讼时效"))
    refs = "；".join(r.statute_ref for r in resp.rows)
    assert "劳动争议调解仲裁法" in refs
    assert "第一百八十八条" in refs
