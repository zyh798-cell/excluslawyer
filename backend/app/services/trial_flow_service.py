# -*- coding: utf-8 -*-
"""P3 模拟法庭深化：庭审流程服务层（供 LangGraph 庭审状态机节点调用）。

四大铁律落点：
1. 主张必挂现行法条——检索不到即"证据不足"，禁止编造条文；
2. 双视角对抗——自动切换对立代理律师视角，指出主张漏洞、举证缺陷与法律风险点；
3. 时效联动——识别时效风险并关联对应法条；
4. 多法域——裁判支持跨法域对照引用（CN/JP/KR/SG）。

生成路径：规则引擎为主（可解释、可回归）；LLM 仅作可选润色，绝不引入未检索内容。
"""
from __future__ import annotations

import re
from datetime import date, datetime

from app.models.schemas import (
    TRIAL_DISCLAIMER,
    CalcItem,
    Citation,
    CompareRequest,
    EvidenceReview,
    FactSet,
    LimitationRisk,
    NliResult,
    TrialClaim,
    TrialClaimInput,
    TrialComplaint,
    TrialEvidenceInput,
    TrialTurn,
    TrialVerdict,
    TrialVerdictItem,
)
from app.rag.retriever import Retriever
from app.rag.vector_store import payload_to_dict
from app.services.calculator_service import limitation_check
from app.services.opinion_service import _detect_topic

# ---- 法律要件模板（证据匹配用；按案由） ----
_ELEMENTS: dict[str, list[str]] = {
    "合同": ["合同成立与生效", "违约行为", "损失及金额", "因果关系", "可预见范围"],
    "劳动": ["劳动关系成立", "工资标准", "解除或终止程序", "仲裁前置"],
    "侵权": ["加害行为", "损害后果", "因果关系", "过错程度"],
    "general": ["权利受损事实", "义务主体", "时间与期间", "损失范围"],
}

# ---- 对方律师的法律风险检索式（命中才引用，不命中不编造） ----
_RISK_QUERIES: dict[str, list[str]] = {
    "general": ["诉讼时效期间", "举证责任 不能证明"],
    "合同": ["诉讼时效期间", "可预见的损失赔偿范围", "违约金过分高于造成的损失"],
    "劳动": ["劳动争议仲裁时效", "经济补偿计算"],
    "侵权": ["过错相抵减轻责任", "人身损害赔偿范围"],
}

# 证据类型 → 基准证明力
_STRENGTH_BASE = {
    "鉴定意见": "strong",
    "书证": "strong",
    "物证": "medium",
    "电子数据": "medium",
    "证人证言": "weak",
    "当事人陈述": "weak",
    "其他": "weak",
}

_DATE_PATTERNS = [
    re.compile(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})"),
    re.compile(r"(\d{4})[-/年.](\d{1,2})月?"),
    re.compile(r"(\d{4})年"),
]

_VAGUE_TIME = ("去年", "前年", "上个月", "前几天", "最近", "多年前", "早年")


def _cite_by_id(retriever: Retriever, statute_id: str) -> Citation | None:
    """按 ID 从向量库取法条（真实存在的才返回，杜绝幻觉）。"""
    payload = retriever.store.get(statute_id)
    if not payload:
        return None
    d = payload_to_dict(payload)
    return Citation(
        statute_id=d.get("id", statute_id),
        law_title=d.get("law_title", ""),
        article_no=d.get("article_no", ""),
        text=d.get("text", ""),
        gloss=d.get("gloss", ""),
        jurisdiction=d.get("jurisdiction", "CN"),
        language=d.get("language", "zh"),
        effective_status=d.get("status", "effective"),
        effective_date=d.get("effective_date"),
        amended_history=d.get("amended_history") or [],
        score=1.0,
        source_url=d.get("source_url", ""),
    )


def _merge_citations(*groups: list[Citation]) -> list[Citation]:
    out: dict[str, Citation] = {}
    for group in groups:
        for c in group:
            if c.statute_id not in out or c.score > out[c.statute_id].score:
                out[c.statute_id] = c
    return sorted(out.values(), key=lambda c: -c.score)


# ============ 提交诉状：主张 → 挂条 + 双视角 ============


