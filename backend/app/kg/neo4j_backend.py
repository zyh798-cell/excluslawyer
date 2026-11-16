# -*- coding: utf-8 -*-
"""Neo4j 生产后端（Cypher 实现，与 MemoryGraph 同接口）。

- 驱动可注入（测试用 FakeDriver；生产用 neo4j.GraphDatabase.driver）
- 固定 Cypher 集：init_schema / ingest / match_anchor / expand / clear / stats
- match_anchor 的打分逻辑与内存后端共用 builder.score_match，两后端行为一致
"""

from __future__ import annotations

import logging

from app.kg import schema
from app.kg.builder import GraphData, GraphNode, score_match
from app.kg.backends import ExpandStep

logger = logging.getLogger(__name__)

_CORE_KEYS = {"id", "node_type", "name", "aliases"}


def _to_graph_node(record_node: dict) -> GraphNode:
    props = {k: v for k, v in record_node.items() if k not in _CORE_KEYS}
    return GraphNode(
        id=record_node.get("id", ""),
        node_type=record_node.get("node_type", ""),
        name=record_node.get("name", ""),
        aliases=list(record_node.get("aliases") or []),
        props=props,
    )


class Neo4jGraphBackend:
    backend_name = "neo4j"

    def __init__(self, driver, database: str = "neo4j"):
        self.driver = driver
        self.database = database

    # ---------------- 连接 ----------------
    @classmethod
    def connect(cls, uri: str, user: str, password: str, *, timeout: float = 3.0, database: str = "neo4j"):
        """建连并 ping；失败抛 ConnectionError（调用方回退内存图）。"""
        from neo4j import GraphDatabase  # 惰性导入，离线环境不阻断内存模式

        driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=timeout)
        backend = cls(driver, database=database)
        backend.driver.verify_connectivity()
        return backend

    def close(self) -> None:
        try:
            self.driver.close()
        except Exception:  # noqa: BLE001
            pass

    # ---------------- 底层 ----------------
    def _run(self, cypher: str, params: dict | None = None) -> list[dict]:
        records, _summary, _keys = self.driver.execute_query(
            cypher, parameters_=params or {}, database_=self.database
        )
        out = []
        for r in records:
            out.append(dict(r) if not isinstance(r, dict) else r)
        return out

    # ---------------- schema / 入库 ----------------
    def init_schema(self) -> None:
        for cypher in schema.CONSTRAINT_CYPHERS:
            self._run(cypher)

    def clear(self) -> None:
        self._run("MATCH (n) DETACH DELETE n")

    def ingest(self, data: GraphData) -> dict:
        """按 label 分批 MERGE 节点、按关系类型 MERGE 边（幂等可重跑）。"""
        by_label: dict[str, list[dict]] = {}
        for node in data.nodes.values():
            label = schema.NODE_LABELS.get(node.node_type)
            if not label:
                data.warnings.append(f"未知节点类型 {node.node_type}（{node.id}），跳过")
                continue
            by_label.setdefault(label, []).append(
                {
                    "id": node.id,
                    "node_type": node.node_type,
                    "name": node.name,
                    "aliases": node.aliases,
                    "props": node.props,
                }
            )
        n_nodes = 0
        for label, rows in by_label.items():
            self._run(
                f"UNWIND $rows AS row "
                f"MERGE (n:`{label}` {{id: row.id}}) "
                f"SET n.node_type = row.node_type, n.name = row.name, "
                f"    n.aliases = coalesce(row.aliases, []), n += row.props",
                {"rows": rows},
            )
            n_nodes += len(rows)

        by_rel: dict[str, list[dict]] = {}
        for e in data.edges:
            by_rel.setdefault(e.relation, []).append({"src": e.src, "dst": e.dst})
        n_edges = 0
        for rel, rows in by_rel.items():
            self._run(
                f"UNWIND $rows AS row "
                f"MATCH (a {{id: row.src}}), (b {{id: row.dst}}) "
                f"MERGE (a)-[:`{rel}`]->(b)",
                {"rows": rows},
            )
            n_edges += len(rows)
        return {"nodes": n_nodes, "edges": n_edges}

    # ---------------- 查询 ----------------
    def match_anchor(self, question: str) -> GraphNode | None:
        # 锚点候选全量（概念/要件/责任/期间/判例/规则，量级小）+ 名称被问题包含的条文
        rows = self._run("MATCH (n) WHERE n.node_type <> 'statute' RETURN n AS node")
        rows += self._run(
            "MATCH (s:Statute) WHERE $q CONTAINS s.name RETURN s AS node",
            {"q": question},
        )
        best: tuple[int, GraphNode] | None = None
        for row in rows:
            raw = row.get("node")
            if raw is None:
                continue
            node = _to_graph_node(dict(raw))
            score = score_match(question, node)
            if score > 0 and (best is None or score > best[0]):
                best = (score, node)
        return best[1] if best else None

    def expand(self, node_id: str, hops: int = 2) -> list[ExpandStep]:
        rows = self._run(
            "MATCH p = (a {id: $id})-[*1..%d]-(x) "
            "RETURN nodes(p) AS ns, [r IN relationships(p) | type(r)] AS rels" % int(hops),
            {"id": node_id},
        )
        steps: list[ExpandStep] = []
        seen: set[tuple[str, str, str]] = set()
        # 短路径优先（贴近内存 BFS 的先发现语义）
        for row in sorted(rows, key=lambda r: len(r.get("ns") or [])):
            ns = [dict(n) for n in (row.get("ns") or [])]
            rels = row.get("rels") or []
            for i in range(len(rels)):
                a = _to_graph_node(ns[i])
                b = _to_graph_node(ns[i + 1])
                rel = rels[i]
                key = (a.id, b.id, rel)
                key_rev = (b.id, a.id, rel)
                if key in seen or key_rev in seen:
                    continue
                seen.add(key)
                steps.append(ExpandStep(a=a, b=b, relation=rel))
        return steps

    def neighbors(self, node_id: str) -> list[tuple[str, str, str]]:
        rows = self._run(
            "MATCH (a {id: $id})-[r]-(b) RETURN b AS node, type(r) AS rel",
            {"id": node_id},
        )
        out = []
        for row in rows:
            node = _to_graph_node(dict(row["node"]))
            out.append((node_id, node.id, row.get("rel", "")))
        return out

    def stats(self) -> dict:
        row = self._run(
            "MATCH (n) RETURN count(n) AS nodes, "
            "count { MATCH ()-[r]->() RETURN count(r) } AS edges"
        )
        # 老内核不支持 count{} 子查询时的回退
        if row and (row[0].get("nodes") is None):
            row = []
        if not row:
            n = self._run("MATCH (n) RETURN count(n) AS nodes")[0]["nodes"]
            e = self._run("MATCH ()-[r]->() RETURN count(r) AS edges")[0]["edges"]
        else:
            n, e = row[0]["nodes"], row[0]["edges"]
        by_type_rows = self._run(
            "MATCH (n) WHERE n.node_type IS NOT NULL "
            "RETURN n.node_type AS t, count(*) AS c"
        )
        return {
            "backend": self.backend_name,
            "nodes": n,
            "edges": e,
            "by_type": {r["t"]: r["c"] for r in by_type_rows},
            "warnings": [],
        }
