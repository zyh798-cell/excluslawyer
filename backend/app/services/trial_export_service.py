# -*- coding: utf-8 -*-
"""庭审全记录导出：Markdown / PDF（附全部法条引用链接）。

- to_markdown：纯文本组合，零依赖；
- to_pdf_bytes：reportlab + STSong-Light CID 字体（中文无需字体文件）。
两者内容同源，PDF 在 Markdown 结构之上排版。
"""
from __future__ import annotations

import re

from app.models.schemas import TRIAL_DISCLAIMER

_PHASE_TITLES = {
    "create_case": "案件创建",
    "fix_facts": "事实固定",
    "file_complaint": "提交诉状",
    "evidence_review": "举证质证",
    "debate": "法庭辩论",
    "closing": "总结陈词",
    "adjudicate": "模拟裁判",
}


def _md_escape(s: str) -> str:
    return (s or "").replace("|", "\\|").strip()


def to_markdown(record: dict) -> str:
    """会话快照（TrialGraphResponse dict）→ 全记录 Markdown。"""
    lines: list[str] = []
    add = lines.append
    add("# 模拟法庭庭审记录")
    add("")
    add(f"> {TRIAL_DISCLAIMER}")
    add("")
    add("## 一、案件信息")
    add("")
    add(f"- 会话 ID：{record.get('session_id', '')}")
    add(f"- 当前阶段：{_PHASE_TITLES.get(record.get('phase', ''), record.get('phase', ''))}")
    add(f"- 状态：{record.get('status', '')}")
    add(f"- 当事人角色：{record.get('user_role', '')}；法域：{record.get('jurisdiction', '')}")
    add("")
    if record.get("case_description"):
        add("## 案情")
        add("")
        add(record["case_description"])
        add("")

    facts = record.get("facts") or {}
    add("## 二、事实固定")
    add("")
    for f in facts.get("facts", []) or []:
        add(f"- [{f.get('fact_type', '')}] {f.get('text', '')}" + (f"（{f.get('date_label')}）" if f.get("date_label") else ""))
    if facts.get("timeline"):
        add("")
        add("时间线：")
        for t in facts["timeline"]:
            add(f"- {t.get('date_label', '')}：{t.get('event_text', '')}")
    add("")

    complaint = record.get("complaint") or {}
    add("## 三、诉状与主张（含双视角对抗）")
    add("")
    for i, c in enumerate(complaint.get("claims", []) or [], 1):
        add(f"### 主张 {i}：{_md_escape(c.get('text', ''))}")
        if c.get("relief"):
            add(f"- 诉求：{_md_escape(c['relief'])}")
        add(f"- 检索支撑：{ {'supported': '充分', 'partial': '偏弱', 'insufficient': '证据不足'}.get(c.get('support'), c.get('support')) }")
        for cit in c.get("citations", []) or []:
            link = cit.get("source_url") or ""
            ref = f"[{cit.get('statute_id')}] {cit.get('law_title', '')}{cit.get('article_no', '')}"
            add(f"- 法条溯源：{ref}" + (f" —— <{link}>" if link else ""))
        for h in c.get("holes", []) or []:
            add(f"- 对方视角漏洞：{h}")
        for r in c.get("risks", []) or []:
            add(f"- {r}")
        add("")
    if complaint.get("opposition_summary"):
        add("**对方律师视角总述**")
        add("")
        add("```")
        add(complaint["opposition_summary"])
        add("```")
        add("")

    reviews = record.get("evidence_reviews") or []
    add("## 四、举证质证")
    add("")
    for i, r in enumerate(reviews, 1):
        add(f"### 证据 {i}：{_md_escape(r.get('title', ''))}（{r.get('evidence_type', '')}）")
        add(f"- 要件匹配：{'、'.join(r.get('target_elements') or [])}（匹配度 {r.get('element_match')}）")
        add(f"- 证明力：{ {'strong': '强', 'medium': '中', 'weak': '弱'}.get(r.get('probative_strength'), '') }")
        for d in r.get("defects", []) or []:
            add(f"- 证据瑕疵：{d}")
        if r.get("note"):
            add(f"- 质证意见：{r['note']}")
        add("")

    lim = record.get("limitation") or {}
    add("## 五、时效联动")
    add("")
    if lim.get("checked"):
        add(f"- 风险等级：{ {'safe': '安全', 'warning': '临近届满', 'expired': '已届满'}.get(lim.get('risk_level'), lim.get('risk_level')) }")
        add(f"- 关键日期：{lim.get('key_date', '')}；届满：{lim.get('deadline', '')}")
        add(f"- 结论：{lim.get('summary', '')}")
        for cit in lim.get("citations", []) or []:
            link = cit.get("source_url") or ""
            add(f"- 法条：[{cit.get('statute_id')}] {cit.get('law_title', '')}{cit.get('article_no', '')}" + (f" —— <{link}>" if link else ""))
    else:
        add(f"- {lim.get('summary', '未进行时效检查')}")
    add("")

    turns = record.get("debate_turns") or []
    add("## 六、法庭辩论")
    add("")
    for t in turns:
        role = {"user": "你（当事人）", "opponent": "对方律师", "judge": "法官"}.get(t.get("role"), t.get("role"))
        add(f"**{role}**（第 {t.get('round', 0)} 轮）")
        add("")
        add(t.get("content", ""))
        add("")

    if record.get("closing_text"):
        add("## 七、总结陈词")
        add("")
        add(record["closing_text"])
        add("")

    verdict = record.get("verdict") or {}
    add("## 八、模拟裁判")
    add("")
    add(f"> {verdict.get('disclaimer', TRIAL_DISCLAIMER)}")
    add("")
    for i, it in enumerate(verdict.get("items", []) or [], 1):
        add(f"### 裁判 {i}：{it.get('decision', '')} —— {_md_escape(it.get('claim', ''))}")
        for r in it.get("reasons", []) or []:
            add(f"- 理由：{r}")
        if it.get("citation_ids"):
            add(f"- 法条溯源：{', '.join(it['citation_ids'])}")
        if it.get("case_refs"):
            add(f"- 判例参考：{'；'.join(it['case_refs'])}")
        if it.get("cross_refs"):
            add(f"- 跨法域对照：{'；'.join(it['cross_refs'])}")
        add("")
    if verdict.get("overall"):
        add(verdict["overall"])
        add("")
    for r in verdict.get("risk_notes", []) or []:
        add(f"- 风险提示：{r}")
    if verdict.get("cross_jurisdiction"):
        add("")
        add("跨法域对照：")
        for row in verdict["cross_jurisdiction"]:
            add(f"- {row.get('jurisdiction_name', row.get('jurisdiction', ''))}：{row.get('rule_summary', '')}（{row.get('statute_ref', '')}）")
    add("")

    # 全部法条引用链接清单
    seen: dict[str, dict] = {}
    def _collect(cits):
        for cit in cits or []:
            seen.setdefault(cit.get("statute_id", ""), cit)

    for c in complaint.get("claims", []) or []:
        _collect(c.get("citations"))
    _collect((record.get("complaint") or {}).get("citations"))
    _collect(lim.get("citations"))
    _collect(verdict.get("citations"))
    add("## 九、法条引用清单")
    add("")
    add("| ID | 法律 | 条文 | 原文链接 |")
    add("| --- | --- | --- | --- |")
    for sid, cit in seen.items():
        link = cit.get("source_url") or "-"
        add(f"| {sid} | {_md_escape(cit.get('law_title', ''))} | {_md_escape(cit.get('article_no', ''))} | {link} |")
    add("")
    add("---")
    add("")
    add(f"{TRIAL_DISCLAIMER}")
    return "\n".join(lines)


