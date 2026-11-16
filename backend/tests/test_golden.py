"""Golden Set 回归门禁：四大指标不达标则测试失败。

这是'每次改 prompt / 换模型自动回归'的落点——CI 里跑 pytest 即完成回归。
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.eval.golden_runner import load_cases, run_regression
from app.rag.embedder import HashingEmbedder
from app.rag.retriever import Retriever
from app.rag.vector_store import NumpyVectorStore
from app.services.ask_service import AskService
from scripts.ingest_cn import ingest_seed, load_statutes

# 待标注反馈用例不计入指标，但加载后展示数量
try:
    from app.eval.golden_runner import FEEDBACK_GOLDEN
except ImportError:  # pragma: no cover
    FEEDBACK_GOLDEN = None


def _build_service():
    emb = HashingEmbedder(dim=128)
    store = NumpyVectorStore(path=None)
    ingest_seed(emb, store)
    return AskService(Retriever(emb, store)), store


def test_golden_set_thresholds():
    svc, store = _build_service()
    valid_ids = {s.id for s in load_statutes(BASE_DIR / "data" / "cn_statutes_sample.json")}
    cases = load_cases(BASE_DIR / "data" / "golden_set.json")
    assert len(cases) == 100, f"Golden Set 应为 100 条，实际 {len(cases)}"

    report = run_regression(svc, cases, valid_ids)
    m = report.metrics
    failures = "\n".join(f"{r.id} [{r.behavior}] {r.detail}" for r in report.failures)

    assert m["citation_recall"] >= 0.98, f"法条引用准确率 {m['citation_recall']:.2%} < 98%\n{failures}"
    assert m["consistency"] >= 0.90, f"结论-依据一致性 {m['consistency']:.2%} < 90%\n{failures}"
    assert m["hallucination_rate"] <= 0.03, f"幻觉率 {m['hallucination_rate']:.2%} > 3%\n{failures}"
    assert m["timeliness_accuracy"] >= 0.99, f"时效正确率 {m['timeliness_accuracy']:.2%} < 99%\n{failures}"


def test_feedback_queue_does_not_pollute_metrics():
    """反馈待标注区不参与指标统计。"""
    if FEEDBACK_GOLDEN is None or not Path(FEEDBACK_GOLDEN).exists():
        return  # 尚无反馈，直接通过
    import json

    blob = json.loads(Path(FEEDBACK_GOLDEN).read_text(encoding="utf-8"))
    for c in blob.get("cases", []):
        assert c.get("needs_review") is True, f"反馈用例 {c['id']} 未标记 needs_review"
