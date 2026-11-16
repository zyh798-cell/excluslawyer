"""知识图谱测试：builder 校验、内存多跳、跨法域对应、SG 判例子图、Neo4j 后端映射。"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.kg.backends import MemoryGraph
from app.kg.builder import build_graph_data, load_official_statutes
from app.kg.neo4j_backend import Neo4jGraphBackend
from app.services.kg_service import KgService


def _service() -> KgService:
    return KgService(graph=MemoryGraph(build_graph_data()))


# ---------------- builder：官源校验 ----------------


def test_builder_links_official_statutes():
    official = load_official_statutes()
    assert official, "官方法条库应存在（迭代 3 产出）"
    data = build_graph_data(official)
    # 核心链接全部落在官源存在的条文上
    for sid in ("CN-MINFA-577", "JP-MIN-415", "KR-MIN-390"):
        node = data.nodes.get(f"s:{sid}")
        assert node is not None, f"{sid} 应建节点"
        assert node.props.get("law_title"), f"{sid} 应带官方法名"
    # 无悬空边
    assert all(e.src in data.nodes and e.dst in data.nodes for e in data.edges)
    # 跨法域对应边（铁律④）
    rels = {(e.src, e.dst, e.relation) for e in data.edges}
    assert ("s:CN-MINFA-577", "s:JP-MIN-415", "ANALOGOUS_TO") in rels
    assert ("s:CN-MINFA-577", "s:KR-MIN-390", "ANALOGOUS_TO") in rels


def test_builder_skips_missing_statutes_without_hallucinating():
    """官源缺失的条文 ID 必须跳过并告警，不许建幻觉节点（铁律①）。"""
    data = build_graph_data({})
    assert data.warnings, "缺失条文应记录 warning"
    assert not any(n.node_type == "statute" for n in data.nodes.values())
    assert all(e.src in data.nodes and e.dst in data.nodes for e in data.edges)


# ---------------- 内存多跳问答 ----------------


def test_kg_breach_elements_compat():
    """test_p2 同口径：违约责任要件展开必须带构成要件与依据条文。"""
    resp = _service().query("违约责任的构成要件是什么")
    assert resp.matched_node and resp.matched_node.name == "违约责任"
    assert "违约行为" in resp.answer and "损害后果" in resp.answer
    assert resp.statute_ids
    assert resp.backend == "memory"


def test_kg_cross_jurisdiction_analogous():
    """铁律④：违约责任展开应带中日韩对应条文对照。"""
    resp = _service().query("违约责任")
    for sid in ("CN-MINFA-577", "JP-MIN-415", "KR-MIN-390"):
        assert sid in resp.statute_ids, f"缺跨法域对应 {sid}"
    assert "跨法域对应条文" in resp.answer
    assert "日本" in resp.answer and "韩国" in resp.answer


def test_kg_japanese_alias_query():
    """日文别名命中中文概念（多语言锚点）。"""
    resp = _service().query("債務不履行の要件")
    assert resp.matched_node and resp.matched_node.name == "违约责任"
    assert "JP-MIN-415" in resp.statute_ids


def test_kg_memory_expand_two_hops():
    g = MemoryGraph(build_graph_data())
    # 概念锚点 2 跳：要件/责任/条文
    steps = g.expand("c:breach", hops=2)
    rels = {s.relation for s in steps}
    assert "构成要件" in rels and "依据条文" in rels
    ids = {s.b.id for s in steps} | {s.a.id for s in steps}
    assert "s:JP-MIN-415" in ids
    # 条文锚点 1 跳：跨法域对应边（ANALOGOUS_TO）
    steps2 = g.expand("s:CN-MINFA-584", hops=1)
    assert "ANALOGOUS_TO" in {s.relation for s in steps2}
    assert {"s:JP-MIN-416", "s:KR-MIN-393"} <= {s.b.id for s in steps2}


# ---------------- SG 判例子图（普通法系） ----------------


def test_kg_sg_precedent_subgraph():
    resp = _service().query("Chwee Kin Keong 标价错误")
    assert resp.matched_node and resp.matched_node.node_type == "precedent"
    assert any("Chwee Kin Keong" in c for c in resp.related_cases)
    assert "[2005] SGCA 2" in resp.answer, "判例引用必须可溯源"
    assert "裁判规则" in resp.answer or "单方错误" in resp.answer


def test_kg_sg_statutory_principle_cites_act():
    """SG 成文规则节点必须挂到官源条文（Contracts (Rights of Third Parties) Act）。"""
    resp = _service().query("第三方合同权利")
    assert resp.matched_node and resp.matched_node.node_type == "principle"
    assert "SG-CRTP-1" in resp.statute_ids


def test_kg_sg_follows_relation():
    data = build_graph_data()
    rels = {(e.src, e.dst, e.relation) for e in data.edges}
    assert ("SG-CASE-SEETOH-2013", "SG-CASE-SPANDECK-2007", "FOLLOWS") in rels


# ---------------- Neo4j 后端（FakeDriver 映射测试） ----------------


class FakeDriver:
    """脚本化 driver：按 Cypher 形状返回预置行，记录全部调用。"""

    def __init__(self, handlers=None):
        self.calls: list[tuple[str, dict]] = []
        self.handlers = handlers or []

    def execute_query(self, cypher, parameters_=None, database_=None, **kw):
        params = parameters_ or {}
        self.calls.append((cypher, params))
        for pred, rows in self.handlers:
            if pred(cypher, params):
                return (rows, None, [])
        return ([], None, [])

    def close(self):
        pass


def test_neo4j_ingest_batches():
    driver = FakeDriver()
    g = Neo4jGraphBackend(driver)
    fake_official = {
        "CN-MINFA-577": {"law_title": "民法典", "article_no": "第五百七十七条"},
        "JP-MIN-415": {"law_title": "民法", "article_no": "第四百十五条"},
        "KR-MIN-390": {"law_title": "민법", "article_no": "제390조"},
    }
    data = build_graph_data(fake_official)
    result = g.ingest(data)
    assert result["nodes"] == len(data.nodes)
    assert result["edges"] == len(data.edges)
    cyphers = [c for c, _ in driver.calls]
    assert any("MERGE (n:`Concept`" in c for c in cyphers)
    assert any("MERGE (n:`Precedent`" in c for c in cyphers), "SG 判例子图应入库"
    assert any("MERGE (a)-[:`ANALOGOUS_TO`]->(b)" in c for c in cyphers)
    # 幂等 MERGE 语句，不应出现 CREATE
    assert not any(" CREATE " in c for c in cyphers)


def test_neo4j_match_anchor_scoring_consistent_with_memory():
    """Neo4j 返回候选行后，打分逻辑与内存后端一致。"""
    rows = [
        {"node": {"id": "e:act", "node_type": "element", "name": "违约行为", "aliases": ["不履行"]}},
        {"node": {"id": "c:breach", "node_type": "concept", "name": "违约责任", "aliases": ["违约"]}},
    ]
    driver = FakeDriver(
        handlers=[
            (lambda c, p: "node_type <> 'statute'" in c, rows),
        ]
    )
    g = Neo4jGraphBackend(driver)
    hit = g.match_anchor("违约责任的构成要件")
    assert hit is not None and hit.id == "c:breach"


def test_neo4j_expand_maps_paths_and_dedupes():
    path_rows = [
        {
            "ns": [
                {"id": "c:breach", "node_type": "concept", "name": "违约责任", "aliases": []},
                {"id": "e:act", "node_type": "element", "name": "违约行为", "aliases": []},
            ],
            "rels": ["构成要件"],
        },
        {
            "ns": [
                {"id": "c:breach", "node_type": "concept", "name": "违约责任", "aliases": []},
                {"id": "e:act", "node_type": "element", "name": "违约行为", "aliases": []},
            ],
            "rels": ["构成要件"],  # 重复路径 → 应去重
        },
        {
            "ns": [
                {"id": "c:breach", "node_type": "concept", "name": "违约责任", "aliases": []},
                {"id": "s:CN-MINFA-577", "node_type": "statute", "name": "民法典 第五百七十七条", "aliases": [], "jurisdiction": "CN"},
            ],
            "rels": ["依据条文"],
        },
    ]
    driver = FakeDriver(handlers=[(lambda c, p: "relationships(p)" in c, path_rows)])
    g = Neo4jGraphBackend(driver)
    steps = g.expand("c:breach", hops=2)
    assert len(steps) == 2, f"重复路径应去重，实际 {len(steps)}"
    assert {s.relation for s in steps} == {"构成要件", "依据条文"}
    assert {s.b.id for s in steps} == {"e:act", "s:CN-MINFA-577"}
    # props 与核心字段正确分离
    statute_step = next(s for s in steps if s.b.node_type == "statute")
    assert statute_step.b.props.get("jurisdiction") == "CN"
