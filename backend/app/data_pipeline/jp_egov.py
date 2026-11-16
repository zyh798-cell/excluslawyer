# -*- coding: utf-8 -*-
"""日本·e-Gov 法令 API 适配器（laws.e-gov.go.jp/api/1）。

- GET /lawlists/1           現行法令名一覧（XML）
- GET /lawdata/{LawId|法令番号}  法令全文（XML: LawFullText > Law > LawBody > Article）
"""
from __future__ import annotations

import re
from xml.etree import ElementTree

from .base import FetchSession, RawArticle, RawLaw

API = "https://laws.e-gov.go.jp/api/1"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(el) -> str:
    return "".join(el.itertext()).strip()


class JpEgovSource:
    source = "jp_egov"

    def __init__(self, session: FetchSession | None = None):
        self.ses = session or FetchSession()
        self._law_list: list[dict] | None = None

    def list_laws(self) -> list[dict]:
        if self._law_list is not None:
            return self._law_list
        r = self.ses.get(f"{API}/lawlists/1")
        root = ElementTree.fromstring(r.content)
        out = []
        for info in root.iter("LawNameListInfo"):
            def g(name):
                el = info.find(name)
                return (el.text or "").strip() if el is not None else ""
            out.append({
                "law_id": g("LawId"), "law_name": g("LawName"),
                "law_no": g("LawNo"), "promulgation_date": g("PromulgationDate"),
            })
        self._law_list = out
        return out

    def find(self, name: str) -> dict | None:
        for row in self.list_laws():
            if row["law_name"] == name:
                return row
        return None

    def law_data(self, law_id_or_no: str) -> bytes:
        r = self.ses.get(f"{API}/lawdata/{law_id_or_no}")
        if b"<Result>" in r.content and b"<Code>0</Code>" not in r.content:
            raise RuntimeError(f"egov lawdata error for {law_id_or_no}")
        return r.content

    @staticmethod
    def parse_law_xml(xml: bytes) -> tuple[list[RawArticle], dict]:
        """LawFullText XML → 条文列表 + 元数据。"""
        root = ElementTree.fromstring(xml)
        meta: dict = {}
        law = None
        for el in root.iter("Law"):
            law = el
            break
        if law is None:
            for el in root.iter():
                if _local(el.tag) == "Law":
                    law = el
                    break
        if law is None:
            raise RuntimeError("egov xml: no Law element")
        for k in ("Era", "Year", "Num", "LawType", "PromulgateMonth", "PromulgateDay"):
            meta[k.lower()] = law.attrib.get(k, "")
        num_el = root.find(".//LawNum")
        meta["law_num"] = (num_el.text or "").strip() if num_el is not None else ""

        articles: list[RawArticle] = []
        amend_nums: list[str] = []

        def walk(el, in_sup: bool = False):
            tag = _local(el.tag)
            if tag in ("SupplProvision", "SupplementaryProvision"):
                in_sup = True
                an = el.attrib.get("AmendLawNum")
                if an and an not in amend_nums:
                    amend_nums.append(an)
            if tag == "Article":
                title_el = el.find("ArticleTitle")
                cap_el = el.find("ArticleCaption")
                no = _text(title_el) if title_el is not None else ""
                caption = _text(cap_el).strip("（）()") if cap_el is not None else ""
                parts = []
                for para in el.iter("Paragraph"):
                    for sent in para.iter("Sentence"):
                        t = _text(sent)
                        if t:
                            parts.append(t)
                body = "".join(parts).strip()
                if no and body:
                    # 附則条文与本则重号（各有第一条），加前缀隔离
                    art_no = f"附則{no}" if in_sup else no
                    articles.append(RawArticle(article_no=art_no, text=body, caption=caption))
                return
            for child in el:
                walk(child, in_sup)

        walk(law)
        meta["amend_laws"] = amend_nums
        return articles, meta

    def fetch_law(self, name: str) -> RawLaw:
        row = self.find(name)
        if not row:
            raise RuntimeError(f"egov: law not found: {name}")
        xml = self.law_data(row["law_id"])
        articles, meta = self.parse_law_xml(xml)

        pub = row.get("promulgation_date") or ""
        pub_iso = f"{pub[:4]}-{pub[4:6]}-{pub[6:8]}" if len(pub) == 8 else None
        history = []
        if pub_iso:
            history.append(f"{pub_iso} 公布")
        law_no = row.get("law_no") or meta.get("law_num") or ""
        if law_no:
            history.append(f"法令番号 {law_no}")
        # 附則 AmendLawNum → 修正沿革（如 令和二年四月一日法律第八十八号）
        for an in meta.get("amend_laws", [])[:30]:
            history.append(f"改正 {an}")

        return RawLaw(
            source=self.source,
            source_id=row["law_id"],
            title=name,
            jurisdiction="JP",
            language="ja",
            law_level="法律",
            promulgation_date=pub_iso,
            effective_date=None,  # e-Gov 各法施行日需查附则，暂公布日为准
            status="effective",  # lawlists/1 为现行法令
            amended_history=history,
            source_url=f"https://laws.e-gov.go.jp/law/{row['law_id']}/",
            articles=articles,
        )
