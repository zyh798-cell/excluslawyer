"""P0-2 事实结构化单测：四分类、时间线排序、保守兜底。"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.services.facts_service import structure_facts

NARRATIVE = (
    "2024年3月我入职某公司，月薪1万元。公司一直没和我签书面劳动合同。"
    "2025年1月起公司开始拖欠工资，至今共欠3个月工资3万元。"
    "我已于2025年7月提出离职，但公司拒绝支付经济补偿。"
    "我认为公司应当支付拖欠工资和赔偿金。"
    "如果公司伪造了考勤记录，那我需要申请仲裁。"
    "听说公司账上没钱了，不清楚能不能执行到。"
)


def test_four_types_present():
    fs = structure_facts(NARRATIVE)
    kinds = {f.fact_type for f in fs.facts}
    assert "confirmed" in kinds, "入职/离职等既成事实应归已确认"
    assert "claim" in kinds, "索赔诉求应归主张"
    assert "assumption" in kinds, "条件句应归假设"
    assert "to_verify" in kinds, "不确定表述应归待核实"


def test_counts_consistent():
    fs = structure_facts(NARRATIVE)
    assert sum(fs.counts.values()) == len(fs.facts)
    assert fs.counts["confirmed"] >= 2


def test_timeline_sorted():
    fs = structure_facts(NARRATIVE)
    keys = [t.sort_key for t in fs.timeline]
    assert keys == sorted(keys), "时间线必须按时间正序"
    # 2024-03 入职应在 2025-01 拖欠之前
    labels = [(t.date_label, t.event_text) for t in fs.timeline]
    idx_2024 = next(i for i, (d, _) in enumerate(labels) if d.startswith("2024-03"))
    idx_2025 = next(i for i, (d, _) in enumerate(labels) if d.startswith("2025-01"))
    assert idx_2024 < idx_2025


def test_unknown_date_goes_last():
    fs = structure_facts("他欠我钱。2024年5月10日打了借条。")
    assert fs.timeline[-1].date_label == "时间待查"
    assert fs.timeline[0].date_label.startswith("2024-05")


def test_assumption_beats_claim_priority():
    """条件句里即便有'主张/要求'字样也应归假设（规则优先级保证）。"""
    fs = structure_facts("如果对方要求赔偿，我方需要准备证据。")
    assert fs.facts[0].fact_type == "assumption"


def test_conservative_default():
    """无任何线索的句子默认待核实，不冒进归已确认。"""
    fs = structure_facts("这件事说来话长。")
    assert fs.facts[0].fact_type == "to_verify"
