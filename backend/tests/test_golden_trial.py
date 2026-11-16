"""模拟法庭 Golden Set 回归门禁：幻觉 / 法条引用准确 / 时效联动。

与 golden_set.json（100 条主链路用例）相互独立：
- data/golden_set_trial.json 庭审场景用例
- 指标不达标即测试失败（每次改庭审 prompt / 节点自动回归）
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.eval.trial_golden_runner import load_trial_cases, run_trial_regression
from app.rag.embedder import HashingEmbedder
from app.rag.retriever import Retriever
from app.rag.vector_store import NumpyVectorStore
from scripts.ingest_cn import ingest_seed, load_statutes


def _build_graph():
    emb = HashingEmbedder(dim=128)
    store = NumpyVectorStore(path=None)
    ingest_seed(emb, store)
    retriever = Retriever(emb, store)
    from app.graph.trial_build import build_trial_graph, make_trial_checkpointer

    graph = build_trial_graph(retriever, checkpointer=make_trial_checkpointer())
    valid_ids = {s.id for s in load_statutes(BASE_DIR / "data" / "cn_statutes_sample.json")}
    return graph, valid_ids


def test_golden_trial_thresholds():
    graph, valid_ids = _build_graph()
    cases = load_trial_cases()
    assert len(cases) == 10, f"模拟法庭 Golden Set 应为 10 条，实际 {len(cases)}"

    report = run_trial_regression(graph, cases, valid_ids)
    m = report.metrics
    failures = "\n".join(f"{r.id} [{r.behavior}] {r.detail}" for r in report.failures)

    assert m["behavior_pass_rate"] >= 1.0, f"行为闸门未全通过\n{failures}"
    assert m["citation_recall"] >= 0.98, f"法条引用准确率 {m['citation_recall']:.2%} < 98%\n{failures}"
    assert m["hallucination_rate"] <= 0.03, f"幻觉率 {m['hallucination_rate']:.2%} > 3%\n{failures}"
    assert m["timeliness_accuracy"] >= 0.99, f"时效联动正确率 {m['timeliness_accuracy']:.2%} < 99%\n{failures}"


def test_golden_trial_cases_are_independent():
    """模拟法庭用例不污染主 Golden Set（主集断言 100 条不受影响）。"""
    from app.eval.golden_runner import load_cases

    main = load_cases(BASE_DIR / "data" / "golden_set.json")
    assert len(main) == 100
    trial = load_trial_cases()
    main_ids = {c.id for c in main}
    for c in trial:
        assert c.id not in main_ids, f"用例 ID 冲突: {c.id}"
