"""Pydantic 领域模型。

数据层设计原则：每条法条记录固定携带 jurisdiction / language / 时效字段，
多法域（中/日/韩/新）只是数据差异，不改代码结构。
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

Jurisdiction = Literal["CN", "JP", "KR", "SG", "OTHER"]
EffectiveStatus = Literal["effective", "amended", "repealed", "unknown"]


class Statute(BaseModel):
    """一条成文法条（或判例要旨）。"""

    id: str = Field(..., description="全局唯一 ID，如 CN-MINFA-465")
    jurisdiction: Jurisdiction = "CN"
    language: str = "zh"  # 原文语言：zh / ja / ko / en
    law_title: str = Field(..., description="法律名称，如《中华人民共和国民法典》")
    law_level: str = Field(
        default="法律",
        description="效力位阶：宪法/法律/行政法规/司法解释/判例",
    )
    article_no: str = Field(..., description="条文号，如 '第五百七十七条'")
    text: str = Field(..., description="法条原文（保留当地语言）")
    gloss: str = Field(default="", description="中文释义（非中文法域用）")
    effective_date: Optional[str] = None  # 生效日期 ISO
    expiry_date: Optional[str] = None  # 失效日期 ISO
    amended_history: list[str] = Field(
        default_factory=list, description="修订历史，如 ['2020-05-28 通过', '2021-01-01 施行']"
    )
    status: EffectiveStatus = "effective"
    source_url: str = Field(default="", description="官方法规源链接")
    topics: list[str] = Field(default_factory=list)
    revisions: list[dict] = Field(
        default_factory=list,
        description="版本沿革 diff：[{date, version, change_summary, old_excerpt, new_excerpt}]",
    )


class Citation(BaseModel):
    """回答中挂载的一条引用（带时效状态）。"""

    statute_id: str
    law_title: str
    article_no: str
    text: str
    gloss: str = ""
    jurisdiction: Jurisdiction = "CN"
    language: str = "zh"
    effective_status: EffectiveStatus = "effective"
    effective_date: Optional[str] = None
    amended_history: list[str] = Field(default_factory=list)
    revisions: list[dict] = Field(
        default_factory=list, description="版本沿革 diff（时效追踪用）"
    )
    score: float = 0.0
    source_url: str = ""


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    jurisdiction: Jurisdiction = "CN"
    language: str = "zh"
    top_k: int = 5
    # 双视角对抗（P0 先出单视角结论，adversarial=True 时附对方律师视角找漏洞）
    adversarial: bool = False


class RetrieveRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    jurisdiction: Jurisdiction = "CN"
    language: str = "zh"
    top_k: int = 5


class NliResult(BaseModel):
    status: Literal["pass", "degraded", "unverified"]
    score: float = 0.0
    reason: str = ""


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    nli: NliResult
    confidence: float = 0.0
    mode: Literal["server", "extractive"] = "server"
    disclaimers: list[str] = [
        "本回答不构成法律意见，仅供参考；重大决策请咨询执业律师。",
        "法条时效状态以官方法规库最新版本为准。",
    ]


class RetrieveResponse(BaseModel):
    citations: list[Citation]
    context_pack: str = Field(
        default="", description="拼好的法条上下文（BYOK 前端拿它自己组 prompt 调 LLM）"
    )


class VerifyRequest(BaseModel):
    question: str = ""
    answer: str
    citations: list[Citation]


class FeedbackRequest(BaseModel):
    question: str
    answer: str
    verdict: Literal["useful", "wrong", "outdated"]  # 有用 / 有误 / 引用过时
    note: str = ""


# ============ P0-2 案件事实结构化 ============

FactType = Literal["confirmed", "to_verify", "assumption", "claim"]


class Fact(BaseModel):
    """一条结构化事实。"""

    text: str = Field(..., description="事实原文片段")
    fact_type: FactType = Field(
        ..., description="四分类：已确认/待核实/假设/主张"
    )
    date_label: Optional[str] = Field(
        default=None, description="从原文抽取的时间标签，如 '2024-03'、'去年'"
    )


class TimelineCard(BaseModel):
    """时间线卡片（按时间排序）。"""

    date_label: str
    sort_key: str = Field(
        default="9999-99-99", description="用于排序的近似日期，无法确定时间的排最后"
    )
    event_text: str
    fact_type: FactType


class FactSet(BaseModel):
    """案件事实结构化结果。"""

    facts: list[Fact]
    timeline: list[TimelineCard]
    counts: dict[str, int] = Field(
        default_factory=dict, description="各类型事实数量统计"
    )


# ============ P0-3 五段式法律意见书 ============


class OpinionSection(BaseModel):
    """意见书的一个段落。"""

    title: str = Field(..., description="如：一、事实认定")
    content: str
    citation_ids: list[str] = Field(
        default_factory=list, description="本段引用的 CIT-id 列表"
    )


class OpinionRequest(BaseModel):
    narrative: str = Field(
        ..., min_length=1, max_length=8000, description="案情描述（不可信数据）"
    )
    jurisdiction: Jurisdiction = "CN"
    language: str = "zh"
    top_k: int = 5
    adversarial: bool = False  # True 时附加"对方律师视角"攻防推演段


class OpinionResponse(BaseModel):
    sections: list[OpinionSection] = Field(
        description="五段式（对抗模式下六段）：事实认定/法律适用/风险等级/行动建议/限制提示[/对方律师视角]"
    )
    fact_set: FactSet
    citations: list[Citation]
    risk_level: Literal["high", "medium", "low"] = "medium"
    risk_reasons: list[str] = Field(default_factory=list)
    nli: NliResult
    mode: Literal["server", "template"] = "template"
    disclaimers: list[str] = [
        "本意见书不构成法律意见，仅供参考；重大决策请咨询执业律师。",
        "法条时效状态以官方法规库最新版本为准。",
    ]


# ============ P1-5 合同风险扫描 ============


class ContractClause(BaseModel):
    """合同条款 + 风险标注。"""

    index: int
    heading: str
    text: str
    risk_level: Literal["risky", "warn", "ok"] = Field(
        ..., description="risky=红 / warn=黄 / ok=绿"
    )
    risk_type: str = ""
    explanation: str = ""
    suggestion: str = ""
    citation_ids: list[str] = Field(default_factory=list)


class ContractScanRequest(BaseModel):
    text: str = Field(default="", max_length=50000, description="合同文本；与 pdf_base64 二选一")
    pdf_base64: str = Field(default="", description="PDF 的 base64 编码（可选）")
    jurisdiction: Jurisdiction = "CN"


class ContractScanResponse(BaseModel):
    clauses: list[ContractClause]
    summary: dict[str, int] = Field(
        default_factory=dict, description="{risky, warn, ok} 计数"
    )
    citations: list[Citation]
    disclaimers: list[str] = [
        "风险标注基于规则引擎，仅供参考，不构成法律意见；重大合同请务必由律师审核。",
    ]


# ============ P1-6 类案参考 ============


class CaseRecord(BaseModel):
    """脱敏裁判文书记录。"""

    id: str
    title: str
    cause: str = Field(..., description="案由")
    court: str = ""
    date: str = ""
    keywords: list[str] = Field(default_factory=list)
    facts_summary: str = ""
    result: Literal["支持", "部分支持", "驳回"] = "支持"
    amount_claimed: float = 0
    amount_supported: float = 0
    holding: str = Field(default="", description="裁判要旨")


class CaseSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    cause: str = Field(default="", description="按案由过滤（可选）")
    top_k: int = 5


class CaseSearchResponse(BaseModel):
    cases: list[CaseRecord]
    result_distribution: dict[str, int] = Field(
        default_factory=dict, description="裁判结果分布：{支持, 部分支持, 驳回}"
    )
    support_rate: float = Field(
        default=0.0, description="（支持+部分支持）占全部匹配案件比例"
    )
    disclaimers: list[str] = [
        "类案仅供参考，个案事实差异可能导致裁判结果不同；不构成对本案结果的承诺。",
        "案例数据为脱敏示例样本，正式版接入官方裁判文书公开渠道。",
    ]


# ============ P1-7 法条时效追踪 ============


class StatuteRevision(BaseModel):
    date: str
    version: str
    change_summary: str
    old_excerpt: str = ""
    new_excerpt: str = ""


class StatuteTimeline(BaseModel):
    statute_id: str
    law_title: str
    article_no: str
    current_text: str
    status: EffectiveStatus
    effective_date: Optional[str] = None
    amended_history: list[str]
    revisions: list[StatuteRevision]
    advice: str = Field(
        default="", description="时效提示：如'引用的是旧版本，注意条文变化'"
    )


# ============ P2-9 模拟法庭 ============


class TrialTurn(BaseModel):
    role: Literal["user", "opponent", "judge"]
    round: int
    content: str


class TrialSession(BaseModel):
    id: str
    user_role: Literal["plaintiff", "defendant"] = "plaintiff"
    case_description: str = ""
    fact_set: FactSet
    citations: list[Citation] = Field(default_factory=list)
    round: int = 1
    turns: list[TrialTurn] = Field(default_factory=list)
    status: Literal["ongoing", "closed"] = "ongoing"


class TrialStartRequest(BaseModel):
    case_description: str = Field(..., min_length=1, max_length=8000)
    user_role: Literal["plaintiff", "defendant"] = "plaintiff"
    jurisdiction: Jurisdiction = "CN"


class TrialTurnRequest(BaseModel):
    session_id: str
    user_statement: str = Field(..., min_length=1, max_length=4000)


# ============ P2-10 法律知识图谱 ============


class KgNode(BaseModel):
    id: str
    node_type: str = Field(..., description="concept/element/duty/statute/period")
    name: str


class KgPath(BaseModel):
    nodes: list[KgNode]
    relations: list[str]


class KgQueryResponse(BaseModel):
    question: str
    matched_node: Optional[KgNode] = None
    paths: list[KgPath] = Field(default_factory=list)
    answer: str
    statute_ids: list[str] = Field(default_factory=list)
    related_cases: list[str] = Field(default_factory=list, description="关联判例（名称+引用+要旨）")
    backend: str = Field(default="memory", description="图后端：memory / neo4j")
    disclaimer: str = "知识图谱为结构化概览，具体适用请核对法条原文；不构成法律意见。"


# ============ P2-11 赔偿计算器 ============


class CalcRequest(BaseModel):
    calc_type: Literal[
        "economic_compensation",  # 经济补偿（劳动合同法47）
        "double_wage",  # 二倍工资（劳动合同法82）
        "personal_injury",  # 人身损害赔偿（民法典1179）
        "liquidated_damages",  # 违约金合理性参考（民法典585）
        "limitation_check",  # 诉讼时效判断（民法典188）
    ]
    params: dict = Field(default_factory=dict, description="计算参数，见各计算器说明")


class CalcItem(BaseModel):
    label: str
    amount: float | None = None
    note: str = ""


class CalcResponse(BaseModel):
    calc_type: str
    total: float | None = None
    items: list[CalcItem]
    formula: str
    basis: list[str] = Field(default_factory=list, description="法条依据（CIT-id）")
    caveats: list[str] = Field(default_factory=list)
    disclaimer: str = "计算结果为参考估算，不构成法律意见；个案以证据与裁判为准。"


# ============ P2-12 多法域对比 ============


class JurisdictionRule(BaseModel):
    jurisdiction: Jurisdiction
    jurisdiction_name: str
    rule_summary: str
    statute_ref: str = ""
    language: str = "zh"
    original_excerpt: str = ""
    gloss: str = ""


class CompareRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    jurisdictions: list[str] = Field(default_factory=lambda: ["CN", "JP", "KR", "SG"])


class CompareResponse(BaseModel):
    topic: str
    rows: list[JurisdictionRule]
    takeaway: str = ""
    disclaimer: str = (
        "跨法域对比为规则概要，各法域具体适用须以官方法源为准（CN: flk.npc.gov.cn / "
        "JP: e-Gov / KR: law.go.kr / SG: sso.agc.gov.sg）；不构成任何法域的法律意见。"
    )


# ============ LangGraph 咨询状态机 ============


class ConsultGraphRequest(BaseModel):
    """状态机执行请求（thread_id + resume_decision 用于中断恢复）。"""

    question: str = Field(..., min_length=1, max_length=4000)
    jurisdiction: Jurisdiction = "CN"
    language: str = "zh"
    top_k: int = 5
    adversarial: bool = False
    interrupt_on_degraded: bool = False  # NLI 降级时挂起等待人工裁决
    thread_id: str | None = None  # 恢复执行时传入上次的 thread_id
    resume_decision: str | None = None  # 人工裁决：approve / reject


class ConsultGraphResponse(BaseModel):
    status: Literal["refused", "insufficient_evidence", "degraded", "done"]
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    facts: Optional[FactSet] = None
    nli: Optional[NliResult] = None
    confidence: float = 0.0
    trace: list[str] = Field(default_factory=list)
    adversarial_notes: Optional[str] = None
    answer_mode: Optional[str] = None
    interrupted: bool = False  # True=停在 human_confirm 等待 resume_decision
    thread_id: Optional[str] = None


# ============ P3 模拟法庭深化（庭审状态机） ============

TRIAL_DISCLAIMER = (
    "【仅法律推演，不具备法律效力，不可用于真实诉讼，请咨询执业律师】"
)

TrialPhase = Literal[
    "create_case",   # 案件创建
    "fix_facts",     # 事实固定
    "file_complaint",  # 提交诉状
    "evidence_review",  # 举证质证
    "debate",        # 法庭辩论
    "closing",       # 总结陈词
    "adjudicate",    # 模拟裁判
]


class TrialClaimInput(BaseModel):
    """诉状主张录入。"""

    text: str = Field(..., min_length=1, max_length=1000, description="主张内容")
    relief: str = Field(default="", max_length=300, description="诉求（金额/行为）")


class TrialEvidenceInput(BaseModel):
    """证据录入。"""

    title: str = Field(..., min_length=1, max_length=200)
    evidence_type: str = Field(default="书证", description="书证/物证/电子数据/证人证言/鉴定意见/当事人陈述/其他")
    description: str = Field(default="", max_length=2000)


class TrialClaim(BaseModel):
    """一项主张的审理状态（铁律 1：必挂现行法条，否则证据不足）。"""

    text: str
    relief: str = ""
    citations: list[Citation] = Field(default_factory=list)
    support: Literal["supported", "partial", "insufficient"] = "insufficient"
    holes: list[str] = Field(default_factory=list, description="对方律师视角漏洞（铁律 2）")
    risks: list[str] = Field(default_factory=list, description="法律风险点（检索支撑）")


class TrialComplaint(BaseModel):
    """诉状 + 双视角对抗结果。"""

    party: str = "原告"
    claims: list[TrialClaim] = Field(default_factory=list)
    opposition_summary: str = Field(default="", description="对方律师视角总述")
    citations: list[Citation] = Field(default_factory=list)
    grounded: bool = Field(default=True, description="是否至少一项主张有法条支撑")


class EvidenceReview(BaseModel):
    """举证质证结果：证据 → 法律要件匹配 + 证明力 + 瑕疵。"""

    title: str
    evidence_type: str = "书证"
    target_elements: list[str] = Field(default_factory=list, description="对应的法律要件")
    element_match: Literal["strong", "partial", "weak"] = "weak"
    probative_strength: Literal["strong", "medium", "weak"] = "weak"
    defects: list[str] = Field(default_factory=list, description="证据瑕疵")
    citations: list[Citation] = Field(default_factory=list)
    note: str = ""


class LimitationRisk(BaseModel):
    """时效计算器联动结果（铁律 3）。"""

    checked: bool = False
    risk_level: Literal["unknown", "safe", "warning", "expired"] = "unknown"
    summary: str = ""
    key_date: str = Field(default="", description="知道或应当知道权利受损之日")
    deadline: str = Field(default="", description="时效届满日")
    calc_items: list[CalcItem] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class TrialEvent(BaseModel):
    """滚动庭审记录的一条事件。"""

    phase: str = ""
    kind: str = Field(default="info", description="trace/turn/evidence/limitation/verdict/info")
    role: str = Field(default="", description="user/opponent/judge/clerk/system")
    title: str = ""
    content: str = ""
    citation_ids: list[str] = Field(default_factory=list)


class TrialVerdictItem(BaseModel):
    """裁判结论逐条：支持/驳回理由 + 法条溯源。"""

    claim: str
    decision: Literal["支持", "部分支持", "驳回"] = "驳回"
    reasons: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    case_refs: list[str] = Field(default_factory=list, description="判例参考")
    cross_refs: list[str] = Field(default_factory=list, description="跨法域对照引用")


class TrialVerdict(BaseModel):
    """模拟裁判书（强制前置免责）。"""

    disclaimer: str = TRIAL_DISCLAIMER
    items: list[TrialVerdictItem] = Field(default_factory=list)
    overall: str = ""
    risk_notes: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    case_refs: list[str] = Field(default_factory=list)
    cross_jurisdiction: list[JurisdictionRule] = Field(default_factory=list)
    nli: Optional[NliResult] = None


class TrialGraphStartRequest(BaseModel):
    """庭审状态机启动：案件 + 诉状主张 + 证据清单。"""

    case_description: str = Field(..., min_length=1, max_length=8000)
    user_role: Literal["plaintiff", "defendant"] = "plaintiff"
    jurisdiction: Jurisdiction = "CN"
    language: str = "zh"
    top_k: int = 5
    claims: list[TrialClaimInput] = Field(default_factory=list)
    evidences: list[TrialEvidenceInput] = Field(default_factory=list)
    interrupt_on_limitation: bool = Field(
        default=False, description="时效风险高时挂起人工确认（interrupt 恢复）"
    )
    session_id: str | None = Field(default=None, description="复用既有会话 ID（可选）")


class TrialGraphStepRequest(BaseModel):
    """庭审推进一步（中断恢复入口）。"""

    session_id: str
    statement: str | None = Field(default=None, max_length=4000, description="辩论发言（debate 阶段）")
    closing: str | None = Field(default=None, max_length=4000, description="总结陈词（closing 阶段）")
    decision: str | None = Field(default=None, description="人工确认：approve / reject")


class TrialGraphResponse(BaseModel):
    """庭审状态机响应（会话快照，可持久化恢复）。"""

    session_id: str
    phase: str = "create_case"
    status: Literal["refused", "insufficient_evidence", "awaiting_input", "done"] = "awaiting_input"
    pending: str = Field(default="", description="下一步待用户输入的提示（awaiting_input 时）")
    interrupted: bool = False
    case_description: str = ""
    user_role: str = "plaintiff"
    jurisdiction: str = "CN"
    trace: list[str] = Field(default_factory=list)
    facts: Optional[FactSet] = None
    complaint: Optional[TrialComplaint] = None
    evidence_reviews: list[EvidenceReview] = Field(default_factory=list)
    limitation: Optional[LimitationRisk] = None
    debate_turns: list[TrialTurn] = Field(default_factory=list)
    closing_text: str = ""
    verdict: Optional[TrialVerdict] = None
    events: list[TrialEvent] = Field(default_factory=list, description="滚动庭审记录")
    disclaimers: list[str] = Field(default_factory=lambda: [TRIAL_DISCLAIMER])
