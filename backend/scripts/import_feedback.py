"""用户反馈闭环：'有误/引用过时' 样本自动进入 Golden Set 迭代队列。

流程：feedback.jsonl → 过滤 verdict ∈ {wrong, outdated} → 写入 golden_feedback.json
（标记 needs_review=true，进入回归报告的待标注区，不污染已标注指标）。

用法：
    python scripts/import_feedback.py
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.eval.golden_runner import FEEDBACK_GOLDEN  # noqa: E402

FEEDBACK_LOG = BASE_DIR / "data" / "feedback.jsonl"


def import_feedback() -> int:
    if not FEEDBACK_LOG.exists():
        print("暂无反馈记录（data/feedback.jsonl 不存在）")
        return 0

    existing_ids: set[str] = set()
    cases: list[dict] = []
    if FEEDBACK_GOLDEN.exists():
        blob = json.loads(FEEDBACK_GOLDEN.read_text(encoding="utf-8"))
        cases = blob.get("cases", [])
        existing_ids = {c["id"] for c in cases}

    added = 0
    with open(FEEDBACK_LOG, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("verdict") not in ("wrong", "outdated"):
                continue
            cid = f"FB-{i+1:03d}"
            if cid in existing_ids:
                continue
            cases.append(
                {
                    "id": cid,
                    "category": f"用户反馈-{rec.get('verdict')}",
                    "question": rec.get("question", ""),
                    "expect": {
                        "behavior": "answer",
                        "statute_ids": [],
                        "must_contain": [],
                        "must_not_contain": [],
                    },
                    "needs_review": True,
                    "note": rec.get("note", ""),
                    "answer_seen": rec.get("answer", "")[:500],
                }
            )
            added += 1

    FEEDBACK_GOLDEN.write_text(
        json.dumps({"meta": {"note": "用户反馈待标注区：needs_review=true 的用例不计入指标，供人工补标注后转正。"}, "cases": cases}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"新并入 {added} 条反馈样本 → {FEEDBACK_GOLDEN}（累计 {len(cases)} 条待标注）")
    return added


if __name__ == "__main__":
    import_feedback()
