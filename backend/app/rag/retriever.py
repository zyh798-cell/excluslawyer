"""检索 + 重排。

流程：问题 → 向量化 → 向量库 top-N 召回 →（可选）BGE-Reranker-v2-m3 精排 → top_k。
质量闸门（铁律 1 的兜底）：向量相似度 OR 词面重叠率必须有一个达标，否则丢弃该召回，
宁可返回空（上层报"证据不足"）也不许硬凑引用。重排器不可用时按向量相似度直接截断。
"""

import logging
import re
from dataclasses import dataclass

from app.config import settings
from app.models.schemas import Citation
from app.rag.embedder import BaseEmbedder
from app.rag.vector_store import VectorStore, payload_to_dict

logger = logging.getLogger(__name__)

# 时效状态权重：失效条文降权，避免拿旧法当现行依据
STATUS_WEIGHT = {"effective": 1.0, "amended": 0.85, "unknown": 0.7, "repealed": 0.3}

# 词面重叠率下限：实测真实法律问题≥0.125、无关问题=0.0，0.08 留安全余量
OVERLAP_FLOOR = 0.08

# 语义强证据阈值：只有语义向量（BGE-M3）能到 0.35+；哈希向量达不到，必须靠词面重叠
SEMANTIC_FLOOR = 0.35


def _bigrams(text: str) -> set[str]:
    cleaned = re.sub(r"[^\w一-鿿぀-ヿ가-힯]", "", text.lower())
    return set(cleaned[i : i + 2] for i in range(len(cleaned) - 1)) or {cleaned}


def _overlap(question: str, text: str) -> float:
    """查询与文本的字符 2-gram 重叠率（中日韩英通吃）。"""
    q = _bigrams(question)
    t = _bigrams(text)
    return len(q & t) / max(len(q), 1)


@dataclass
class Hit:
    statute_id: str
    score: float
    payload: dict


class Retriever:
    def __init__(self, embedder: BaseEmbedder, store: VectorStore):
        self.embedder = embedder
        self.store = store
        self._reranker = None

    def _get_reranker(self):
        if self._reranker is not None:
            return self._reranker
        if settings.reranker.lower() in ("auto", "bge_reranker"):
            try:
                from sentence_transformers import CrossEncoder

                self._reranker = CrossEncoder("BAAI/bge-reranker-v2-m3")
                logger.info("Reranker 就绪: BGE-Reranker-v2-m3")
            except Exception as exc:  # noqa: BLE001
                if settings.reranker.lower() == "bge_reranker":
                    raise
                logger.warning("Reranker 不可用（%s），使用向量相似度排序", exc)
                self._reranker = False
        else:
            self._reranker = False
        return self._reranker

    def retrieve(self, question: str, top_k: int = 5, jurisdiction: str | None = None) -> list[Citation]:
        qvec = self.embedder.embed([question], query=True)[0]
        # 多召一点给重排留余量
        raw = self.store.search(qvec, top_k=max(top_k * 3, top_k))
        hits = [Hit(sid, score, payload_to_dict(p)) for sid, score, p in raw]

        if jurisdiction:
            # 法域过滤：优先本法域，但不直接丢弃他法域（跨法域比较场景需要）
            hits.sort(key=lambda h: (h.payload.get("jurisdiction") != jurisdiction, -h.score))

        reranker = self._get_reranker()
        if reranker and reranker is not False and hits:
            pairs = [(question, f"{h.payload.get('law_title', '')} {h.payload.get('article_no', '')} {h.payload.get('text', '')}") for h in hits]
            scores = reranker.predict(pairs)
            order = sorted(range(len(hits)), key=lambda i: -float(scores[i]))
            hits = [hits[i] for i in order]
            for i, h in enumerate(hits):
                h.score = float(scores[i])

        citations: list[Citation] = []
        # 质量闸门（铁律1）：词面重叠达标 或 语义高分，二选一才放行；
        # 否则丢弃——召回质量不够就说"证据不足"，不许硬凑引用。
        # 哈希向量模式词面重叠是唯一可靠信号（向量分会碰撞虚高）。
        for h in hits[:top_k]:
            p = h.payload
            status = p.get("status", "unknown")
            # 时效加权：废止条文即使相似度高也要压下去
            weighted = h.score * STATUS_WEIGHT.get(status, 0.7)
            lex_overlap = _overlap(question, f"{p.get('article_no', '')} {p.get('text', '')}")
            if lex_overlap < OVERLAP_FLOOR and weighted < SEMANTIC_FLOOR:
                continue
            citations.append(
                Citation(
                    statute_id=h.statute_id,
                    law_title=p.get("law_title", ""),
                    article_no=p.get("article_no", ""),
                    text=p.get("text", ""),
                    gloss=p.get("gloss", ""),
                    jurisdiction=p.get("jurisdiction", "CN"),
                    language=p.get("language", "zh"),
                    effective_status=status if status in STATUS_WEIGHT else "unknown",
                    effective_date=p.get("effective_date"),
                    amended_history=p.get("amended_history", []),
                    revisions=p.get("revisions", []),
                    score=round(weighted, 4),
                    source_url=p.get("source_url", ""),
                )
            )
        citations.sort(key=lambda c: -c.score)
        return citations