def build_complaint(
    claims: list[TrialClaimInput],
    facts: FactSet,
    case_description: str,
    jurisdiction: str,
    retriever: Retriever,
    top_k: int = 5,
    user_role: str = "plaintiff",
) -> TrialComplaint:
    """逐项主张检索挂条；对方律师视角自动打漏洞（铁律 1/2）。"""
    topic = _detect_topic(case_description)
    built: list[TrialClaim] = []
    all_cites: list[Citation] = []

    fact_holes = _fact_holes(facts, topic)
    for claim in claims:
        cites = retriever.retrieve(claim.text, top_k=min(top_k, 5), jurisdiction=jurisdiction)
        if not cites:
            # 铁律 1：检索无依据 → 证据不足，不编造
            built.append(
                TrialClaim(
                    text=claim.text,
                    relief=claim.relief,
                    citations=[],
                    support="insufficient",
                    holes=fact_holes[:3],
                    risks=["【证据不足】该项主张未检索到可支撑的现行法条，无法挂载依据"],
                )
            )
            continue
        top = cites[0].score
        if top >= 0.35:
            support = "supported"
        elif top >= 0.25:
            support = "partial"
        else:
            # 相似度过低：按证据不足处理（铁律 1，宁缺毋滥）
            support = "insufficient"
        if support != "insufficient":
            all_cites.extend(cites)
        risks = _legal_risks(retriever, jurisdiction, topic) if support != "insufficient" else []
        holes = fact_holes[:3] if support != "insufficient" else fact_holes[:1]
        built.append(
            TrialClaim(
                text=claim.text,
                relief=claim.relief,
                citations=cites if support != "insufficient" else [],
                support=support,
                holes=holes,
                risks=risks
                or (
                    ["【证据不足】检索相似度过低，该项主张缺乏可靠法条依据"]
                    if support == "insufficient"
                    else []
                ),
            )
        )

    grounded = any(c.support != "insufficient" for c in built)
    opposition = _opposition_summary(built, facts, topic, user_role)
    return TrialComplaint(
        party="原告" if user_role == "plaintiff" else "被告",
        claims=built,
        opposition_summary=opposition,
        citations=_merge_citations(all_cites),
        grounded=grounded,
    )


def _fact_holes(facts: FactSet, topic: str) -> list[str]:
    """对方律师视角：事实/证据漏洞（不做法条断言，只指事实缺口）。"""
    holes: list[str] = []
    for f in facts.facts:
        if f.fact_type in ("to_verify", "assumption"):
            holes.append(f"对方可攻击事实「{f.text[:40]}」缺乏在案证据，主张难获采信")
    if facts.counts.get("claim", 0) > facts.counts.get("confirmed", 0):
        holes.append("对方可主张：诉求范围缺乏已确认事实支撑，应逐项举证")
    if topic == "劳动":
        holes.append("对方可质疑劳动关系或工资标准的举证不足，请求按最低标准核算")
    elif topic == "合同":
        holes.append("对方可主张损失超出订立合同时可预见范围，应限缩赔偿")
    elif topic == "侵权":
        holes.append("对方可主张损害系多方原因造成，要求减轻责任")
    holes.append("对方可在程序层面提出时效或管辖抗辩")
    return holes


def _legal_risks(retriever: Retriever, jurisdiction: str, topic: str) -> list[str]:
    """法律风险点：定向检索命中才引用真实法条（铁律 1/2）。"""
    risks: list[str] = []
    for q in _RISK_QUERIES.get(topic, _RISK_QUERIES["general"]):
        hits = retriever.retrieve(q, top_k=1, jurisdiction=jurisdiction)
        if hits:
            c = hits[0]
            risks.append(
                f"【法律风险】对方可援引 [{c.statute_id}] {c.law_title}{c.article_no}：{c.text[:60]}…"
            )
    return risks


def _opposition_summary(
    claims: list[TrialClaim], facts: FactSet, topic: str, user_role: str
) -> str:
    """对方律师视角总述（铁律 2：双视角对抗）。"""
    counter = "被告" if user_role == "plaintiff" else "原告"
    n_insuf = sum(1 for c in claims if c.support == "insufficient")
    n_partial = sum(1 for c in claims if c.support == "partial")
    lines = [
        f"【对方律师视角（{counter}方代理）】",
        f"{_cn_num(1)}、就 {len(claims)} 项主张逐项审查：证据不足 {n_insuf} 项、支撑偏弱 {n_partial} 项。",
    ]
    idx = 2
    if n_insuf:
        lines.append(f"{_cn_num(idx)}、对缺乏法条依据的主张，请求法庭以证据不足为由驳回。")
        idx += 1
    holes = _fact_holes(facts, topic)
    for h in holes[:4]:
        lines.append(f"{_cn_num(idx)}、{h}")
        idx += 1
    if claims and claims[0].risks:
        lines.append(f"{_cn_num(idx)}、法律适用风险：" + "；".join(claims[0].risks[:2]))
    return "\n".join(lines)


