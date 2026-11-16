"""API 路由：/api/ask /api/retrieve /api/verify /api/feedback /api/health。

BYOK 模式下前端只调 /api/retrieve + /api/verify，
LLM 由前端直连服务商——API Key 绝不经过本后端。
"""

import json
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile

from app.config import settings
from app.core.security import scan_untrusted
from app.models.schemas import (
    AskRequest,
    AskResponse,
    CalcRequest,
    CalcResponse,
    CaseSearchRequest,
    CaseSearchResponse,
    CompareRequest,
    CompareResponse,
    ConsultGraphRequest,
    ConsultGraphResponse,
    ContractScanRequest,
    ContractScanResponse,
    FeedbackRequest,
    KgQueryResponse,
    NliResult,
    OpinionRequest,
    OpinionResponse,
    RetrieveRequest,
    RetrieveResponse,
    StatuteTimeline,
    TrialSession,
    TrialStartRequest,
    TrialTurnRequest,
    VerifyRequest,
)

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request) -> dict:
    return {
        "status": "ok",
        "vector_count": request.app.state.retriever.store.count(),
        "embedder": type(request.app.state.retriever.embedder).__name__,
    }


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, request: Request) -> AskResponse:
    svc = request.app.state.ask_service
    try:
        return svc.ask(
            question=req.question,
            jurisdiction=req.jurisdiction,
            language=req.language,
            top_k=min(req.top_k, 20),
            adversarial=req.adversarial,
        )
    except ValueError as exc:
        # 注入检测 / 拒答机制 → 400
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(req: RetrieveRequest, request: Request) -> RetrieveResponse:
    """BYOK 流程第一步：只检索，不生成。前端拿 context_pack 自己调 LLM。"""
    scan = scan_untrusted(req.question)
    if not scan.safe:
        raise HTTPException(status_code=400, detail=scan.detail)
    svc = request.app.state.ask_service
    return svc.retrieve(req.question, req.jurisdiction, req.language, min(req.top_k, 20))


@router.post("/verify", response_model=NliResult)
def verify(req: VerifyRequest, request: Request) -> NliResult:
    """BYOK 流程第二步：前端生成完答案后回来做结论-依据一致性校验。"""
    svc = request.app.state.ask_service
    return svc.verify(req)


@router.post("/structure-facts")
def structure_facts_endpoint(req: dict) -> dict:
    """P0-2：案情叙述 → 四类事实 + 时间线卡片。"""
    narrative = str(req.get("narrative", "")).strip()
    if not narrative:
        raise HTTPException(status_code=400, detail="narrative 不能为空")
    scan = scan_untrusted(narrative)
    if not scan.safe:
        raise HTTPException(status_code=400, detail=scan.detail)
    from app.services.facts_service import structure_facts

    return structure_facts(narrative).model_dump()


@router.post("/opinion", response_model=OpinionResponse)
def opinion(req: OpinionRequest, request: Request) -> OpinionResponse:
    """P0-3：案情 → 事实结构化 + 法条检索 + 五段式法律意见书。"""
    scan = scan_untrusted(req.narrative)
    if not scan.safe:
        raise HTTPException(status_code=400, detail=scan.detail)
    from app.services.opinion_service import OpinionService

    svc = OpinionService(request.app.state.retriever)
    return svc.build(req)


# ============ P1 ============


@router.post("/contract/scan", response_model=ContractScanResponse)
def contract_scan(req: ContractScanRequest, request: Request) -> ContractScanResponse:
    """P1-5：合同文本/PDF → 逐条红黄绿风险标注 + 法条引用 + 修改建议。"""
    import base64

    text = req.text.strip()
    if not text and req.pdf_base64:
        from app.services.contract_service import extract_text_from_pdf

        try:
            text = extract_text_from_pdf(base64.b64decode(req.pdf_base64))
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not text:
        raise HTTPException(status_code=400, detail="请提供合同文本（text）或 PDF（pdf_base64）")

    from app.services.contract_service import ContractScanService

    svc = ContractScanService(request.app.state.retriever)
    return svc.scan(text)


@router.post("/cases/search", response_model=CaseSearchResponse)
def cases_search(req: CaseSearchRequest) -> CaseSearchResponse:
    """P1-6：要素匹配类案 → 裁判结果分布 + 支持率。"""
    from app.services.cases_service import CaseSearchService

    svc = CaseSearchService()
    return svc.search(req)


@router.get("/statute/{statute_id}", response_model=StatuteTimeline)
def statute_timeline(statute_id: str, request: Request) -> StatuteTimeline:
    """P1-7：法条时效追踪 → 版本沿革 + 修订 diff + 引用建议。"""
    from app.rag.vector_store import payload_to_dict
    from app.services.statute_service import build_statute_timeline

    payload = request.app.state.retriever.store.get(statute_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"未找到法条 {statute_id}")
    return build_statute_timeline(statute_id, payload_to_dict(payload))


