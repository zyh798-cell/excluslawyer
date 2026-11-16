"""向量化层：BGE-M3（多语言，中/日/韩/英跨语言检索）+ 哈希兜底。

EMBEDDER=auto 时优先 BGE-M3；未安装 sentence-transformers 或模型下载失败
则自动降级为哈希向量（仅开发/测试可用，检索质量明显下降，会打 warning）。
"""

import hashlib
import logging
import re
from typing import Protocol

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


class BaseEmbedder(Protocol):
    dim: int
    score_floor: float  # 检索相似度下限（低于此分视为未命中，触发"证据不足"）

    def embed(self, texts: list[str], query: bool = False) -> list[list[float]]: ...


class HashingEmbedder:
    """确定性哈希嵌入（无依赖兜底）。

    中日韩文本按字符 2-gram 切分，英文按词，SHA1 播种到固定维度桶，
    同一文本永远得到同一向量，保证测试可复现。
    """

    score_floor = 0.10  # 哈希向量分数普遍偏低，实测相关≥0.13、无关≤0.06

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _tokens(self, text: str) -> list[str]:
        text = text.lower()
        # 英文/数字词
        tokens = re.findall(r"[a-z0-9]+", text)
        # CJK 字符 2-gram
        cjk = re.findall(r"[一-鿿一-鿿぀-ヿ가-힯]", text)
        tokens.extend("".join(pair) for pair in zip(cjk, cjk[1:]))
        return tokens or [text.strip() or "empty"]

    def embed(self, texts: list[str], query: bool = False) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=np.float32)
            for tok in self._tokens(text):
                digest = hashlib.sha1(tok.encode("utf-8")).digest()
                idx = int.from_bytes(digest[:4], "little") % self.dim
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vec[idx] += sign
            norm = float(np.linalg.norm(vec))
            out.append((vec / norm if norm > 0 else vec).tolist())
        return out


class BGEM3Embedder:
    """BAAI/bge-m3：多语言统一向量空间，支持中日韩英跨语言检索。"""

    score_floor = 0.35  # 语义向量空间相关文档通常 0.45+，0.35 以下视为未命中

    # BGE 系列检索前缀：查询与文档用不同指令（官方推荐）
    QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
    DOC_PREFIX = "Represent this document for retrieval: "

    def __init__(self, model_name: str = "BAAI/bge-m3", device: str | None = None):
        from sentence_transformers import SentenceTransformer  # 延迟导入

        self.model = SentenceTransformer(model_name, device=device)
        self.dim = int(self.model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str], query: bool = False) -> list[list[float]]:
        prefix = self.QUERY_PREFIX if query else self.DOC_PREFIX
        prefixed = [f"{prefix}{t}" for t in texts]
        vecs = self.model.encode(prefixed, normalize_embeddings=True)
        return [v.tolist() for v in vecs]


def get_embedder() -> BaseEmbedder:
    """按配置构造 embedder；auto 模式失败即降级，不阻塞服务。"""
    choice = settings.embedder.lower()
    if choice in ("auto", "bge_m3"):
        try:
            emb = BGEM3Embedder()
            logger.info("Embedder 就绪: BGE-M3 (dim=%d)", emb.dim)
            return emb
        except Exception as exc:  # noqa: BLE001
            if choice == "bge_m3":
                raise
            logger.warning("BGE-M3 不可用（%s），降级为哈希向量（仅开发用）", exc)
    emb = HashingEmbedder()
    logger.info("Embedder 就绪: HashingEmbedder (dim=%d)", emb.dim)
    return emb