def to_pdf_bytes(record: dict) -> bytes:
    """Markdown 同源内容 → PDF（reportlab CID 中文字体）。"""
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    font = "STSong-Light"

    styles = {
        "h1": ParagraphStyle("h1", fontName=font, fontSize=16, leading=22, alignment=TA_CENTER, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName=font, fontSize=13, leading=18, spaceBefore=10, spaceAfter=4),
        "h3": ParagraphStyle("h3", fontName=font, fontSize=11, leading=15, spaceBefore=6, spaceAfter=2),
        "body": ParagraphStyle("body", fontName=font, fontSize=9.5, leading=14),
        "quote": ParagraphStyle("quote", fontName=font, fontSize=9.5, leading=14, textColor="#8B0000", spaceAfter=4),
        "small": ParagraphStyle("small", fontName=font, fontSize=8, leading=11, textColor="#444444"),
    }

    def esc(s: str) -> str:
        return (
            (s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    md = to_markdown(record)
    story = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            story.append(Spacer(1, 2 * mm))
        elif line.startswith("# "):
            story.append(Paragraph(esc(line[2:]), styles["h1"]))
        elif line.startswith("## "):
            story.append(Paragraph(esc(line[3:]), styles["h2"]))
        elif line.startswith("### "):
            story.append(Paragraph(esc(line[4:]), styles["h3"]))
        elif line.startswith("> "):
            story.append(Paragraph(esc(line[2:]), styles["quote"]))
        elif line.startswith("|") or line.startswith("---") or line.startswith("```"):
            if line.startswith("| ") and not re.match(r"^\|\s*-+", line):
                story.append(Paragraph(esc(line.strip("|").replace("|", " | ")), styles["small"]))
        elif line.startswith("- "):
            story.append(Paragraph("• " + esc(line[2:]), styles["body"]))
        else:
            story.append(Paragraph(esc(line), styles["body"]))

    import io

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title="模拟法庭庭审记录",
    )
    doc.build(story)
    return buf.getvalue()
