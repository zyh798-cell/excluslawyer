# -*- coding: utf-8 -*-
"""中国·国家法律法规数据库（flk.npc.gov.cn）适配器。

接口（自前端 bundle 逆向确认）：
- POST /law-search/search/list      检索（searchType=1 标题 / 2 全文）
- GET  /law-search/search/flfgDetails?bbbs=  详情（目录树+元数据）
- GET  /law-search/download/pc?bbbs=&format=docx|pdf  签名下载链接（公网 OBS）
sxx（时效性）枚举实测破译：1=已废止 2=旧版本(已被修订) 3=现行有效
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from xml.etree import ElementTree

from .base import FetchSession, RawArticle, RawLaw

API = "https://flk.npc.gov.cn/law-search"
SXX_MAP = {"1": "repealed", "2": "amended", "3": "effective"}

# 中文数字条号 → 排序键
CN_NUM = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9}


def cn_num_to_int(s: str) -> int:
    """第一百八十八条 → 188（仅用于排序/连续性校验）。"""
    total, section = 0, 0
    for ch in s:
        if ch in CN_NUM:
            section = CN_NUM[ch]
        elif ch == "十":
            total += (section or 1) * 10
            section = 0
        elif ch == "百":
            total += (section or 1) * 100
            section = 0
        elif ch == "千":
            total += (section or 1) * 1000
            section = 0
    return total + section


class CnFlkSource:
    source = "cn_flk"

    def __init__(self, session: FetchSession | None = None):
        self.ses = session or FetchSession()

    # ---------- 检索 ----------
    def search(self, keyword: str, size: int = 10, search_type: int = 1) -> list[dict]:
        payload = {
            "searchRange": 1, "sxrq": [], "gbrq": [], "searchType": search_type,
            "sxx": [], "gbrqYear": [], "flfgCodeId": [], "zdjgCodeId": [],
            "searchContent": keyword, "page": 1, "size": size,
        }
        r = self.ses.post(f"{API}/search/list", json=payload)
        data = r.json()
        rows = data.get("rows") or []
        for row in rows:
            row["title"] = re.sub(r"<[^>]+>", "", row.get("title") or "")
        return rows

    def find_exact(self, title: str) -> dict | None:
        """标题精确匹配现行有效版本（sxx=3 优先）。"""
        rows = self.search(title, size=10)
        exact = [r for r in rows if r["title"] == title]
        if not exact:
            return None
        exact.sort(key=lambda r: {"3": 0, "2": 1, "1": 2}.get(str(r.get("sxx")), 3))
        return exact[0]

    # ---------- 详情 ----------
    def detail(self, bbbs: str) -> dict:
        r = self.ses.get(f"{API}/search/flfgDetails", params={"bbbs": bbbs})
        data = r.json().get("data") or {}
        if not data:
            raise RuntimeError(f"flk detail empty for {bbbs}")
        return data

    # ---------- 全文下载 ----------
    def download_docx(self, bbbs: str) -> bytes:
        r = self.ses.get(f"{API}/download/pc", params={"bbbs": bbbs, "format": "docx"})
        data = r.json().get("data") or {}
        url = data.get("url")
        if not url:
            raise RuntimeError(f"flk download link empty for {bbbs}: {data}")
        resp = self.ses.get(url)
        if not resp.content.startswith(b"PK"):
            raise RuntimeError(f"flk docx download invalid for {bbbs}")
        return resp.content

    @staticmethod
    def parse_docx(docx: bytes) -> str:
        """docx → 纯文本（按段落拼接）。"""
        with zipfile.ZipFile(io.BytesIO(docx)) as z:
            xml = z.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paras = []
        for p in root.iter(f"{ns}p"):
            text = "".join(t.text or "" for t in p.iter(f"{ns}t"))
            paras.append(text)
        return "\n".join(paras)

    # ---------- 整部法律 ----------
    def fetch_law(self, title: str, tag: str | None = None) -> RawLaw:
        row = self.find_exact(title)
        if not row:
            raise RuntimeError(f"flk: title not found: {title}")
        bbbs = row["bbbs"]
        det = self.detail(bbbs)
        docx = self.download_docx(bbbs)
        text = self.parse_docx(docx)
        articles = split_cn_articles(text)

        status = SXX_MAP.get(str(det.get("sxx", row.get("sxx"))), "unknown")
        history = []
        if det.get("gbrq"):
            history.append(f"{det['gbrq']} 公布")
        if det.get("sxrq"):
            history.append(f"{det['sxrq']} 施行")

        return RawLaw(
            source=self.source,
            source_id=bbbs,
            title=title,
            jurisdiction="CN",
            language="zh",
            law_level=det.get("flxz") or "法律",
            promulgation_date=det.get("gbrq") or None,
            effective_date=det.get("sxrq") or None,
            status=status,
            amended_history=history,
            source_url=f"https://flk.npc.gov.cn/detail?id={bbbs}",
            articles=articles,
        )


ARTICLE_RE = re.compile(
    r"(?:^|(?<=[。；！？\n]))[ 　]*(第[零一二三四五六七八九十百千两]+条(?:之[零一二三四五六七八九十]+)?)(?=[　\s（(]|$)",
)
FALLBACK_RE = re.compile(r"((?<![一-鿿、，。；：])第[零一二三四五六七八九十百千两]+条)")


def split_cn_articles(text: str) -> list[RawArticle]:
    """按 条号 切分中文法条。先精确（后跟空白/括号），漏则宽松回退。"""
    matches = list(ARTICLE_RE.finditer(text))
    if not matches:
        matches = list(FALLBACK_RE.finditer(text))
    articles: list[RawArticle] = []
    for i, m in enumerate(matches):
        no = m.group(1)
        body_start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:end].strip()
        # 拆出条标（目的）
        caption = ""
        cm = re.match(r"[（(]([^）)]{1,40})[）)]\s*", body)
        if cm:
            caption = cm.group(1)
            body = body[cm.end():].strip()
        body = re.sub(r"\s+", "", body)
        if body:
            articles.append(RawArticle(article_no=no, text=body, caption=caption))
    return articles
