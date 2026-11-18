"""FastAPI 入口。

启动时：
1. 初始化 Embedder / VectorStore / Retriever / AskService
2. AUTO_INGEST=true 且向量库为空时，自动灌入种子法条（开箱即用）
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.trial_routes import router as trial_router
from app.config import settings
from app.rag.embedder import get_embedder
from app.rag.retriever import Retriever
from app.rag.vector_store import get_vector_store
from app.services.ask_service import AskService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("excluslawyer")


@asynccontextmanager
async def lifespan(app: FastAPI):
    embedder = get_embedder()
    store = get_vector_store(embedder.dim)
    retriever = Retriever(embedder, store)
    app.state.retriever = retriever
    app.state.ask_service = AskService(retriever)

    # LangGraph 咨询状态机（带 checkpointer：支持人工确认中断恢复）
    from langgraph.checkpoint.memory import MemorySaver

    from app.graph.build import build_graph

    app.state.consult_graph = build_graph(retriever, checkpointer=MemorySaver())

    # LangGraph 模拟法庭状态机（SqliteSaver：跨进程/重启中断恢复）
    from app.graph.trial_build import build_trial_graph, make_trial_checkpointer
    from app.services.trial_session_store import TrialSessionStore

    app.state.trial_graph = build_trial_graph(
        retriever,
        checkpointer=make_trial_checkpointer(settings.data_dir / "trial_checkpoints.sqlite"),
    )
    app.state.trial_sessions = TrialSessionStore(settings.data_dir / "trial_sessions")

    if settings.auto_ingest and store.count() == 0:
        logger.info("向量库为空，自动灌入种子法条…")
        from scripts.ingest_cn import ingest_seed

        n = ingest_seed(embedder, store)
        logger.info("种子法条入库完成: %d 条", n)
    else:
        logger.info("向量库现有 %d 条记录", store.count())
    yield


app = FastAPI(
    title="EXCLUSLAWYER API",
    description="多法域法律推理引擎 —— 每条结论必挂现行有效法条原文",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(trial_router)


@app.get("/")
def root() -> dict:
    return {
        "name": "EXCLUSLAWYER",
        "docs": "/docs",
        "endpoints": [
            "/api/ask",
            "/api/retrieve",
            "/api/verify",
            "/api/structure-facts",
            "/api/opinion",
            "/api/contract/scan",
            "/api/cases/search",
            "/api/statute/{id}",
            "/api/multimodal/analyze",
            "/api/trial/start",
            "/api/trial/turn",
            "/api/trial/graph/start",
            "/api/trial/graph/step",
            "/api/trial/graph/stream",
            "/api/trial/session/{id}",
            "/api/trial/session/{id}/export.md",
            "/api/trial/session/{id}/export.pdf",
            "/api/kg/query",
            "/api/calculator/calculate",
            "/api/compare",
            "/api/feedback",
            "/api/health",
        ],
    }
