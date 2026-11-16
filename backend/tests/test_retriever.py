"""检索层单测：哈希向量 + Numpy 后端，零外部依赖可跑。"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.models.schemas import Statute
from app.rag.embedder import HashingEmbedder
from app.rag.retriever import Retriever
from app.rag.vector_store import NumpyVectorStore
from scripts.ingest_cn import ingest_statutes


def _seed_store() -> Retriever:
    emb = HashingEmbedder(dim=128)
    store = NumpyVectorStore(path=None)  # 纯内存
    statutes = [
        Statute(
            id="CN-TEST-1",
            law_title="测试合同法",
            article_no="第一条",
            text="当事人一方不履行合同义务的，应当承担违约责任，赔偿对方损失。",
            topics=["合同", "违约"],
            status="effective",
        ),
        Statute(
            id="CN-TEST-2",
            law_title="测试劳动法",
            article_no="第二条",
            text="用人单位解除劳动合同应当支付经济补偿金。",
            topics=["劳动", "经济补偿"],
            status="effective",
        ),
        Statute(
            id="CN-TEST-3",
            law_title="已废止条例",
            article_no="第三条",
            text="本条例关于违约金的规定已经废止，不再适用。",
            topics=["合同"],
            status="repealed",
        ),
    ]
    ingest_statutes(statutes, emb, store)
    return Retriever(emb, store)


def test_retrieve_relevant_statute():
    r = _seed_store()
    cites = r.retrieve("对方违约不赔钱怎么办", top_k=2)
    assert cites, "必须有召回结果"
    assert cites[0].statute_id == "CN-TEST-1", f"应召回违约条文，实际 {cites[0].statute_id}"


def test_repealed_statute_downweighted():
    r = _seed_store()
    cites = r.retrieve("违约金的规定", top_k=3)
    by_id = {c.statute_id: c.score for c in cites}
    # 废止条文加权后要么被 MIN_SCORE 过滤掉（更严格），要么分数必须低于生效条文
    if "CN-TEST-3" in by_id:
        assert "CN-TEST-1" in by_id
        assert by_id["CN-TEST-3"] < by_id["CN-TEST-1"]
    else:
        assert "CN-TEST-1" in by_id, "生效条文仍应被召回"


def test_empty_store_returns_nothing():
    emb = HashingEmbedder(dim=64)
    r = Retriever(emb, NumpyVectorStore(path=None))
    assert r.retrieve("任何问题", top_k=3) == []


def test_embedder_deterministic():
    emb = HashingEmbedder(dim=64)
    v1 = emb.embed(["同一句话"])[0]
    v2 = emb.embed(["同一句话"])[0]
    assert v1 == v2, "哈希向量必须确定性"
