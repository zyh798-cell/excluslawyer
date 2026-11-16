# -*- coding: utf-8 -*-
"""RawLaw → Statute 归一 + 数据质量校验。"""
from __future__ import annotations

import re

from app.models.schemas import Statute

from .base import RawLaw

# 与种子数据/golden set 兼容的法律标签（必须保持一致，否则回归指标失效）
LAW_TAGS = {
    "中华人民共和国民法典": "MINFA",
    "中华人民共和国劳动合同法": "LDF",
    "中华人民共和国刑法": "XF",
    "中华人民共和国消费者权益保护法": "XFZQ",
    "中华人民共和国劳动法": "LD",
    "日本国憲法": "KEN",
    "民法": "MIN",
    "労働基準法": "LAB",
    "会社法": "COA",
    "민법": "MIN",
    "헌법": "CON",
    "대한민국헌법": "CON",
    "근로기준법": "LBA",
    "형법": "CRL",
    "Contract Act 1967": "CA",
    "Employment Act 1968": "EA",
    "Constitution of the Republic of Singapore": "CONS",
    "Contracts (Rights of Third Parties) Act 2001": "CRTP",
    "Sale of Goods Act 1979": "SGA",
}


def slug_tag(title: str) -> str:
    """未知法律 → 确定性短标签。"""
    if title in LAW_TAGS:
        return LAW_TAGS[title]
    ascii_part = re.sub(r"[^A-Za-z]", "", title)
    if ascii_part:
        return ascii_part[:6].upper()
    return f"S{abs(hash(title)) % 10000:04d}"


def article_key(article_no: str) -> str:
    """条号 → ID 片段：
    '第一百八十八条'→188 / '第1条'→1 / '제1조의2'→1-2 /
    '第百条の二'→100-2 / '第一百三十三条之一'→133-1 / '1.'→1。
    """
    digits = re.findall(r"\d+", article_no)
    if digits:
        key = "-".join(digits)
    else:
        from .cn_flk import cn_num_to_int

        # 中/日汉字条号，含 之N / のN 子条
        m = re.search(
            r"([零一二三四五六七八九十百千两]+)条(?:[之の]([零一二三四五六七八九十]+))?",
            article_no,
        )
        if m:
            base = cn_num_to_int(m.group(1))
            key = f"{base}-{cn_num_to_int(m.group(2))}" if m.group(2) else str(base)
        else:
            key = re.sub(r"\W", "", article_no)
    # 附則（日）/ 부칙（韩）独立命名空间，避免与本则重号
    if article_no.startswith(("附則", "附则", "부칙")):
        key = f"F{key}"
    return key


def normalize(raw: RawLaw) -> list[Statute]:
    tag = slug_tag(raw.title)
    out: list[Statute] = []
    for art in raw.articles:
        text = art.text.strip()
        if not text:
            continue
        caption = art.caption.strip()
        if caption and caption not in text[: len(caption) + 2]:
            text = f"（{caption}）{text}"
        out.append(
            Statute(
                id=f"{raw.jurisdiction}-{tag}-{article_key(art.article_no)}",
                jurisdiction=raw.jurisdiction,
                language=raw.language,
                law_title=raw.title,
                law_level=raw.law_level,
                article_no=art.article_no,
                text=text,
                gloss="",
                effective_date=raw.effective_date,
                expiry_date=None,
                amended_history=list(raw.amended_history),
                status=raw.status,
                source_url=raw.source_url,
                topics=[],
                revisions=[],
            )
        )
    return out


def validate(statutes: list[Statute]) -> dict:
    """质量报告：完整性/重复/条号连续性/长度异常。"""
    ids = [s.id for s in statutes]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    missing_text = [s.id for s in statutes if len(s.text) < 8]
    no_date = [s.id for s in statutes if not s.effective_date and not s.amended_history]
    bad_status = [s.id for s in statutes if s.status not in
                  ("effective", "amended", "repealed", "unknown")]

    by_law: dict[str, list[int]] = {}
    for s in statutes:
        try:
            n = int(article_key(s.article_no))
        except ValueError:
            continue
        by_law.setdefault(s.law_title, []).append(n)
    gaps = {}
    for law, nums in by_law.items():
        nums = sorted(set(nums))
        if len(nums) < 2:
            continue
        expected = list(range(nums[0], nums[-1] + 1))
        missing = sorted(set(expected) - set(nums))
        if missing and len(missing) <= 30:
            gaps[law] = missing
        elif missing:
            gaps[law] = missing[:30] + [f"...共缺 {len(missing)} 条"]

    return {
        "total": len(statutes),
        "laws": {law: len(v) for law, v in by_law.items()},
        "duplicate_ids": dup,
        "too_short": missing_text[:20],
        "no_date_no_history": no_date[:20],
        "bad_status": bad_status,
        "numbering_gaps": gaps,
        "avg_text_len": int(sum(len(s.text) for s in statutes) / max(1, len(statutes))),
    }
