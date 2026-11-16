# -*- coding: utf-8 -*-
"""新加坡·Singapore Statutes Online（sso.agc.gov.sg）适配器。

- GET /Act/{短码}  → 元数据 + 修订时间线（Historical versions）
- GET /Act/{短码}?WholeDoc=1 / ?ViewType=Print → 全文条文（prov1 块）
注意：站点有 AWS WAF JS 盾，202+challenge.html 为拦截；带完整浏览器头 + 退避重试。
"""
from __future__ import annotations

import html as html_mod
import io
import re
import time

from bs4 import BeautifulSoup

from .base import FetchSession, RawArticle, RawLaw

BASE = "https://sso.agc.gov.sg"

BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-SG,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

PROV_TXT_RE = re.compile(r"^\s*(\d+)\.\s*(?:—|&#x2014;|-)?\s*")
# PDF 行首条号两种式样：'1.—(1)' 破折号式长条 / '6.  Where' 空格式短条（点后 1+ 空格 + 大写/括号）。
# 只认行首：目录条目（'6.       Title'）靠区段选择排除，"Rule 1.—" 等正文内嵌编号天然不匹配。
PDF_LINE_RE = re.compile(
    r"(?m)^[ \t]*(\d{1,2})\.(?:(?:—|–|&#x2014;)[ \t]*|[ \t]+(?=[A-Z\[\(]))"
)
# 尾部非条文区标题行：Schedule / 修订对照表 / 立法沿革（末条裁剪用）
TAIL_MARKERS_RE = re.compile(
    r"(?m)^[ \t]*(?:THE[ \t]+)?SCHEDULE(?:[ \t]*(?:[—–-].*|\d+[A-Z]?))?$"
    r"|^[ \t]*COMPARATIVE[ \t]+TABLE"
    r"|^[ \t]*LEGISLATIVE[ \t]+HISTORY"
)


def split_pdf_text(text: str) -> list[RawArticle]:
    """按行首条号切 PDF layout 文本为条文。

    PDF 文本含目录区、Schedule、修订对照表等多段同号编号，处理策略：
    1. 编号回落（num < prev）即切新区段（目录/正文/Schedule/沿革各自成段）；
    2. 正文区 = 跨度最大的区段（目录是单行标题跨度小，Schedule/沿革同理）；
    3. 末条终点裁到 Schedule/对照表/沿革标题行。
    """
    anchors = list(PDF_LINE_RE.finditer(text))
    if not anchors:
        return []
    runs: list[list[re.Match]] = [[anchors[0]]]
    for a in anchors[1:]:
        if int(a.group(1)) < int(runs[-1][-1].group(1)):
            runs.append([])
        runs[-1].append(a)
    body = max(runs, key=lambda r: (r[-1].start() - r[0].start(), r[0].start()))
    body_start = body[0].start()
    cut = len(text)
    tm = TAIL_MARKERS_RE.search(text, body_start)
    if tm:
        cut = tm.start()
    all_starts = [a.start() for a in anchors]
    out: dict[str, RawArticle] = {}
    for i, m in enumerate(body):
        no = m.group(1)
        nxt = body[i + 1].start() if i + 1 < len(body) else None
        if nxt is None:
            later = [p for p in all_starts if p > m.start()]
            nxt = later[0] if later else cut
        seg = text[m.end():min(nxt, cut)]
        seg = re.sub(r"\s+", " ", seg).strip()
        if len(seg) < 5:
            continue
        key = f"{no}."
        # 同号重复（重印/夹入）保留更长正文
        if key not in out or len(seg) > len(out[key].text):
            out[key] = RawArticle(article_no=key, text=seg, caption="")
    return sorted(out.values(), key=lambda a: int(a.article_no.rstrip(".")))


