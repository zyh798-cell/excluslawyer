# -*- coding: utf-8 -*-
"""图后端：内存实现（开箱即用/测试）。

统一接口（Neo4jGraphBackend 同款）：
- match_anchor(question) -> GraphNode | None   问答锚点命中
- expand(node_id, hops)  -> list[ExpandStep]   多跳展开
- nodes/edges 视图（内存实现直接持有）
"""

from __future__ import annotations

from dataclasses import dataclass

from app.kg.builder import GraphData, GraphNode, score_match


@dataclass
class ExpandStep:
    """一条关系路径（本次展开新增的两节点一关系）。"""

    a: GraphNode
    b: GraphNode
    relation: str


class MemoryGraph:
    """内存图后端：构建期的 GraphData 直接驻留，BFS 多跳。"""

    backend_name = "memory"

    def __init__(self, data: GraphData):
        self.data = data

    @property
    def nodes(self) -> dict[str, GraphNode]:
        return self.data.nodes

    @property
    def edges(self):
        return self.data.edges

    def neighbors(self, node_id: str) -> list[tuple[str, str, str]]:
        """(src, dst, relation) 视角的无向邻居（兼容旧接口）。"""
        out = [(e.src, e.dst, e.relation) for e in self.data.edges if e.src == node_id]
        out += [(e.dst, e.src, e.relation) for e in self.data.edges if e.dst == node_id]
        return out

    def match_anchor(self, question: str) -> GraphNode | None:
        best: tuple[int, GraphNode] | None = None
        for node in self.data.nodes.values():
            score = score_match(question, node)
            if score > 0 and (best is None or score > best[0]):
                best = (score, node)
        return best[1] if best else None

    def expand(self, node_id: str, hops: int = 2) -> list[ExpandStep]:
        if node_id not in self.data.nodes:
            return []
        steps: list[ExpandStep] = []
        visited = {node_id}
        frontier = [node_id]
        for _hop in range(hops):
            nxt: list[str] = []
            for nid in frontier:
                for src, dst, rel in self.neighbors(nid):
                    other = dst if src == nid else src
                    if other in visited:
                        continue
                    visited.add(other)
                    nxt.append(other)
                    steps.append(
                        ExpandStep(
                            a=self.data.nodes[nid],
                            b=self.data.nodes[other],
                            relation=rel,
                        )
                    )
            frontier = nxt
        return steps

    def stats(self) -> dict:
        from collections import Counter

        return {
            "backend": self.backend_name,
            "nodes": len(self.data.nodes),
            "edges": len(self.data.edges),
            "by_type": dict(Counter(n.node_type for n in self.data.nodes.values())),
            "warnings": list(self.data.warnings),
        }