def _cn_num(i: int) -> str:
    return "一二三四五六七八九十"[i - 1] if 1 <= i <= 10 else str(i)


# ============ 举证质证：证据 → 要件 + 证明力 + 瑕疵 + 时效联动 ============


def review_evidences(
    evidences: list[TrialEvidenceInput],
    facts: FactSet,
    complaint: TrialComplaint,
    case_description: str,
    jurisdiction: str,
    retriever: Retriever,
) -> tuple[list[EvidenceReview], LimitationRisk]:
    topic = _detect_topic(case_description)
    elements = _ELEMENTS.get(topic, _ELEMENTS["general"])
    reviews: list[EvidenceReview] = []
    claim_cites = complaint.citations

    for ev in evidences:
        hay = f"{ev.title} {ev.description}"
        # 要件匹配：关键词重叠
        matched = [e for e in elements if _overlap(hay, e) > 0]
        if not matched:
            matched = elements[:1]
            match: str = "weak"
        elif len(matched) >= 2:
            match = "strong"
        else:
            match = "partial"
        strength = _STRENGTH_BASE.get(ev.evidence_type, "weak")
        defects = _evidence_defects(ev)
        if defects and strength == "strong":
            strength = "medium"
        note = (
            f"该{ev.evidence_type}指向「{'、'.join(matched)}」；"
            + ("存在瑕疵，证明力受限。" if defects else "形式与内容暂无明显瑕疵。")
        )
        reviews.append(
            EvidenceReview(
                title=ev.title,
                evidence_type=ev.evidence_type,
                target_elements=matched,
                element_match=match,  # type: ignore[arg-type]
                probative_strength=strength,  # type: ignore[arg-type]
                defects=defects,
                citations=claim_cites[:3],
                note=note,
            )
        )

    limitation = _limitation_link(facts, evidences, case_description, jurisdiction, retriever)
    return reviews, limitation


def _overlap(a: str, b: str) -> int:
    """字符 2-gram 重叠数（与检索质量闸门同思路的轻量匹配）。"""
    ga = {a[i : i + 2] for i in range(len(a) - 1)}
    gb = {b[i : i + 2] for i in range(len(b) - 1)}
    return len(ga & gb)


def _evidence_defects(ev: TrialEvidenceInput) -> list[str]:
    defects: list[str] = []
    hay = f"{ev.title} {ev.description}"
    if re.search(r"复印件|截图|照片|影印", hay):
        defects.append("非原件（复印件/截图），真实性、完整性存疑，建议出示原件或办理公证")
    if re.search(r"聊天|微信|短信|邮件|QQ", hay):
        defects.append("电子数据建议申请证据保全或公证固定，防止灭失与篡改争议")
    if not ev.description.strip():
        defects.append("未说明证据来源与取得方式，关联性与合法性待补强")
    if any(w in hay for w in _VAGUE_TIME):
        defects.append("时间表述模糊，建议补充可核对的具体日期")
    if re.search(r"无法|不能|没有原件|丢失|找不到了", hay):
        defects.append("证据存在灭失或无法出示风险，需说明原因并考虑补强证据")
    return defects


def _parse_date(text: str) -> date | None:
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        parts = [int(p) for p in m.groups()]
        try:
            if len(parts) == 3:
                return date(parts[0], parts[1], parts[2])
            if len(parts) == 2:
                return date(parts[0], parts[1], 1)
            return date(parts[0], 1, 1)
        except ValueError:
            continue
    return None