class SgSsoSource:
    source = "sg_sso"

    def __init__(self, session: FetchSession | None = None):
        self.ses = session or FetchSession()

    def _get_with_retry(self, url: str, attempts: int = 4) -> str:
        """WAF 202 挑战时退避重试（盾是间歇性的；请求数越少越容易挤进窗口）。"""
        for i in range(attempts):
            r = self.ses.get(url, headers=BROWSER_HEADERS)
            if r.status_code == 200 and "awswaf" not in r.text[:2000] and "<body" in r.text:
                return r.text
            time.sleep(15 * (i + 1))
        raise RuntimeError(f"sg: WAF blocked after {attempts} attempts: {url}")

    def fetch_act(self, act_code: str) -> tuple[str, str, bytes | None]:
        """主页面（时间线）+ 全文：优先 PDF 单请求（WAF 友好），退 HTML WholeDoc。"""
        main = self._get_with_retry(f"{BASE}/Act/{act_code}")
        pdf = None
        try:
            r = self.ses.get(
                f"{BASE}/Act/{act_code}?ViewType=Pdf",
                headers=BROWSER_HEADERS,
                timeout=90,
            )
            if r.status_code == 200 and r.content.startswith(b"%PDF"):
                pdf = r.content
        except Exception:
            pass
        whole = ""
        if pdf is None:
            # WholeDoc 与 Print 两种全文视图互为备份（WAF 可能只拦其一）
            for u in (f"{BASE}/Act/{act_code}?WholeDoc=1", f"{BASE}/Act/{act_code}?ViewType=Print"):
                try:
                    whole = self._get_with_retry(u, attempts=3)
                    break
                except RuntimeError:
                    continue
            if not whole:
                whole = main
        return main, whole, pdf

    @staticmethod
    def parse_provisions_from_pdf(pdf_bytes: bytes) -> list[RawArticle]:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        # layout 模式保留字体拼接处的空格（plain 会把 'In this' 压成 'Inthis'）
        text = "\n".join(
            (page.extract_text(extraction_mode="layout") or page.extract_text() or "")
            for page in reader.pages
        )
        return split_pdf_text(text)

    @staticmethod
    def parse_timeline(page_html: str) -> list[str]:
        """Historical versions 链接 → 修订沿革。"""
        out = []
        for m in re.finditer(
            r"/Act/[A-Za-z0-9]+/Historical/(\d{8})\?DocDate=(\d{8})&amp;ValidDate=(\d{8})", page_html
        ):
            valid, doc = m.group(3), m.group(2)
            out.append(f"{valid[:4]}-{valid[4:6]}-{valid[6:8]} 版本（文件日 {doc[:4]}-{doc[4:6]}-{doc[6:8]}）")
        if not out:
            for m in re.finditer(r"ValidDate=(\d{8})", page_html):
                v = m.group(1)
                out.append(f"{v[:4]}-{v[4:6]}-{v[6:8]} 版本")
        # 去重保序
        seen, uniq = set(), []
        for x in out:
            if x not in seen:
                seen.add(x)
                uniq.append(x)
        return uniq

    @staticmethod
    def parse_provisions(html_text: str) -> list[RawArticle]:
        soup = BeautifulSoup(html_text, "lxml")
        by_no: dict[str, RawArticle] = {}
        for hdr in soup.select(".prov1Hdr"):
            txt_el = hdr.find_next(class_="prov1Txt")
            if txt_el is None:
                continue
            raw_txt = txt_el.get_text(" ", strip=True)
            raw_txt = html_mod.unescape(raw_txt)
            m = PROV_TXT_RE.match(raw_txt)
            if not m:
                continue
            no = m.group(1)
            body = raw_txt[m.end():].strip()
            title = hdr.get_text(" ", strip=True)
            title = re.sub(r"\s+", " ", title).strip()
            if not body:
                continue
            key = f"{no}."
            # 多视图/分页并集：同号保留更长正文
            if key not in by_no or len(body) > len(by_no[key].text):
                by_no[key] = RawArticle(article_no=key, text=body, caption=title)
        return sorted(by_no.values(), key=lambda a: int(a.article_no.rstrip(".")))

    def fetch_law(self, act_code: str, title_hint: str | None = None) -> RawLaw:
        main, whole, pdf = self.fetch_act(act_code)
        # PDF（条全）与 HTML（字净）取并集，同号保留更长正文
        by_no: dict[str, RawArticle] = {}
        for arts in (
            self.parse_provisions_from_pdf(pdf) if pdf else [],
            self.parse_provisions(whole if "prov1" in whole else main),
        ):
            for a in arts:
                if a.article_no not in by_no or len(a.text) > len(by_no[a.article_no].text):
                    by_no[a.article_no] = a
        articles = sorted(by_no.values(), key=lambda a: int(a.article_no.rstrip(".")))
        if not articles:
            raise RuntimeError(f"sg: no provisions parsed for {act_code}")

        title = title_hint
        if not title:
            tm = re.search(r"<title>\s*([^<]+?)\s*- Singapore Statutes Online", main)
            title = tm.group(1).strip() if tm else act_code
        # 立法年份
        ym = re.search(r"\b(18|19|20)\d{2}\b", title)
        prom = f"{ym.group(0)}" if ym else None
        timeline = self.parse_timeline(main)

        return RawLaw(
            source=self.source,
            source_id=act_code,
            title=title,
            jurisdiction="SG",
            language="en",
            law_level="Act",
            promulgation_date=prom,
            effective_date=None,
            status="effective",  # 默认 Current 视图
            amended_history=timeline[:20],
            source_url=f"{BASE}/Act/{act_code}",
            articles=articles,
        )
