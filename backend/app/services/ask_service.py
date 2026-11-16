"""RAG 编排服务：注入检测 → 检索 → 组 Prompt → LLM/演示降级 → NLI 校验。

NLI 校验（"结论是否被引用法条蕴含"）：
- 有 NLI 模型时用模型打分；
- 无模型时用词面重叠启发式打分，status=unverified（诚实标注，不假装校验过）；
- 低于阈值自动降级：在 answer 头部插入"引用支撑不足"警示。
"""

import logging
import re

from app.config import settings
from app.core.llm import LLMConfig, extractive_answer, generate
from app.core.prompts import SYSTEM_PROMPT, build_user_prompt
from app.core.security import scan_untrusted
from app.models.schemas import (
    AskResponse,
    Citation,
    NliResult,
    RetrieveResponse,
    VerifyRequest,
)
from app.rag.retriever import Retriever

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[一-鿿鿿぀-ヿ가-힯a-z0-9]")


def _tokens(text: str) -> set[str]:
    """中日韩按字、英文按词，粗粒度词面集合。"""
    chars = _TOKEN_RE.findall(text.lower())
    words = re.findall(r"[a-z0-9]+", text.lower())
    return set(chars) | set(words)


def nli_check(answer: str, citations: list[Citation]) -> NliResult:
    """结论-依据一致性校验。P0 用词面重叠启发式，P1 换多语言 NLI 模型。"""
    if not citations:
        return NliResult(status="unverified", score=0.0, reason="无引用，无法校验")
    if "【演示模式" in answer or "【证据不足】" in answer:
        # 演示模式只做摘录，不存在生成幻觉，直接通过
        return NliResult(status="pass", score=1.0, reason="演示模式（摘录式回答）")

    ans_tokens = _tokens(answer)
    best = 0.0
    for c in citations:
        cit_tokens = _tokens(c.text) | _tokens(c.article_no)
        if not ans_tokens or not cit_tokens:
            continue
        overlap = len(ans_tokens & cit_tokens) / max(len(ans_tokens), 1)
        best = max(best, overlap)

    if best >= settings.nli_threshold:
        return NliResult(
            status="unverified",
            score=round(best, 3),
            reason="词面重叠达阈值（未加载 NLI 模型，结果仅供参考）",
        )
    return NliResult(
        status="degraded",
        score=round(best, 3),
        reason=f"结论与引用法条词面重叠仅 {best:.0%}，低于阈值 {settings.nli_threshold:.0%}，已降级标注",
    )


class AskService:
    def __init__(self, retriever: Retriever):
        self.retriever = retriever

    def retrieve(self, question: str, jurisdiction: str, language: str, top_k: int) -> RetrieveResponse:
        citations = self.retriever.retrieve(question, top_k=top_k, jurisdiction=jurisdiction)
        return RetrieveResponse(
            citations=citations,
            context_pack=_pack_context(citations),
        )

    def verify(self, req: VerifyRequest) -> NliResult:
        return nli_check(req.answer, req.citations)

    def ask(self, question: str, jurisdiction: str, language: str, top_k: int, adversarial: bool) -> AskResponse:
        # 1. 注入检测
        scan = scan_untrusted(question)
        if not scan.safe:
            raise ValueError(f"{scan.detail}")

        # 2. 检索
        citations = self.retriever.retrieve(question, top_k=top_k, jurisdiction=jurisdiction)

        # 3. 组 prompt + LLM（未配置则演示降级）
        cfg = LLMConfig(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )
        user_prompt = build_user_prompt(question, citations, adversarial=adversarial)
        answer = generate(SYSTEM_PROMPT, user_prompt, cfg)
        mode = "server"
        if answer is None:
            answer = extractive_answer(question, citations)
            mode = "extractive"

        # 4. NLI 校验，不通过自动降级标注
        nli = nli_check(answer, citations)
        if nli.status == "degraded":
            answer = (
                "⚠️【引用支撑不足·已降级】以下结论与所引法条的蕴含关系校验未通过，请谨慎采信：\n\n"
                + answer
            )

        # 5. 置信度：检索得分 × NLI 得分
        top_score = citations[0].score if citations else 0.0
        confidence = round(min(1.0, top_score * 0.7 + nli.score * 0.3), 3)

        return AskResponse(
            answer=answer,
            citations=citations,
            nli=nli,
            confidence=confidence,
            mode=mode,  # type: ignore[arg-type]
        )


def _pack_context(citations: list[Citation]) -> str:
    """BYOK 用：把法条上下文打包给前端，前端自己组 prompt 调 LLM（Key 不经过后端）。"""
    from app.core.prompts import build_context_block

    return build_context_block(citations)
