"""Golden Set 回归 CLI：跑 100 条用例，输出报告，门槛不达标退出码 1。

用法（backend/ 目录下）：
    python scripts/golden_regression.py                 # 默认 hash+numpy（确定性，CI 可用）
    python scripts/golden_regression.py --report data/golden_report.md
    EMBEDDER=bge_m3 python scripts/golden_regression.py  # 换 BGE-M3 后跑同套用例比质量
"""

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.eval.golden_runner import (  # noqa: E402
    DEFAULT_GOLDEN,
    FEEDBACK_GOLDEN,
    format_report,
    load_cases,
    run_regression,
)
from app.rag.embedder import get_embedder  # noqa: E402
from app.rag.retriever import Retriever  # noqa: E402
from app.rag.vector_store import get_vector_store  # noqa: E402
from app.services.ask_service import AskService  # noqa: E402
from scripts.ingest_cn import ingest_seed  # noqa: E402


def build_service():
    embedder = get_embedder()
    store = get_vector_store(embedder.dim)
    if store.count() == 0:
        ingest_seed(embedder, store)
    return AskService(Retriever(embedder, store)), store


def main() -> int:
    parser = argparse.ArgumentParser(description="EXCLUSLAWYER Golden Set 回归")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--report", type=Path, default=BASE_DIR / "data" / "golden_report.md")
    args = parser.parse_args()

    svc, store = build_service()
    valid_ids = set(store.payloads) if hasattr(store, "payloads") else set()
    if not valid_ids:
        from scripts.ingest_cn import load_statutes

        valid_ids = {s.id for s in load_statutes(BASE_DIR / "data" / "cn_statutes_sample.json")}

    cases = load_cases(args.golden, FEEDBACK_GOLDEN)
    print(f"加载用例 {len(cases)} 条（含反馈并入）…")

    report = run_regression(svc, cases, valid_ids)
    mode = type(store).__name__
    text = format_report(report, mode=mode)
    args.report.write_text(text, encoding="utf-8")
    print(text)
    print(f"\n报告已写入 {args.report}")
    return 0 if report.thresholds_ok else 1


if __name__ == "__main__":
    sys.exit(main())