@router.post("/multimodal/analyze")
async def multimodal_analyze(file: UploadFile, request: Request) -> dict:
    """P1-8：拍照/截图 → OCR → 自动路由到对应分析流程。"""
    data = await file.read()
    from app.services.contract_service import ContractScanService
    from app.services.multimodal_service import MultimodalService

    svc = MultimodalService(ContractScanService(request.app.state.retriever))
    return svc.analyze(data)


# ============ P2 ============


@router.post("/trial/start", response_model=TrialSession)
def trial_start(req: TrialStartRequest, request: Request) -> TrialSession:
    """P2-9：开庭（法官归纳焦点 + 对方律师开场）。"""
    scan = scan_untrusted(req.case_description)
    if not scan.safe:
        raise HTTPException(status_code=400, detail=scan.detail)
    from app.services.trial_service import TrialService

    return TrialService(request.app.state.retriever).start(req)


@router.post("/trial/turn", response_model=TrialSession)
def trial_turn(req: TrialTurnRequest, request: Request) -> TrialSession:
    """P2-9：用户发言 → 对方反驳 → 法官评析（3 轮后模拟判决）。"""
    from app.services.trial_service import TrialService

    try:
        return TrialService(request.app.state.retriever).turn(req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/kg/query", response_model=KgQueryResponse)
def kg_query(req: dict) -> KgQueryResponse:
    """P2-10：法律知识图谱多跳问答。"""
    question = str(req.get("question", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="question 不能为空")
    from app.services.kg_service import KgService

    return KgService().query(question)


@router.get("/kg/stats")
def kg_stats() -> dict:
    """图谱观测：后端类型、节点/边规模、类型分布。"""
    from app.services.kg_service import get_default_graph

    return get_default_graph().stats()


@router.post("/calculator/calculate", response_model=CalcResponse)
def calculator_calculate(req: CalcRequest) -> CalcResponse:
    """P2-11：赔偿计算器（透明公式 + 法条依据）。"""
    from app.services.calculator_service import CalculatorService

    return CalculatorService().calculate(req)


@router.post("/compare", response_model=CompareResponse)
def compare(req: CompareRequest) -> CompareResponse:
    """P2-12：多法域规则并列对比。"""
    from app.services.compare_service import CompareService

    return CompareService().compare(req)


@router.post("/feedback")
def feedback(req: FeedbackRequest, request: Request) -> dict:
    """用户反馈闭环：'有误'/'引用过时' 样本落盘，自动进入 Golden Set 迭代。"""
    path: Path = settings.data_dir / "feedback.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": time.time(), **req.model_dump()}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"ok": True, "saved_to": str(path)}


@router.post("/consult/graph", response_model=ConsultGraphResponse)
def consult_graph(req: ConsultGraphRequest, request: Request) -> ConsultGraphResponse:
    """LangGraph 咨询状态机：intake→facts→retrieve→draft→nli[→human]→adversarial→finalize。

    - interrupt_on_degraded=True 且 NLI 降级时返回 interrupted=True，
      带 thread_id 再调本接口并传 resume_decision（approve/reject）恢复执行。
    """
    import uuid

    from langgraph.types import Command

    from app.graph.build import build_graph

    graph = getattr(request.app.state, "consult_graph", None)
    if graph is None:
        # 兜底：无 lifespan 场景（测试）现场编译（无 checkpointer 则不支持中断）
        graph = build_graph(request.app.state.retriever)
        request.app.state.consult_graph = graph

    thread_id = req.thread_id or f"consult-{uuid.uuid4().hex[:12]}"
    config = {"configurable": {"thread_id": thread_id}}

    if req.resume_decision:
        payload = Command(resume=req.resume_decision)
    else:
        payload = {
            "question": req.question,
            "jurisdiction": req.jurisdiction,
            "language": req.language,
            "top_k": min(req.top_k, 20),
            "adversarial": req.adversarial,
            "interrupt_on_degraded": req.interrupt_on_degraded,
        }

    try:
        result = graph.invoke(payload, config)
    except ValueError as e:  # 无 checkpointer 时 interrupt 会报错
        raise HTTPException(status_code=400, detail=str(e)) from e

    interrupted = "__interrupt__" in result
    facts = result.get("facts")
    nli = result.get("nli")
    return ConsultGraphResponse(
        status=result.get("status") or ("done" if not interrupted else "degraded"),
        answer=result.get("answer") or result.get("draft_answer") or "",
        citations=result.get("citations") or [],
        facts=facts,
        nli=nli,
        confidence=result.get("confidence") or 0.0,
        trace=result.get("trace") or [],
        adversarial_notes=result.get("adversarial_notes"),
        answer_mode=result.get("answer_mode"),
        interrupted=interrupted,
        thread_id=thread_id,
    )
