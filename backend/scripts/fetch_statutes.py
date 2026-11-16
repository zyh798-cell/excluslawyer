# -*- coding: utf-8 -*-
"""官方法规源数据管道 CLI。

用法（backend/ 目录下）：
    python scripts/fetch_statutes.py                      # 四法域核心法律
    python scripts/fetch_statutes.py --jur CN JP          # 仅中国+日本
    python scripts/fetch_statutes.py --ingest             # 抓完后灌入向量库（hash 兜底）
产出：
    data/official/{JUR}_{source_id}.json   单法条文级明细
    data/official/official_statutes.json   合并 Statute 列表
    data/official/PIPELINE_REPORT.md       质量报告
"""
import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.data_pipeline.pipeline import DATA_DIR, run  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="官方源法规抓取管线")
    ap.add_argument("--jur", nargs="*", default=None, help="法域子集：CN JP KR SG")
    ap.add_argument("--sleep", type=float, default=1.5, help="请求间隔秒（限速）")
    ap.add_argument("--ingest", action="store_true", help="抓取后灌入向量库")
    args = ap.parse_args()

    report = run(jurisdictions=args.jur, sleep_s=args.sleep)

    ok = sum(1 for r in report["laws"] if r.get("ok"))
    fail = [r for r in report["laws"] if not r.get("ok")]
    print(f"\n抓取成功 {ok}/{len(report['laws'])}")
    if fail:
        print("失败：", [f["title"] for f in fail])

    if args.ingest:
        from app.rag.embedder import HashingEmbedder
        from app.rag.retriever import Retriever
        from app.rag.vector_store import NumpyVectorStore
        from app.models.schemas import Statute
        from scripts.ingest_cn import ingest_statutes

        raw = json.loads((DATA_DIR / "official_statutes.json").read_text(encoding="utf-8"))
        statutes = [Statute(**item) for item in raw]
        store = NumpyVectorStore(path=BASE_DIR / "data" / "vector_official.pkl")
        n = ingest_statutes(statutes, HashingEmbedder(), store)
        store.flush()
        print(f"入库 {n} 条 → data/vector_official.pkl")

    # 门禁：核心法域不允许全挂
    if ok == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
