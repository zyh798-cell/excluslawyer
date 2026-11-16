# -*- coding: utf-8 -*-
"""P2-10 法律知识图谱：概念/构成要件/责任方式/条文/判例的多跳问答。

后端可插拔：默认内存图（开箱即用）；配置 NEO4J_URI 且可连通时自动切换
Neo4j 生产后端（空库自动灌入种子，见 app/kg/）。

schema 分两套：大陆法系（构成要件→责任方式→成文法条文，中/日/韩复用，
条文间 ANALOGOUS_TO 跨法域对应）+ 普通法系判例子图（新加坡：判例→裁判规则）。

多跳问答：问题 → 节点命中 → 展开 1-2 跳 → 按节点类型组织答案 + 挂法条 +
跨法域对应条文 + 判例要旨。只做结构化展开，不生成自由法律结论。
"""

from __future__ import annotations

import logging

from app.config import settings
from app.kg.backends import ExpandStep, MemoryGraph
from app.kg.builder import GraphData, build_graph_data
from app.kg.neo4j_backend import Neo4jGraphBackend
from app.models.schemas import KgNode, KgPath, KgQueryResponse

logger = logging.getLogger(__name__)

# 兼容旧名字（历史代码从本模块 import GraphBackend）
GraphBackend = MemoryGraph

# 节点类型 → 答案分组标签
_TYPE_LABEL = {
    "concept": "关联概念",
    "element": "构成要件",
    "duty": "责任方式/法律后果",
    "period": "期间",
    "statute": "依据条文",
    "precedent": "判例",
    "principle": "裁判规则",
    "court": "审理法院",
}

_JUR_NAMES = {"CN": "中国", "JP": "日本", "KR": "韩国", "SG": "新加坡"}


def build_legal_kg(data: GraphData | None = None) -> MemoryGraph:
    """构建内存图（大陆法系种子 + 官源条文链接 + SG 判例子图）。"""
    return MemoryGraph(data or build_graph_data())


def _try_neo4j_graph() -> Neo4jGraphBackend | None:
    """连得上 Neo4j 就用生产后端（空库自动灌种子），失败静默回退。"""
    if not settings.neo4j_uri:
        return None
    try:
        g = Neo4jGraphBackend.connect(
            settings.neo4j_uri,
            settings.neo4j_user,
            settings.neo4j_password,
            timeout=2.0,
        )
        st = g.stats()
        if not st.get("nodes"):
            logger.info("Neo4j 空库，灌入图谱种子")
            g.ingest(build_graph_data())
        return g
    except Exception as exc:  # noqa: BLE001 —— Neo4j 不可用不算错误，回退内存
        logger.debug("Neo4j 不可用，使用内存图：%s", exc)
        return None


_CACHED_GRAPH: MemoryGraph | Neo4jGraphBackend | None = None


def get_default_graph() -> MemoryGraph | Neo4jGraphBackend:
    global _CACHED_GRAPH
    if _CACHED_GRAPH is None:
        _CACHED_GRAPH = _try_neo4j_graph() or build_legal_kg()
    return _CACHED_GRAPH


class KgService:
    def __init__(self, graph=None):
        self.graph = graph or get_default_graph()

    # ---------------- 多跳展开 → 分组答案 ----------------
    def query(self, question: str) -> KgQueryResponse:
        start = self.graph.match_anchor(question)
        if start is None:
            return KgQueryResponse(
                question=question,
                answer=(
                    "知识图谱中未命中对应概念（当前覆盖：违约责任/合同解除/侵权责任/人身损害赔偿/"
                    "诉讼时效/劳动经济补偿/二倍工资，以及新加坡判例子图）。"
                    "换个法律术语试试，如“违约责任的构成要件”。"
                ),
                backend=getattr(self.graph, "backend_name", "memory"),
            )

        steps: list[ExpandStep] = self.graph.expand(start.id, hops=2)

        grouped: dict[str, list[str]] = {t: [] for t in _TYPE_LABEL}
        statute_ids: list[str] = []
        statutes_by_jur: dict[str, list[str]] = {}
        case_lines: list[str] = []
        principle_lines: list[str] = []
        seen_nodes: set[str] = set()

        def _collect(node, *, into_group: bool = True) -> None:
            if node.id in seen_nodes:
                return
            seen_nodes.add(node.id)
            if into_group:
                grouped.setdefault(node.node_type, []).append(node.name)
            if node.node_type == "statute":
                sid = node.id.replace("s:", "")
                statute_ids.append(sid)
                jur = (node.props.get("jurisdiction") or sid.split("-", 1)[0] or "?").upper()
                statutes_by_jur.setdefault(jur, []).append(sid)
            elif node.node_type == "precedent":
                cite = node.props.get("citation", "")
                case_lines.append(f"{node.name} {cite}".strip())
                holding = node.props.get("holding", "")
                if holding:
                    case_lines.append(f"  要旨：{holding}")
            elif node.node_type == "principle":
                summary = node.props.get("summary", "")
                principle_lines.append(f"{node.name}——{summary}" if summary else node.name)

        _collect(start, into_group=False)  # 锚点自身的判例/规则/条文详情也要收
        for step in steps:
            _collect(step.a)
            _collect(step.b)

        statute_ids = list(dict.fromkeys(statute_ids))
        relations_used = list(dict.fromkeys(s.relation for s in steps))

        lines = [f"【{start.name}】知识图谱展开（{len(steps)} 条关系路径）："]
        for node_type, label in _TYPE_LABEL.items():
            names = list(dict.fromkeys(grouped.get(node_type, [])))
            if names and node_type not in ("statute", "precedent", "principle"):
                lines.append(f"· {label}：{'、'.join(names)}")
        if statute_ids:
            lines.append(f"· 依据条文：{'、'.join(statute_ids)}")
        # 跨法域对应（铁律④）：同组条文出现 2 个以上法域时列对照
        if len(statutes_by_jur) >= 2:
            parts = [
                f"{_JUR_NAMES.get(jur, jur)}：{'、'.join(ids)}"
                for jur, ids in statutes_by_jur.items()
            ]
            lines.append(f"· 跨法域对应条文：{'；'.join(parts)}")
        if principle_lines:
            for pl in principle_lines:
                lines.append(f"· 裁判规则：{pl}")
        if case_lines:
            for cl in case_lines:
                lines.append(f"· {cl}" if not cl.startswith("  ") else cl)
        lines.append("（图谱仅做结构化展开，构成要件是否齐备须结合个案证据判断。）")

        return KgQueryResponse(
            question=question,
            matched_node=KgNode(id=start.id, node_type=start.node_type, name=start.name),
            paths=[
                KgPath(
                    nodes=[
                        KgNode(id=s.a.id, node_type=s.a.node_type, name=s.a.name),
                        KgNode(id=s.b.id, node_type=s.b.node_type, name=s.b.name),
                    ],
                    relations=[s.relation],
                )
                for s in steps
            ],
            answer="\n".join(lines),
            statute_ids=statute_ids,
            related_cases=list(dict.fromkeys(case_lines)),
            backend=getattr(self.graph, "backend_name", "memory"),
        )
