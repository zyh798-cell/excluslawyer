# -*- coding: utf-8 -*-
"""模拟法庭 API：会话状态机（start/step/session/export + SSE 流式）。

- POST /api/trial/graph/start   开庭（案件+诉状+证据）→ 运行至辩论等待发言
- POST /api/trial/graph/step    中断恢复推进一步（statement / closing / decision）
- POST /api/trial/graph/stream  同 start/step，SSE 流式逐段输出（event: phase/event/…）
- GET  /api/trial/session/{id}  会话快照（刷新/重启后恢复）
- GET  /api/trial/session/{id}/export.md|.pdf  庭审全记录导出（附法条链接）
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response, StreamingResponse

from app.models.schemas import (
    TrialGraphResponse,
    TrialGraphStartRequest,
    TrialGraphStepRequest,
)

router = APIRouter(prefix="/api/trial")


# ---------------- 内部工具 ----------------


def _get_graph(request: Request):
    graph = getattr(request.app.state, "trial_graph", None)
    if graph is None:
        # 兜底：无 lifespan（测试）现场编译（checkpointer 用内存版）
        from app.graph.trial_build import build_trial_graph, make_trial_checkpointer

        graph = build_trial_graph(
            request.app.state.retriever, checkpointer=make_trial_checkpointer()
        )
        request.app.state.trial_graph = graph
    return graph


def _get_store(request: Request):
    store = getattr(request.app.state, "trial_sessions", None)
    if store is None:
        from app.config import settings
        from app.services.trial_session_store import TrialSessionStore

        store = TrialSessionStore(settings.data_dir / "trial_sessions")
        request.app.state.trial_sessions = store
    return store


def _build_response(session_id: str, result: dict) -> TrialGraphResponse:
    """LangGraph 执行结果 → 会话快照响应。"""
    interrupted = "__interrupt__" in result
    phase = result.get("phase") or "create_case"
    pending = ""
    status = result.get("status")
    if interrupted:
        ivs = result.get("__interrupt__") or []
        value = {}
        if ivs:
            iv = ivs[0]
            value = getattr(iv, "value", iv) or {}
        if isinstance(value, dict):
            phase = value.get("phase", phase) or phase
            pending = str(value.get("prompt", "") or "")
        status = status or "awaiting_input"
    elif status is None:
        status = "done"
    return TrialGraphResponse(
        session_id=session_id,
        phase=phase,
        status=status,
        pending=pending,
        interrupted=interrupted,
        case_description=result.get("case_description") or "",
        user_role=result.get("user_role") or "plaintiff",
        jurisdiction=result.get("jurisdiction") or "CN",
        trace=result.get("trace") or [],
        facts=result.get("facts"),
        complaint=result.get("complaint"),
        evidence_reviews=result.get("evidence_reviews") or [],
        limitation=result.get("limitation"),
        debate_turns=result.get("debate_turns") or [],
        closing_text=result.get("closing_text") or "",
        verdict=result.get("verdict"),
        events=result.get("events") or [],
    )


def _start_payload(req: TrialGraphStartRequest, session_id: str) -> dict:
    return {
        "session_id": session_id,
        "case_description": req.case_description,
        "user_role": req.user_role,
        "jurisdiction": req.jurisdiction,
        "language": req.language,
        "top_k": min(req.top_k, 20),
        "claims_input": [c.model_dump() for c in req.claims],
        "evidences_input": [e.model_dump() for e in req.evidences],
        "interrupt_on_limitation": req.interrupt_on_limitation,
    }


def _resume_value(req: TrialGraphStepRequest):
    if req.statement is not None:
        return req.statement
    if req.closing is not None:
        return req.closing
    if req.decision is not None:
        return req.decision
    raise HTTPException(status_code=400, detail="statement / closing / decision 三选一")


# ---------------- JSON 接口 ----------------


@router.post("/graph/start", response_model=TrialGraphResponse)
def trial_graph_start(req: TrialGraphStartRequest, request: Request) -> TrialGraphResponse:
    """开庭：create_case→fix_facts→file_complaint→evidence_review→debate（等待第 1 轮发言）。"""
    graph = _get_graph(request)
    session_id = req.session_id or f"trial-{uuid.uuid4().hex[:12]}"
    config = {"configurable": {"thread_id": session_id}}
    result = graph.invoke(_start_payload(req, session_id), config)
    resp = _build_response(session_id, result)
    _get_store(request).save(resp.model_dump())
    return resp


@router.post("/graph/step", response_model=TrialGraphResponse)
def trial_graph_step(req: TrialGraphStepRequest, request: Request) -> TrialGraphResponse:
    """中断恢复推进一步：辩论发言 / 总结陈词 / 人工确认（approve|reject）。"""
    from langgraph.types import Command

    graph = _get_graph(request)
    config = {"configurable": {"thread_id": req.session_id}}
    try:
        result = graph.invoke(Command(resume=_resume_value(req)), config)
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=404, detail=f"会话 {req.session_id} 不存在或已终结（{exc}）"
        ) from exc
    resp = _build_response(req.session_id, result)
    _get_store(request).save(resp.model_dump())
    return resp


@router.get("/session/{session_id}", response_model=TrialGraphResponse)
def get_trial_session(session_id: str, request: Request) -> TrialGraphResponse:
    """会话快照：刷新/重启后恢复庭审现场。"""
    rec = _get_store(request).load(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")
    return TrialGraphResponse(**rec)


# ---------------- 导出 ----------------


def _load_record(request: Request, session_id: str) -> dict:
    rec = _get_store(request).load(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")
    return rec


@router.get("/session/{session_id}/export.md")
def export_trial_markdown(session_id: str, request: Request) -> PlainTextResponse:
    from app.services.trial_export_service import to_markdown

    md = to_markdown(_load_record(request, session_id))
    return PlainTextResponse(
        md,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="trial-{session_id}.md"'
        },
    )


@router.get("/session/{session_id}/export.pdf")
def export_trial_pdf(session_id: str, request: Request) -> Response:
    from app.services.trial_export_service import to_pdf_bytes

    try:
        pdf = to_pdf_bytes(_load_record(request, session_id))
    except ImportError as exc:  # reportlab 未安装
        raise HTTPException(status_code=501, detail=f"PDF 导出依赖缺失: {exc}") from exc
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="trial-{session_id}.pdf"'
        },
    )


# ---------------- SSE 流式 ----------------


def _sse(data: dict, event: str) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/graph/stream")
def trial_graph_stream(req: dict, request: Request) -> StreamingResponse:
    """SSE 流式执行：body 同 start（含 case_description）或同 step（含 statement/closing/decision）。

    事件流：phase（节点完成）→ event（庭审记录事件）→ turn（辩论发言）→ done（完整快照）。
    """
    # 预校验（错误立即 4xx，而不是流中途 error 事件）
    from pydantic import ValidationError

    is_step = any(k in req for k in ("statement", "closing", "decision")) or (
        "session_id" in req and "case_description" not in req
    )
    try:
        step_req = TrialGraphStepRequest.model_validate(req) if is_step else None
        start_req = None if is_step else TrialGraphStartRequest.model_validate(req)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if step_req is not None:
        _resume_value(step_req)  # 三选一校验

    def generate():
        from langgraph.types import Command

        graph = _get_graph(request)
        try:
            if step_req is not None:
                session_id = step_req.session_id
                config = {"configurable": {"thread_id": session_id}}
                payload = Command(resume=_resume_value(step_req))
            else:
                assert start_req is not None
                session_id = start_req.session_id or f"trial-{uuid.uuid4().hex[:12]}"
                config = {"configurable": {"thread_id": session_id}}
                payload = _start_payload(start_req, session_id)

            yield _sse({"session_id": session_id}, "open")

            interrupted = False
            for chunk in graph.stream(payload, config, stream_mode="updates"):
                for node, upd in (chunk or {}).items():
                    # interrupt/元信息 chunk 值不是 dict（如 {"__interrupt__": (Interrupt,)}），跳过
                    if not isinstance(upd, dict):
                        continue
                    yield _sse(
                        {"node": node, "trace": upd.get("trace", [])}, "phase"
                    )
                    for ev in upd.get("events", []) or []:
                        d = ev.model_dump() if hasattr(ev, "model_dump") else ev
                        yield _sse(d, "event")
                    for turn in upd.get("debate_turns", []) or []:
                        t = turn.model_dump() if hasattr(turn, "model_dump") else turn
                        yield _sse(t, "turn")
                    if upd.get("verdict") is not None:
                        v = upd["verdict"]
                        yield _sse(
                            v.model_dump() if hasattr(v, "model_dump") else v,
                            "verdict",
                        )

            snapshot = graph.get_state(config)
            values = dict(snapshot.values or {})
            if snapshot.next:
                interrupted = True
                interrupts = []
                for task in snapshot.tasks or ():
                    interrupts.extend(getattr(task, "interrupts", ()) or ())
                values["__interrupt__"] = list(interrupts) or [True]
            resp = _build_response(session_id, values)
            _get_store(request).save(resp.model_dump())
            yield _sse(resp.model_dump(), "done")
        except (ValueError, KeyError) as exc:
            yield _sse({"error": str(exc)}, "error")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
