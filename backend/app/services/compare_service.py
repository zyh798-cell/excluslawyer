"""P2-12 多法域对比：主题识别 → 四法域规则并列对比。

数据：cross_jurisdiction_topics.json（概要种子，外法域标注"需官源核对"）。
正式版按 jurisdiction 字段从 lex-data-cn/jp/kr/sg 数据仓拉取现行条文。
"""

import json
import re
from pathlib import Path

from app.models.schemas import (
    CompareRequest,
    CompareResponse,
    JurisdictionRule,
)

DEFAULT_TOPICS = Path(__file__).resolve().parents[2] / "data" / "cross_jurisdiction_topics.json"

_CODE_NAME = {"CN": "中国", "JP": "日本", "KR": "韩国", "SG": "新加坡"}


class CompareService:
    def __init__(self, topics_path: Path | None = None):
        path = topics_path or DEFAULT_TOPICS
        blob = json.loads(path.read_text(encoding="utf-8"))
        self.topics: list[dict] = blob["topics"]

    def _match_topic(self, query: str) -> dict | None:
        best: tuple[int, dict] | None = None
        for topic in self.topics:
            score = sum(len(k) for k in topic["keywords"] if k in query)
            if score > 0 and (best is None or score > best[0]):
                best = (score, topic)
        return best[1] if best else None

    def compare(self, req: CompareRequest, causes: list[str] | None = None) -> CompareResponse:
        """按主题返回跨法域对比行。

        causes：可选案由过滤（如 ["合同"]）。传入时仅保留
        cause ∈ causes ∪ {"通用"} 的条目，排除与当前案由无关的条目
        （如合同案件混入劳动仲裁时效条目）；传 None 不过滤（API 默认行为）。
        """
        topic = self._match_topic(req.query)
        if topic is None:
            return CompareResponse(
                topic="未匹配主题",
                rows=[],
                takeaway=(
                    "暂未覆盖该主题的跨法域对比（现有主题：诉讼时效 / 违约金过高调减 / "
                    "未签书面劳动合同的责任 / 合同法定解除）。换个法律术语试试。"
                ),
            )

        wanted = {j.upper() for j in req.jurisdictions}
        allowed = set(causes) | {"通用"} if causes is not None else None
        rows = []
        for r in topic["rows"]:
            if r["jurisdiction"] not in wanted:
                continue
            if allowed is not None and r.get("cause", "通用") not in allowed:
                continue
            payload = {k: v for k, v in r.items() if k != "cause"}
            rows.append(JurisdictionRule(**payload))
        return CompareResponse(topic=topic["topic"], rows=rows, takeaway=topic.get("takeaway", ""))
