"""双层 LLM 封装。

- BYOK 模式：Key 只存浏览器 localStorage，前端直连 LLM 服务商，本模块不参与。
- 服务端演示模式：用环境变量配置的 OpenAI 兼容端点（本地 Qwen2.5 / 云端任意兼容 API）。
- 未配置 Key → 返回 None，由调用方降级为"只引法条、不生成自由文本"的演示模式。
"""

import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout: int = 60

    @property
    def available(self) -> bool:
        return bool(self.base_url)

    @classmethod
    def from_settings(cls) -> "LLMConfig":
        """从全局配置构造（服务端演示模式；BYOK 不走这里）。"""
        from app.config import settings

        return cls(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )


def generate(system: str, user: str, cfg: LLMConfig, temperature: float = 0.2) -> str | None:
    """调 OpenAI 兼容 /chat/completions。失败返回 None（调用方降级）。"""
    if not cfg.available:
        return None
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg.model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=cfg.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001 —— 任何失败都走降级，不让接口 500
        logger.warning("LLM 调用失败，进入演示降级模式: %s", exc)
        return None


def extractive_answer(question: str, citations: list) -> str:
    """演示模式兜底：不生成自由文本，只把检索到的法条原样呈现。

    这就是铁律 1 的兜底实现——宁可"证据不足"，绝不幻觉。
    """
    if not citations:
        return (
            "【证据不足】\n"
            "本次检索未能在知识库中找到与问题直接对应的现行有效法条，"
            "因此不提供法律结论（防止幻觉）。\n"
            "建议：补充关键事实（时间、金额、合同条款、当事人身份）后重试，"
            "或改用更具体的法律术语检索（如“违约金 过高 调整”）。\n\n"
            "免责声明：本回答不构成法律意见。"
        )
    lines = [
        "【演示模式·检索结果】未配置 LLM，以下为知识库命中的现行法条原文，不做任何自由生成：",
        f"问题：{question}",
        "",
    ]
    for c in citations:
        lines.append(f"· [{c.law_title} {c.article_no}]（时效：{c.effective_status}）")
        lines.append(f"  {c.text}")
        if c.amended_history:
            lines.append(f"  修订历史：{'；'.join(c.amended_history)}")
        lines.append("")
    lines.append("免责声明：本回答不构成法律意见，仅供参考。")
    return "\n".join(lines)
