"""P1-6 类案参考：要素匹配裁判文书 → 裁判结果分布。

匹配策略（无 LLM，确定性）：
1. 案由过滤（可选）
2. 词面 2-gram 重叠打分：查询 vs 关键词 + 事实摘要 + 裁判要旨
3. 相关度达标的案件进入结果，统计裁判结果分布 + 支持率

数据：脱敏示例裁判文书（开发种子）；正式数据接入官方公开渠道，入库前必须脱敏。
"""

import json
import re
from pathlib import Path

from app.models.schemas import CaseRecord, CaseSearchRequest, CaseSearchResponse

DEFAULT_CASES = Path(__file__).resolve().parents[2] / "data" / "cn_cases_sample.json"

# 相关度下限（2-gram 重叠率）
CASE_OVERLAP_FLOOR = 0.06


def _bigrams(text: str) -> set[str]:
    cleaned = re.sub(r"[^\w一-鿿぀-ヿ가-힯]", "", text.lower())
    return set(cleaned[i : i + 2] for i in range(len(cleaned) - 1)) or {cleaned}


def _score(query: str, case: CaseRecord) -> float:
    hay = " ".join([case.cause, case.title, case.facts_summary, case.holding] + case.keywords)
    q = _bigrams(query)
    t = _bigrams(hay)
    overlap = len(q & t) / max(len(q), 1)
    # 关键词命中加权：查询里直接出现案件关键词的强化相关度
    kw_bonus = sum(1 for k in case.keywords if k in query) * 0.08
    return overlap + kw_bonus


class CaseSearchService:
    def __init__(self, cases_path: Path | None = None):
        path = cases_path or DEFAULT_CASES
        blob = json.loads(path.read_text(encoding="utf-8"))
        self.cases: list[CaseRecord] = [CaseRecord(**c) for c in blob["cases"]]

    def search(self, req: CaseSearchRequest) -> CaseSearchResponse:
        scored: list[tuple[float, CaseRecord]] = []
        for case in self.cases:
            if req.cause and req.cause not in case.cause:
                continue
            s = _score(req.query, case)
            if s >= CASE_OVERLAP_FLOOR:
                scored.append((s, case))
        scored.sort(key=lambda x: -x[0])
        top = [c for _, c in scored[: req.top_k]]

        dist = {"支持": 0, "部分支持": 0, "驳回": 0}
        for c in top:
            dist[c.result] = dist.get(c.result, 0) + 1
        total = len(top)
        support_rate = round((dist["支持"] + dist["部分支持"]) / total, 3) if total else 0.0

        return CaseSearchResponse(
            cases=top,
            result_distribution=dist,
            support_rate=support_rate,
        )
