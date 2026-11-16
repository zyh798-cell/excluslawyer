"""向量库抽象：Milvus Lite（本地文件）/ Milvus Standalone / Numpy 兜底。

三者接口一致（upsert / search / count），上层不感知具体后端。
Milvus Lite 就是 pymilvus 的嵌入式模式（URI 指向本地 .db 文件），无需起服务。
"""

import logging
import pickle
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


class VectorStore(Protocol):
    def upsert(self, ids: list[str], vectors: list[list[float]], payloads: list[dict]) -> None: ...
    def search(self, vector: list[float], top_k: int) -> list[tuple[str, float, dict]]: ...
    def get(self, id: str) -> dict | None: ...
    def count(self) -> int: ...
    def flush(self) -> None: ...


class NumpyVectorStore:
    """纯 Python 后端：内存余弦检索，落盘 pickle。开发/测试兜底。"""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.ids: list[str] = []
        self.vectors: np.ndarray | None = None
        self.payloads: dict[str, dict] = {}
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        with open(self.path, "rb") as f:
            blob = pickle.load(f)
        self.ids = blob["ids"]
        self.vectors = np.asarray(blob["vectors"], dtype=np.float32)
        self.payloads = blob["payloads"]
        logger.info("NumpyVectorStore 加载 %d 条记录", len(self.ids))

    def upsert(self, ids: list[str], vectors: list[list[float]], payloads: list[dict]) -> None:
        new_vecs = np.asarray(vectors, dtype=np.float32)
        # 按 id 去重覆盖
        for i, sid in enumerate(ids):
            if sid in self.payloads and self.vectors is not None:
                pos = self.ids.index(sid)
                self.vectors[pos] = new_vecs[i]
            else:
                self.ids.append(sid)
                self.vectors = (
                    np.vstack([self.vectors, new_vecs[i : i + 1]])
                    if self.vectors is not None
                    else new_vecs[i : i + 1]
                )
            self.payloads[sid] = payloads[i]

    def search(self, vector: list[float], top_k: int) -> list[tuple[str, float, dict]]:
        if self.vectors is None or not self.ids:
            return []
        q = np.asarray(vector, dtype=np.float32)
        q = q / (np.linalg.norm(q) or 1.0)
        mat = self.vectors / (np.linalg.norm(self.vectors, axis=1, keepdims=True) + 1e-9)
        sims = mat @ q
        order = np.argsort(-sims)[:top_k]
        return [(self.ids[i], float(sims[i]), self.payloads[self.ids[i]]) for i in order]

    def get(self, id: str) -> dict | None:
        return self.payloads.get(id)

    def count(self) -> int:
        return len(self.ids)

    def flush(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "wb") as f:
            pickle.dump({"ids": self.ids, "vectors": self.vectors, "payloads": self.payloads}, f)


class MilvusVectorStore:
    """pymilvus 后端：URI 是本地 .db 文件即 Milvus Lite，是 http://host:19530 即 Standalone。"""

    def __init__(self, uri: str, collection: str, dim: int):
        from pymilvus import (  # 延迟导入：无 pymilvus 环境也能跑 Numpy 后端
            DataType,
            FieldSchema,
            CollectionSchema,
            MilvusClient,
        )

        self.client = MilvusClient(uri=uri)
        self.collection = collection
        self.dim = dim
        if not self.client.has_collection(collection):
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=128),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
                FieldSchema(name="payload", dtype=DataType.JSON),
            ]
            self.client.create_collection(
                collection_name=collection, schema=CollectionSchema(fields)
            )
            self.client.create_index(
                collection_name=collection,
                field_name="vector",
                index_params={"metric_type": "COSINE", "index_type": "FLAT", "params": {}},
            )
            logger.info("Milvus collection 创建完成: %s", collection)

    def upsert(self, ids: list[str], vectors: list[list[float]], payloads: list[dict]) -> None:
        rows = [
            {"id": i, "vector": v, "payload": p}
            for i, v, p in zip(ids, vectors, payloads)
        ]
        self.client.upsert(collection_name=self.collection, data=rows)

    def search(self, vector: list[float], top_k: int) -> list[tuple[str, float, dict]]:
        res = self.client.search(
            collection_name=self.collection,
            data=[vector],
            limit=top_k,
            output_fields=["payload"],
            search_params={"metric_type": "COSINE"},
        )
        hits = res[0] if res else []
        return [(h["id"], float(h["distance"]), h["entity"]["payload"]) for h in hits]

    def get(self, id: str) -> dict | None:
        rows = self.client.get(collection_name=self.collection, ids=[id], output_fields=["payload"])
        if not rows:
            return None
        p = rows[0].get("payload")
        return p if isinstance(p, dict) else dict(p or {})

    def count(self) -> int:
        return int(self.client.get_collection_stats(self.collection)["row_count"])

    def flush(self) -> None:  # Milvus 自带持久化
        return


def get_vector_store(dim: int) -> VectorStore:
    choice = settings.vector_store.lower()
    if choice == "numpy":
        return NumpyVectorStore(settings.data_dir / "numpy_store.pkl")
    if choice in ("auto", "milvus_lite", "milvus"):
        try:
            uri = settings.milvus_uri
            if choice == "milvus" and uri.startswith("./"):
                uri = "http://localhost:19530"
            return MilvusVectorStore(uri, settings.collection_name, dim)
        except Exception as exc:  # noqa: BLE001
            if choice == "milvus":
                raise
            logger.warning("Milvus 不可用（%s），降级为 Numpy 向量库", exc)
    return NumpyVectorStore(settings.data_dir / "numpy_store.pkl")


def payload_to_dict(p: Any) -> dict:
    if isinstance(p, dict):
        return p
    return dict(p or {})
