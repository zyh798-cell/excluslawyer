# -*- coding: utf-8 -*-
"""韩国·国家法令信息中心（law.go.kr）适配器。

流程（无开放 API 密钥，走官方网页端点）：
1. GET /법령/{名称}（或 lsInfoP.do?lsiSeq=）→ 页面 hidden inputs（lsId/lsiSeq/ancYd/ancNo）
2. POST lsInfoR.do（带全套参数）→ 法令正文 HTML 片段（.lawcon 块）
3. 抽取 제N조（条标）+ 条文文本
"""
from __future__ import annotations

import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from .base import FetchSession, RawArticle, RawLaw

BASE = "https://www.law.go.kr"

# 제N조 或 제N조의M（允许后随条标括号）
JO_RE = re.compile(r"^제(\d+)조(?:의(\d+))?")


def _to_iso(yymmdd: str | None) -> str | None:
    if not yymmdd or len(yymmdd) != 8 or not yymmdd.isdigit():
        return None
    return f"{yymmdd[:4]}-{yymmdd[4:6]}-{yymmdd[6:8]}"


class KrLawSource:
    source = "kr_law"

    def __init__(self, session: FetchSession | None = None):
        self.ses = session or FetchSession()

    def fetch_page_meta(self, name: str) -> dict:
        """别名页 → hidden inputs 元数据。"""
        url = f"{BASE}/%EB%B2%95%EB%A0%B9/{quote(name)}"  # /법령/名称
        r = self.ses.get(url, headers={"Accept-Language": "ko"})
        html = r.text
        if "lsInfoP" not in html and "lsiSeq" not in html:
            raise RuntimeError(f"kr: page not found for {name}")
        meta = {}
        # 主 hidden inputs：id 直取
        for key in ("lsId", "lsiSeq", "ancYd", "ancNo", "lsNm"):
            m = re.search(
                rf'<input[^>]*id="{key}"[^>]*value="([^"]*)"|'
                rf'<input[^>]*value="([^"]*)"[^>]*id="{key}"',
                html,
            )
            if m:
                meta[key] = m.group(1) or m.group(2)
        # 施行日：frm_efYd（name="efYd"，与公布日常常不同，取错会报 기본정보 조회 실패）
        m = re.search(r'<input[^>]*name="efYd"[^>]*value="(\d{8})"', html)
        if not m:
            m = re.search(r'<input[^>]*id="frm_efYd"[^>]*value="(\d{8})"', html)
        if m:
            meta["efYd"] = m.group(1)
        if "lsiSeq" not in meta:
            raise RuntimeError(f"kr: lsiSeq not found for {name}")
        meta["page_html"] = html
        return meta

    def fetch_body(self, meta: dict) -> str:
        """POST lsInfoR.do → 正文 HTML（缺 lsId/ancYd 等会报 기본정보 조회 실패）。"""
        payload = {
            "lsiSeq": meta.get("lsiSeq", ""),
            "lsId": meta.get("lsId", ""),
            "chrClsCd": "010202",  # 한글
            "ancYnChk": "0",
            "ancYd": meta.get("ancYd", ""),
            "ancNo": meta.get("ancNo", ""),
            "efYd": meta.get("efYd") or meta.get("ancYd", ""),
            "lsNm": meta.get("lsNm", ""),
            "target": "law",
        }
        r = self.ses.post(
            f"{BASE}/lsInfoR.do",
            data=payload,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        html = r.text
        if "제1조" not in html and "법con" not in html and "lawcon" not in html:
            raise RuntimeError(f"kr: body fetch failed for {meta.get('lsNm')}")
        return html

    @staticmethod
    def parse_body(html: str) -> list[RawArticle]:
        soup = BeautifulSoup(html, "lxml")
        articles: list[RawArticle] = []
        for block in soup.select("div.lawcon"):
            label = block.select_one("span.bl label")
            if not label:
                continue
            m = JO_RE.match(label.get_text(strip=True))
            if not m:
                continue
            no = label.get_text(strip=True)
            # 去掉 label/checkbox 后取正文
            text = block.get_text(" ", strip=True)
            text = text.replace(label.get_text(strip=True), " ", 1)
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            # 条标在 label 原文括号里：제1조(법원)
            full = label.get_text(strip=True)
            caption = ""
            cm2 = re.search(r"[（(]([^）)]*)[）)]", full)
            if cm2:
                caption = cm2.group(1)
            articles.append(RawArticle(article_no=no, text=text, caption=caption))
        return articles

    def fetch_law(self, name: str) -> RawLaw:
        meta = self.fetch_page_meta(name)
        body = self.fetch_body(meta)
        articles = self.parse_body(body)

        anc = _to_iso(meta.get("ancYd"))
        history = []
        if anc:
            history.append(f"{anc} 公布")
        if meta.get("ancNo"):
            history.append(f"공포번호 {meta['ancNo']}")

        return RawLaw(
            source=self.source,
            source_id=meta.get("lsiSeq", ""),
            title=name,
            jurisdiction="KR",
            language="ko",
            law_level="법률",
            promulgation_date=anc,
            effective_date=_to_iso(meta.get("efYd")),
            status="effective",  # 법령/别名默认现行
            amended_history=history,
            source_url=f"{BASE}/lsInfoP.do?lsiSeq={meta.get('lsiSeq')}",
            articles=articles,
        )
