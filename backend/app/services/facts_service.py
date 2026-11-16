"""P0-2 案件事实结构化。

从案情叙述中抽取四类事实：
- confirmed（已确认）：叙述者以确定口吻陈述的既成事实
- to_verify（待核实）：带不确定表述、需要证据补强的事实
- assumption（假设）：条件句/假定情形
- claim（主张）：诉求、索赔要求、主张的法律结论

并抽取时间表达，生成时间线卡片（无法确定时间的排最后）。

P0 用规则抽取（无 LLM 也能跑，确定性、可测试）；P1 可换 LLM 抽取器，
输出结构不变。规则只做"分句 + 分类 + 抽时间"，绝不生成新内容。
"""

import re

from app.models.schemas import Fact, FactSet, FactType, TimelineCard

# ---- 分类规则（按优先级从上到下匹配，先命中先归类）----
# 顺序很重要：条件句往往也带"主张"字样，assumption 必须排在 claim 前面
_RULES: list[tuple[FactType, re.Pattern]] = [
    # 假设：条件/假定情形
    ("assumption", re.compile(r"如果|假如|假设|万一|要是|若是|假定|倘若|如.*则")),
    # 待核实：不确定、传闻、待确认
    ("to_verify", re.compile(r"不清楚|不确定|待核实|待确认|据说|听说|好像|大概|也许|记不清|无法确认|疑似|可能需要核实|没证据|没有.*证据|缺")),
    # 主张：诉求、索赔、要求承担责任
    ("claim", re.compile(r"主张|索赔|要求.{0,8}(支付|赔|承担|解除|履行|补偿|给付|返还)|请求.{0,8}(支付|承担)|告他|起诉|申请仲裁|应当赔|应该赔|必须赔|我方认为|我认为")),
    # 已确认：完成体/确定性陈述
    ("confirmed", re.compile(r"已[经于]|了[。？！，]|签订|签署|支付|交付|收到|入职|离职|辞退|解除|转账|打款|开具|实际|确实|当时|至今|一直")),
]

# ---- 时间表达抽取 ----
_DATE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # 2024年3月15日 / 2024年3月 → 年-月[-日]
    (
        re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})?日?"),
        "abs",
    ),
    # 2024-03-15 / 2024/3/15
    (
        re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})"),
        "abs",
    ),
    # 3月15日（无年份，按当年近似）
    (re.compile(r"(?<!\d)(\d{1,2})月\s*(\d{1,2})日"), "month-day"),
    # 相对时间
    (re.compile(r"前年"), "rel:-2y"),
    (re.compile(r"去年|上一年"), "rel:-1y"),
    (re.compile(r"今年|本年"), "rel:0y"),
    (re.compile(r"上上个月"), "rel:-2m"),
    (re.compile(r"上个月"), "rel:-1m"),
    (re.compile(r"本月|这个月"), "rel:0m"),
    (re.compile(r"上周"), "rel:-1w"),
    (re.compile(r"最近"), "rel:recent"),
    (re.compile(r"至今|目前"), "rel:now"),
]

_SENT_SPLIT = re.compile(r"[。！？；\n]+")

# 相对时间 → 排序键（粗粒度，仅用于时间线排序）
_REL_SORT = {
    "rel:-2y": "0002-01-01",
    "rel:-1y": "0001-01-01",
    "rel:0y": "0000-02-01",
    "rel:-2m": "0000-04-01",
    "rel:-1m": "0000-05-01",
    "rel:0m": "0000-06-01",
    "rel:-1w": "0000-07-01",
    "rel:recent": "0000-08-01",
    "rel:now": "0000-09-01",
}


def _classify(sentence: str) -> FactType:
    """按规则给句子分到四类事实之一；默认归待核实（保守：没把握的不进已确认）。"""
    for fact_type, pattern in _RULES:
        if pattern.search(sentence):
            return fact_type
    return "to_verify"


def _extract_date(sentence: str) -> tuple[str | None, str]:
    """抽取时间表达，返回 (展示标签, 排序键)。抽不到 → (None, 末尾排位)。"""
    for pattern, kind in _DATE_PATTERNS:
        m = pattern.search(sentence)
        if not m:
            continue
        if kind == "abs":
            year = m.group(1)
            month = m.group(2).zfill(2)
            day = m.group(3).zfill(2) if m.lastindex and m.lastindex >= 3 and m.group(3) else "01"
            return f"{year}-{month}-{day}", f"{year}-{month}-{day}"
        if kind == "month-day":
            month = m.group(1).zfill(2)
            day = m.group(2).zfill(2)
            return f"{month}月{day}日（当年）", f"0001-{month}-{day}"
        # 相对时间
        label_map = {
            "rel:-2y": "前年",
            "rel:-1y": "去年",
            "rel:0y": "今年",
            "rel:-2m": "上上个月",
            "rel:-1m": "上个月",
            "rel:0m": "本月",
            "rel:-1w": "上周",
            "rel:recent": "最近",
            "rel:now": "至今",
        }
        return label_map[kind], _REL_SORT[kind]
    return None, "9999-99-99"


def structure_facts(narrative: str) -> FactSet:
    """把案情叙述结构化为四类事实 + 时间线卡片。"""
    raw_sentences = [s.strip() for s in _SENT_SPLIT.split(narrative) if s.strip()]
    facts: list[Fact] = []
    for sent in raw_sentences:
        fact_type = _classify(sent)
        date_label, _ = _extract_date(sent)
        facts.append(Fact(text=sent, fact_type=fact_type, date_label=date_label))

    # 组装时间线：有时间的按时间正序，无时间的排最后保持原文顺序
    timeline: list[TimelineCard] = []
    for f in facts:
        _, sort_key = _extract_date(f.text)
        timeline.append(
            TimelineCard(
                date_label=f.date_label or "时间待查",
                sort_key=sort_key,
                event_text=f.text,
                fact_type=f.fact_type,
            )
        )
    timeline.sort(key=lambda c: c.sort_key)

    counts: dict[str, int] = {"confirmed": 0, "to_verify": 0, "assumption": 0, "claim": 0}
    for f in facts:
        counts[f.fact_type] += 1

    return FactSet(facts=facts, timeline=timeline, counts=counts)
