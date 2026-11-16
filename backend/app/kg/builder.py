# -*- coding: utf-8 -*-
"""图谱构建器：产出后端无关的 GraphData（节点 + 边），供内存/Neo4j 两后端消费。

数据来源三路，全部可校验：
1. 大陆法系种子概念/要件/责任方式/期间（规则固定，确定性）
2. 官方法条库（data/official/official_statutes.json）——链接前逐 ID 校验存在，
   缺失只降级跳过并记录 warning，绝不引入幻觉条文（铁律①）
3. 新加坡判例子图种子（data/kg/sg_precedents.json，判例引用经公开来源核实）

跨法域 ANALOGOUS_TO（铁律④）：违约/赔偿/侵权/解除/时效在中日韩的对应条文成组互链。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.kg import schema

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
OFFICIAL_STATUTES = DATA_DIR / "official" / "official_statutes.json"
SG_PRECEDENTS = DATA_DIR / "kg" / "sg_precedents.json"

JUR_NAMES = {"CN": "中国", "JP": "日本", "KR": "韩国", "SG": "新加坡"}


# ---------------------------------------------------------------- GraphData
@dataclass
class GraphNode:
    id: str
    node_type: str
    name: str
    aliases: list[str] = field(default_factory=list)
    props: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    src: str
    dst: str
    relation: str


@dataclass
class GraphData:
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, src: str, dst: str, relation: str) -> None:
        if src not in self.nodes or dst not in self.nodes:
            self.warnings.append(f"跳过悬空边 {src}-[{relation}]->{dst}")
            return
        self.edges.append(GraphEdge(src=src, dst=dst, relation=relation))


# ---------------------------------------------------------------- 大陆法系种子
# 概念/要件/责任方式/期间（名称 + 多语言别名，别名参与问答匹配）
_SEED_NODES: list[tuple[str, str, str, list[str]]] = [
    # 概念
    ("c:breach", "concept", "违约责任", ["債務不履行", "채무불이행", "违约", "契約違反", "계약위반"]),
    ("c:termination", "concept", "合同解除", ["契約解除", "계약해제", "解除合同"]),
    ("c:tort", "concept", "侵权责任", ["不法行為", "불법행위", "侵权"]),
    ("c:injury", "concept", "人身损害赔偿", ["人身伤害赔偿", "損害賠償", "인적 손해배상"]),
    ("c:limitation", "concept", "诉讼时效", ["消滅時效", "소멸시효", "时效", "時効"]),
    ("c:labor", "concept", "劳动经济补偿", ["経済補償", "경제적 보상", "经济补偿", "退職金"]),
    ("c:double_wage", "concept", "二倍工资", ["二倍賃金", "이중임금", "未签劳动合同"]),
    # 构成要件
    ("e:act", "element", "违约行为", ["債務不履行行為", "违约", "不履行"]),
    ("e:damage", "element", "损害后果", ["損害", "손해", "损失"]),
    ("e:causation", "element", "因果关系", ["因果関係", "인과관계"]),
    ("e:fault", "element", "过错", ["故意過失", "과실", "故意或过失"]),
    # 责任方式
    ("d:continue", "duty", "继续履行", ["履行請求", "이행청구"]),
    ("d:remedy", "duty", "采取补救措施", ["追完請求", "补救"]),
    ("d:compensate", "duty", "赔偿损失", ["損害賠償", "손해배상"]),
    ("d:penalty", "duty", "支付违约金", ["違約金", "위약벌", "违约金"]),
    ("d:deposit", "duty", "定金罚则", ["手付", "계약금"]),
    # 期间
    ("p:3y", "period", "三年诉讼时效", ["3年", "三年時効"]),
    ("p:1y", "period", "一年劳动仲裁时效", ["1年", "劳动仲裁"]),
]

_SEED_EDGES: list[tuple[str, str, str]] = [
    ("c:breach", "e:act", schema.REL_CONCEPT_ELEMENT),
    ("c:breach", "e:damage", schema.REL_CONCEPT_ELEMENT),
    ("c:breach", "e:causation", schema.REL_CONCEPT_ELEMENT),
    ("c:breach", "d:continue", schema.REL_CONCEPT_DUTY),
    ("c:breach", "d:remedy", schema.REL_CONCEPT_DUTY),
    ("c:breach", "d:compensate", schema.REL_CONCEPT_DUTY),
    ("c:breach", "d:penalty", schema.REL_CONCEPT_DUTY),
    ("c:tort", "e:fault", schema.REL_CONCEPT_ELEMENT),
    ("c:tort", "e:damage", schema.REL_CONCEPT_ELEMENT),
    ("c:tort", "e:causation", schema.REL_CONCEPT_ELEMENT),
    ("c:injury", "d:compensate", schema.REL_CONCEPT_DUTY),
    ("c:limitation", "p:3y", schema.REL_CONCEPT_PERIOD),
    ("c:labor", "p:1y", schema.REL_CONCEPT_PERIOD),
]

# 概念/要件/责任方式/期间 → 条文（多法域；构建期逐 ID 校验）
_CONCEPT_STATUTES: list[tuple[str, list[str]]] = [
    ("c:breach", ["CN-MINFA-577", "JP-MIN-415", "KR-MIN-390"]),
    ("d:compensate", ["CN-MINFA-584", "JP-MIN-416", "KR-MIN-393"]),
    ("d:penalty", ["CN-MINFA-585"]),
    ("d:deposit", ["CN-MINFA-586"]),
    ("d:continue", ["CN-MINFA-577"]),
    ("d:remedy", ["CN-MINFA-577"]),
    ("c:termination", ["CN-MINFA-563", "JP-MIN-541", "KR-MIN-543"]),
    ("c:limitation", ["CN-MINFA-188", "JP-MIN-166", "KR-MIN-162"]),
    ("p:3y", ["CN-MINFA-188"]),
    ("c:tort", ["CN-MINFA-1165", "JP-MIN-709", "KR-MIN-750"]),
    ("c:injury", ["CN-MINFA-1179", "JP-MIN-716"]),
    ("c:labor", ["CN-LDF-47"]),
    ("c:double_wage", ["CN-LDF-82"]),
]

# 跨法域对应条文组（组内两两 ANALOGOUS_TO；缺失 ID 自动跳过）
ANALOGOUS_GROUPS: list[list[str]] = [
    ["CN-MINFA-577", "JP-MIN-415", "KR-MIN-390"],  # 违约/債務不履行/채무불이행
    ["CN-MINFA-584", "JP-MIN-416", "KR-MIN-393"],  # 损害赔偿范围（可预见性）
    ["CN-MINFA-1165", "JP-MIN-709", "KR-MIN-750"],  # 过错侵权/一般不法行为
    ["CN-MINFA-563", "JP-MIN-541", "KR-MIN-543"],  # 合同解除
    ["CN-MINFA-188", "JP-MIN-166", "KR-MIN-162"],  # 消灭时效
]


# ---------------------------------------------------------------- 匹配打分
def score_match(question: str, node: GraphNode) -> int:
    """问答锚点命中打分：名称/别名整串包含 > 逐字包含；越长越优先。"""
    compact = question.replace("的", "").replace("什么", "")
    best = 0
    for token in [node.name, *node.aliases]:
        if not token:
            continue
        if token in question:
            best = max(best, len(token))
        elif all(ch in compact for ch in token):
            best = max(best, len(token) - 1)
    return best


# ---------------------------------------------------------------- 构建
def load_official_statutes(path: Path | None = None) -> dict[str, dict]:
    """读官方法条库 → {statute_id: {law_title, article_no, text, status, ...}}。"""
    p = path or OFFICIAL_STATUTES
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("statutes", raw.get("items", []))
    return {it["id"]: it for it in items}


def _jurisdiction_of(statute_id: str) -> str:
    return statute_id.split("-", 1)[0] if "-" in statute_id else ""


def _statute_node(statute_id: str, official: dict[str, dict]) -> GraphNode:
    """条文节点：优先用官方法名+条号，缺官源时退回 ID 描述（不编造）。"""
    if statute_id in official:
        it = official[statute_id]
        name = f"{it.get('law_title', statute_id)} {it.get('article_no', '')}".strip()
        props = {
            "jurisdiction": _jurisdiction_of(statute_id) or it.get("jurisdiction", ""),
            "law_title": it.get("law_title", ""),
            "article_no": it.get("article_no", ""),
            "status": it.get("status", "unknown"),
        }
    else:
        name = statute_id
        props = {"jurisdiction": _jurisdiction_of(statute_id)}
    return GraphNode(id=f"s:{statute_id}", node_type="statute", name=name, props=props)


def _load_sg_subgraph(data: GraphData, official: dict[str, dict], path: Path | None = None) -> None:
    """新加坡判例子图（普通法系独立子图）。"""
    p = path or SG_PRECEDENTS
    if not p.exists():
        data.warnings.append(f"判例种子缺失：{p}")
        return
    seed = json.loads(p.read_text(encoding="utf-8"))

    for pr in seed.get("principles", []):
        data.add_node(
            GraphNode(
                id=pr["id"],
                node_type="principle",
                name=pr["name"],
                aliases=pr.get("aliases", []),
                props={"summary": pr.get("summary", ""), "jurisdiction": "SG"},
            )
        )
        for sid in pr.get("statute_ids", []):
            sid_full = f"s:{sid}"
            if sid_full not in data.nodes:
                if sid in official:
                    data.add_node(_statute_node(sid, official))
                else:
                    data.warnings.append(f"判例种子引用了官源不存在的条文 {sid}，已跳过")
                    continue
            data.add_edge(pr["id"], sid_full, schema.REL_BASIS)

    for case in seed.get("precedents", []):
        data.add_node(
            GraphNode(
                id=case["id"],
                node_type="precedent",
                name=case["name"],
                aliases=case.get("aliases", []),
                props={
                    "citation": case.get("citation", ""),
                    "court": case.get("court", ""),
                    "year": case.get("year"),
                    "holding": case.get("holding", ""),
                    "jurisdiction": "SG",
                },
            )
        )
        for pid in case.get("principle_ids", []):
            if pid in data.nodes:
                data.add_edge(case["id"], pid, schema.REL_ESTABLISHES)
            else:
                data.warnings.append(f"判例 {case['id']} 引用未知规则 {pid}")
        follows = case.get("follows")
        if follows:
            if follows in data.nodes:
                data.add_edge(case["id"], follows, schema.REL_FOLLOWS)
            else:
                data.warnings.append(f"判例 {case['id']} 引用未知前例 {follows}")


def build_graph_data(
    official: dict[str, dict] | None = None,
    *,
    include_sg: bool = True,
    sg_path: Path | None = None,
) -> GraphData:
    """构建完整图谱数据（大陆法系 + 可选 SG 判例子图）。

    official：{statute_id: 来源条目}；传 None 时尝试读官方库文件，读不到则
    条文节点退化为裸 ID（warning 记录），保证离线可构建。
    """
    data = GraphData()
    if official is None:
        official = load_official_statutes()
        if not official:
            data.warnings.append("官方法条库缺失/为空，条文节点将只含 ID")

    # 1. 种子节点
    for nid, ntype, name, aliases in _SEED_NODES:
        data.add_node(GraphNode(id=nid, node_type=ntype, name=name, aliases=aliases))
    # 2. 种子边
    for src, dst, rel in _SEED_EDGES:
        data.add_edge(src, dst, rel)
    # 3. 条文节点 + 链接（逐 ID 校验）
    for anchor, statute_ids in _CONCEPT_STATUTES:
        for sid in statute_ids:
            full = f"s:{sid}"
            if full not in data.nodes:
                if sid in official:
                    data.add_node(_statute_node(sid, official))
                else:
                    data.warnings.append(f"条文 {sid} 不在官方法条库，跳过链接（{anchor}）")
                    continue
            data.add_edge(anchor, full, schema.REL_BASIS)
    # 4. 跨法域对应（组内两两互链）
    for group in ANALOGOUS_GROUPS:
        present = [sid for sid in group if f"s:{sid}" in data.nodes]
        missing = [sid for sid in group if f"s:{sid}" not in data.nodes]
        for sid in missing:
            data.warnings.append(f"跨法域对应组缺失 {sid}，组内剩余继续互链")
        for i, a in enumerate(present):
            for b in present[i + 1 :]:
                data.add_edge(f"s:{a}", f"s:{b}", schema.REL_ANALOGOUS)
    # 5. SG 判例子图
    if include_sg:
        _load_sg_subgraph(data, official, sg_path)
    return data