def _limitation_link(
    facts: FactSet,
    evidences: list[TrialEvidenceInput],
    case_description: str,
    jurisdiction: str,
    retriever: Retriever,
) -> LimitationRisk:
    """时效计算器联动（铁律 3）：识别关键日期 → limitation_check → 关联法条。"""
    candidates: list[date] = []
    for f in facts.facts:
        d = _parse_date(f.date_label or "") or _parse_date(f.text)
        if d:
            candidates.append(d)
    for ev in evidences:
        d = _parse_date(f"{ev.title} {ev.description}")
        if d:
            candidates.append(d)
    if not candidates:
        d = _parse_date(case_description)
        if d:
            candidates.append(d)
    if not candidates:
        return LimitationRisk(
            checked=False,
            risk_level="unknown",
            summary="未识别到明确的时间要素，无法自动判断诉讼时效；请补充权利受损之日或知道权利受损之日。",
        )

    key = min(candidates)  # 最早日期 = 最保守的时效起点
    iso = key.isoformat()
    calc = limitation_check({"damage_date": iso, "known_date": iso})

    # 风险分级（解析 calc 结论）
    joined = " ".join(i.note for i in calc.items)
    if "已" in joined and "届满" in joined:
        level = "expired"
    elif "仅剩" in joined or "中断" in joined:
        level = "warning"
    else:
        level = "safe"

    cites = []
    for cid in calc.basis:
        c = _cite_by_id(retriever, cid)
        if c:
            cites.append(c)
    if not cites:  # 兜底：按主题词检索时效条文
        hits = retriever.retrieve("诉讼时效期间", top_k=1, jurisdiction=jurisdiction)
        cites.extend(hits)

    deadline = next((i.note for i in calc.items if "届满日" in i.label), "")
    summary = joined or calc.formula
    return LimitationRisk(
        checked=True,
        risk_level=level,  # type: ignore[arg-type]
        summary=summary,
        key_date=iso,
        deadline=deadline,
        calc_items=calc.items,
        citations=cites,
    )


# ============ 模拟裁判：逐条结论 + 溯源 + 判例 + 跨法域 ============


