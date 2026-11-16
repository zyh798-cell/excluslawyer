"""P1-7 法条时效追踪：版本沿革 + 新旧修订 diff + 引用时效建议。

用途：旧法引用自动提示修订差异——回答里挂的引用如果带 revisions，
溯源面板展示新旧对比；status=amended/repealed 时给出硬性提示。
"""

from app.models.schemas import StatuteRevision, StatuteTimeline


def build_statute_timeline(statute_id: str, payload: dict) -> StatuteTimeline:
    """从向量库 payload 组装法条时效线。"""
    revisions = [StatuteRevision(**r) for r in payload.get("revisions", [])]
    status = payload.get("status", "unknown")

    if status == "repealed":
        advice = "⚠️ 该条文已废止，不得作为现行法律依据引用；请查找替代条文。"
    elif status == "amended" or revisions:
        advice = (
            "⚠️ 该条文存在修订历史，引用时务必核对适用版本："
            "行为发生在新法施行前的，可能适用旧法（从旧兼从轻/有利于当事人原则）。"
            "下方 diff 展示新旧文本差异。"
        )
    elif status == "unknown":
        advice = "该条文时效状态未知，请到官方法规源核对后引用。"
    else:
        advice = "该条文现行有效；引用时仍请以官方法规库最新文本为准。"

    return StatuteTimeline(
        statute_id=statute_id,
        law_title=payload.get("law_title", ""),
        article_no=payload.get("article_no", ""),
        current_text=payload.get("text", ""),
        status=status if status in ("effective", "amended", "repealed", "unknown") else "unknown",
        effective_date=payload.get("effective_date"),
        amended_history=payload.get("amended_history", []),
        revisions=revisions,
        advice=advice,
    )
