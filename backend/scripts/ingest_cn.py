"""法条入库脚本：JSON（含多法域字段）→ 向量化 → 写入向量库。

用法（在 backend/ 目录下）：
    python scripts/ingest_cn.py                       # 灌入种子数据
    python scripts/ingest_cn.py --input data/xxx.json # 灌入指定文件
    python scripts/ingest_cn.py --jurisdiction JP     # 多法域数据复用同一 schema

数据规范：每条记录必须含 jurisdiction / language / effective_date / amended_history / status。
正式数据从官方法规源抓取（CN: flk.npc.gov.cn / JP: e-Gov / KR: law.go.kr / SG: sso.agc.gov.sg），
严禁商业法规库；裁判文书入库前做隐私脱敏。
"""

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))  # 允许直接 python scripts/ingest_cn.py 运行

from app.models.schemas import Statute  # noqa: E402

DEFAULT_SEED = BASE_DIR / "data" / "cn_statutes_sample.json"


def load_statutes(path: Path) -> list[Statute]:
    blob = json.loads(path.read_text(encoding="utf-8"))
    raw = blob["statutes"] if isinstance(blob, dict) else blob
    return [Statute(**item) for item in raw]


def statutes_to_rows(statutes: list[Statute]) -> tuple[list[str], list[dict]]:
    """展开成向量库三元组：ids / payloads（原文+元数据）。"""
    ids, payloads = [], []
    for s in statutes:
        ids.append(s.id)
        payloads.append(
            {
                "law_title": s.law_title,
                "law_level": s.law_level,
                "article_no": s.article_no,
                "text": s.text,
                "gloss": s.gloss,
                "jurisdiction": s.jurisdiction,
                "language": s.language,
                "effective_date": s.effective_date,
                "expiry_date": s.expiry_date,
                "amended_history": s.amended_history,
                "revisions": s.revisions,
                "status": s.status,
                "source_url": s.source_url,
                "topics": s.topics,
            }
        )
    return ids, payloads


def ingest_seed(embedder, store, path: Path = DEFAULT_SEED) -> int:
    """灌入种子数据（供 FastAPI 启动时 AUTO_INGEST 调用）。"""
    statutes = load_statutes(path)
    return ingest_statutes(statutes, embedder, store)


def ingest_statutes(statutes: list[Statute], embedder, store) -> int:
    ids, payloads = statutes_to_rows(statutes)
    # 向量化的文本 = 条文号 + 原文 + 主题，提高召回
    texts = [
        f"{p['law_title']} {p['article_no']} {p['text']} {' '.join(p['topics'])}"
        for p in payloads
    ]
    vectors = embedder.embed(texts)
    store.upsert(ids, vectors, payloads)
    store.flush()
    return len(ids)


def main() -> None:
    parser = argparse.ArgumentParser(description="EXCLUSLAWYER 法条入库")
    parser.add_argument("--input", type=Path, default=DEFAULT_SEED, help="法条 JSON 文件")
    parser.add_argument("--jurisdiction", default=None, help="仅灌入指定法域（过滤用）")
    args = parser.parse_args()

    from app.rag.embedder import get_embedder
    from app.rag.vector_store import get_vector_store

    embedder = get_embedder()
    store = get_vector_store(embedder.dim)

    statutes = load_statutes(args.input)
    if args.jurisdiction:
        statutes = [s for s in statutes if s.jurisdiction == args.jurisdiction.upper()]

    n = ingest_statutes(statutes, embedder, store)
    print(f"ingested={n}  collection_total={store.count()}  embedder={type(embedder).__name__}")


if __name__ == "__main__":
    main()