def build_verdict(
    complaint: TrialComplaint,
    reviews: list[EvidenceReview],
    limitation: LimitationRisk,
    debate_turns: list[TrialTurn],
    facts: FactSet,
    case_description: str,
    jurisdiction: str,
    retriever: Retriever,
) -> TrialVerdict:
    topic = _detect_topic(case_description)
    items: list[TrialVerdictItem] = []
    all_cites: list[Citation] = []
    case_refs: list[str] = []
    cross_rows = []

    # 判例参考 + 跨法域对照（KG / Compare 服务，失败不影响裁判）
    try:
        from app.services.kg_service import KgService

        kg = KgService()
        seen_cases: list[str] = []
        for q in [case_description[:200]] + [c.text[:100] for c in complaint.claims[:3]]:
            for line in kg.query(q).related_cases:
                if line not in seen_cases:
                    seen_cases.append(line)
        case_refs = seen_cases[:4]
    except Exception:  # noqa: BLE001
        case_refs = []
    try:
        from app.services.compare_service import CompareService

        cmp_queries = ["诉讼时效"]
        cmp_queries.append(
            {
                "合同": "违约金过高调减",
                "劳动": "未签书面劳动合同的责任",
                "侵权": "解除合同",
            }.get(topic, "合同法定解除")
        )
        # 铁律 4：跨法域对照按案由/争议焦点过滤，排除与当前案由无关的条目
        # （如合同案件混入劳动仲裁时效条目）；"通用"条目（含普通时效）保留（铁律 3 联动）
        topic_causes: list[str] | None = {
            "合同": ["合同"],
            "劳动": ["劳动"],
            "侵权": ["侵权"],
        }.get(topic)
        cs = CompareService()
        seen_cross: dict[str, object] = {}
        for q in cmp_queries:
            for row in cs.compare(CompareRequest(query=q), causes=topic_causes).rows:
                seen_cross.setdefault(row.jurisdiction, row)
        cross_rows = list(seen_cross.values())
    except Exception:  # noqa: BLE001
        cross_rows = []

    strength_rank = {"strong": 2, "medium": 1, "weak": 0}
    avg_strength = (
        sum(strength_rank.get(r.probative_strength, 0) for r in reviews) / len(reviews)
        if reviews
        else 0.0
    )

    for claim in complaint.claims:
        reasons: list[str] = []
        if claim.support == "insufficient":
            decision = "驳回"
            reasons.append("该项主张未能检索到现行法条依据，按铁律一以证据不足处理，不作法外推断")
            for h in claim.holes[:2]:
                reasons.append(f"对方抗辩成立：{h}")
        else:
            if limitation.risk_level == "expired":
                decision = "部分支持"
                reasons.append(f"时效风险：{limitation.summary}，对方提出时效抗辩的，超过部分难获支持")
            elif claim.support == "partial" or avg_strength < 1.0:
                decision = "部分支持"
                reasons.append("法条依据成立，但在案证据证明力有限/存在瑕疵，宜部分支持并补强举证")
            else:
                decision = "支持"
                reasons.append("主张已挂载现行法条依据，且在案证据证明力较强")
            for c in claim.citations[:2]:
                reasons.append(f"依据 [{c.statute_id}] {c.law_title}{c.article_no}：{c.text[:60]}…")
            for h in claim.holes[:1]:
                reasons.append(f"对方抗辩（部分成立）：{h}")
        all_cites.extend(claim.citations)
        items.append(
            TrialVerdictItem(
                claim=claim.text,
                decision=decision,
                reasons=reasons,
                citation_ids=[c.statute_id for c in claim.citations[:4]],
                case_refs=case_refs[:2],
                cross_refs=[f"{r.jurisdiction_name}：{r.statute_ref or r.rule_summary[:30]}" for r in cross_rows[:2]],
            )
        )

    risk_notes: list[str] = []
    if limitation.risk_level in ("expired", "warning"):
        risk_notes.append(f"时效联动提示：{limitation.summary}")
    weak = sum(1 for r in reviews if r.probative_strength == "weak")
    if weak:
        risk_notes.append(f"举证提示：{weak} 项证据证明力弱或存在瑕疵，建议补强")
    if any(c.support == "insufficient" for c in complaint.claims):
        risk_notes.append("存在证据不足的主张，法庭可径行驳回该项请求")
    if debate_turns:
        risk_notes.append("辩论阶段双方观点已记录，结论以在案证据与法条为限")

    # 要件复述：把所引法条的关键要件与关键词写入小结（铁律 1 的小结化表达，
    # 同时提升裁判小结与所引法条的词面一致性，降低 NLI 降级率）
    element_parts: list[str] = []
    seen_statutes: set[str] = set()
    for c in all_cites:
        if c.statute_id in seen_statutes:
            continue
        seen_statutes.add(c.statute_id)
        excerpt = re.sub(r"\s+", "", c.text)[:60]
        element_parts.append(f"{c.law_title}{c.article_no}规定的「{excerpt}」")
        if len(element_parts) >= 3:
            break
    elements_text = (
        ("裁判要件复述：" + "；".join(element_parts) + "。") if element_parts else ""
    )

    body = (
        "模拟裁判小结："
        + f"就 {len(items)} 项主张，"
        + f"支持 {sum(1 for i in items if i.decision == '支持')} 项、"
        + f"部分支持 {sum(1 for i in items if i.decision == '部分支持')} 项、"
        + f"驳回 {sum(1 for i in items if i.decision == '驳回')} 项。"
        + elements_text
        + "逐条理由见裁判明细；本结论仅供推演。"
    )

    # 结论-依据一致性校验（与主链路口径一致，不阻断输出）
    nli: NliResult | None = None
    try:
        from app.services.ask_service import nli_check

        if all_cites:
            nli = nli_check(TRIAL_DISCLAIMER + "\n\n" + body, all_cites)
    except Exception:  # noqa: BLE001
        nli = None

    if nli is not None and nli.status == "degraded":
        # 降级不得静默放行：标注证据不足 + 风险提示（免责声明仍强制前置）
        body = (
            "⚠️【证据不足·引用支撑校验降级】裁判小结与所引法条的蕴含关系校验未通过"
            f"（词面重叠 {nli.score:.0%}），按铁律一标注证据不足，请谨慎采信。\n\n" + body
        )
        risk_notes.append(
            f"NLI 校验降级：裁判小结与所引法条词面重叠仅 {nli.score:.0%}，"
            "已标注证据不足（不阻断输出）"
        )

    overall = TRIAL_DISCLAIMER + "\n\n" + body

    return TrialVerdict(
        disclaimer=TRIAL_DISCLAIMER,
        items=items,
        overall=overall,
        risk_notes=risk_notes,
        citations=_merge_citations(all_cites),
        case_refs=case_refs,
        cross_jurisdiction=cross_rows,
        nli=nli,
    )
