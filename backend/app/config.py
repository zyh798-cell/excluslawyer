"""全局配置：环境变量驱动，数据层字段全部多法域可配，不写死中国法。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ---- 向量与检索 ----
    embedder: str = "auto"  # auto | bge_m3 | hash
    reranker: str = "auto"  # auto | bge_reranker | none
    vector_store: str = "auto"  # auto | milvus_lite | milvus | numpy
    milvus_uri: str = "./data/milvus_lite.db"
    collection_name: str = "lex_statutes"
    top_k: int = 5

    # ---- LLM（服务端演示模式；BYOK 模式下前端直连，不读这些）----
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "Qwen2.5-7B-Instruct"

    # ---- 校验与降级 ----
    nli_threshold: float = 0.35

    # ---- 数据 ----
    data_dir: Path = Path("./data")
    auto_ingest: bool = True

    # ---- 可选基础设施 ----
    redis_url: str = "redis://localhost:6379/0"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "excluslawyer"

    # CORS：本地开发前端
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
