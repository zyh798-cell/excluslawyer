# -*- coding: utf-8 -*-
"""数据管道公共基类与抓取会话。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class RawArticle:
    """源格式条文（未归一）。"""

    article_no: str  # 当地语言条号，如 第一百八十八条 / 第1条 / 제1조 / "1."
    text: str  # 条文正文
    caption: str = ""  # 条标，如 （目的）


@dataclass
class RawLaw:
    """一部法律的抓取结果。"""

    source: str  # cn_flk / jp_egov / kr_law / sg_sso
    source_id: str  # bbbs / LawId / lsiSeq / Act 短码
    title: str
    jurisdiction: str  # CN/JP/KR/SG
    language: str  # zh/ja/ko/en
    law_level: str = "法律"
    promulgation_date: str | None = None  # 公布日 ISO
    effective_date: str | None = None  # 施行日 ISO
    status: str = "unknown"  # effective/amended/repealed/unknown
    amended_history: list[str] = field(default_factory=list)
    source_url: str = ""
    articles: list[RawArticle] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class FetchSession:
    """带重试/限速的共享 HTTP 会话。"""

    def __init__(self, timeout: int = 45, sleep_s: float = 1.5, retries: int = 3):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT})
        self.timeout = timeout
        self.sleep_s = sleep_s
        self.retries = retries

    def get(self, url: str, **kw) -> requests.Response:
        return self._req("GET", url, **kw)

    def post(self, url: str, **kw) -> requests.Response:
        return self._req("POST", url, **kw)

    def _req(self, method: str, url: str, **kw) -> requests.Response:
        kw.setdefault("timeout", self.timeout)
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                r = self.s.request(method, url, **kw)
                if r.status_code == 200:
                    time.sleep(self.sleep_s)  # 官方源限速
                    return r
                # 4xx/202（WAF 挑战）立即失败交上层退避——底层重试只会加剧封禁
                if 400 <= r.status_code < 500 or r.status_code == 202:
                    raise RuntimeError(f"HTTP {r.status_code} for {url}")
                last = RuntimeError(f"HTTP {r.status_code} for {url}")
            except requests.RequestException as e:  # noqa: PERF203
                last = e
            time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"fetch failed: {url}") from last
