# -*- coding: utf-8 -*-
"""知识图谱构建 CLI：校验 → 快照 → （可选）灌 Neo4j。

用法：
  python scripts/build_kg.py                     # 构建 + 校验 + 落快照 data/kg/kg_snapshot.json
  python scripts/build_kg.py --neo4j             # 额外灌入 Neo4j（NEO4J_URI/USER/PASSWORD 可环境变量覆盖）
  python scripts/build_kg.py --no-sg             # 只建大陆法系子图
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from app.kg.builder import build_graph_data, load_official_statutes


def main() -> int:
    ap = argparse.ArgumentParser(description="构建法律知识图谱")
    ap.add_argument("--neo4j", action="store_true", help="灌入 Neo4j（默认 bolt://localhost:7687）")
    ap.add_argument("--uri", default=None, help="Neo4j URI（覆盖 settings）")
    ap.add_argument("--user", default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--no-sg", action="store_true", help="不含新加坡判例子图")
    ap.add_argument("--clear", action="store_true", help="灌库前先清空 Neo4j")
    args = ap.parse_args()

    official = load_official_statutes()
    print(f"官方法条库：{len(official)} 条")
    data = build_graph_data(official, include_sg=not args.no_sg)

    print(f"图谱：{len(data.nodes)} 节点 / {len(data.edges)} 边")
    from collections import Counter

    print("节点类型分布：", dict(Counter(n.node_type for n in data.nodes.values())))
    print("关系类型分布：", dict(Counter(e.relation for e in data.edges)))

    if data.warnings:
        print(f"\n[warning] {len(data.warnings)} 条（条文缺失/悬空引用已自动跳过）：")
        for w in data.warnings[:20]:
            print("  -", w)

    # 悬空校验（add_edge 已拦，这里兜底再查一次）
    dangling = [e for e in data.edges if e.src not in data.nodes or e.dst not in data.nodes]
    assert not dangling, f"存在悬空边：{dangling[:5]}"

    snap = BASE_DIR / "data" / "kg" / "kg_snapshot.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(
        json.dumps(
            {
                "nodes": [asdict(n) for n in data.nodes.values()],
                "edges": [asdict(e) for e in data.edges],
                "warnings": data.warnings,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\n快照已写入 {snap}")

    if args.neo4j:
        from app.kg.neo4j_backend import Neo4jGraphBackend

        uri = args.uri or settings.neo4j_uri
        user = args.user or settings.neo4j_user
        password = args.password or settings.neo4j_password
        print(f"连接 Neo4j：{uri} ...")
        g = Neo4jGraphBackend.connect(uri, user, password, timeout=5.0)
        g.init_schema()
        if args.clear:
            g.clear()
            print("已清空图库")
        result = g.ingest(data)
        print(f"入库完成：{result}")
        print("统计：", g.stats())
        g.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
