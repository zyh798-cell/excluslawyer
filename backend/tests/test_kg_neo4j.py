"""Neo4j 真库集成测试（默认跳过）。

开启方法（本地或 CI 有 Neo4j 时）：
    docker compose up -d neo4j
    set KG_NEO4J_URI=bolt://localhost:7687   # 或 export
    pytest tests/test_kg_neo4j.py -v
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import pytest

from app.kg.backends import MemoryGraph
from app.kg.builder import build_graph_data, load_official_statutes
from app.kg.neo4j_backend import Neo4jGraphBackend
from app.services.kg_service import KgService

NEO4J_URI = os.environ.get("KG_NEO4J_URI", "")

pytestmark = pytest.mark.skipif(
    not NEO4J_URI, reason="未设置 KG_NEO4J_URI（docker compose up -d neo4j 后开启）"
)


@pytest.fixture(scope="module")
def neo4j_graph():
    g = Neo4jGraphBackend.connect(
        NEO4J_URI,
        os.environ.get("KG_NEO4J_USER", "neo4j"),
        os.environ.get("KG_NEO4J_PASSWORD", "excluslawyer"),
        timeout=5.0,
    )
    g.init_schema()
    g.clear()
    g.ingest(build_graph_data(load_official_statutes()))
    yield g
    g.close()


def test_neo4j_roundtrip_counts(neo4j_graph):
    data = build_graph_data(load_official_statutes())
    st = neo4j_graph.stats()
    assert st["nodes"] == len(data.nodes)
    assert st["edges"] == len(data.edges)


def test_neo4j_query_matches_memory(neo4j_graph):
    """同问题下 Neo4j 与内存后端的锚点与关键结论一致。"""
    data = build_graph_data(load_official_statutes())
    mem = MemoryGraph(data)
    q = "违约责任的构成要件是什么"
    assert neo4j_graph.match_anchor(q).id == mem.match_anchor(q).id

    svc_neo = KgService(graph=neo4j_graph)
    svc_mem = KgService(graph=mem)
    r_neo, r_mem = svc_neo.query(q), svc_mem.query(q)
    assert set(r_neo.statute_ids) == set(r_mem.statute_ids)
    assert r_neo.matched_node.id == r_mem.matched_node.id
    assert r_neo.backend == "neo4j"


def test_neo4j_sg_precedent_roundtrip(neo4j_graph):
    resp = KgService(graph=neo4j_graph).query("Chwee Kin Keong 标价错误")
    assert resp.matched_node.node_type == "precedent"
    assert any("SGCA" in c for c in resp.related_cases)


def test_neo4j_clear(neo4j_graph):
    neo4j_graph.clear()
    assert neo4j_graph.stats()["nodes"] == 0
