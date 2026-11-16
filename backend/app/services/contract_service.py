"""P1-5 合同风险扫描：条款切分 → 红黄绿风险规则 → 挂载法条 → 修改建议。

- risky（红）：条款可能无效/严重失衡，必须改
- warn（黄）：条款模糊或有隐患，建议改
- ok（绿）：未发现风险模式

规则引擎透明可解释：每条命中给出风险类型、理由、修改建议、对应法条。
LLM 不参与判定（P1 规则版），保证确定性与可测试性。
"""

import re
from dataclasses import dataclass, field

from app.models.schemas import Citation, ContractClause, ContractScanResponse

# ---------- 条款切分 ----------

# 中文合同常见条标题：第X条 / 一、 / 1. / （一）
_CLAUSE_HEAD = re.compile(
    r"(?m)^(第[一二三四五六七八九十百千零\d]+条[^\n]{0,30}|[一二三四五六七八九十]+、[^\n]{0,30}|\d+[.、][^\n]{0,30}|（[一二三四五六七八九十\d]+）[^\n]{0,30})"
)


def split_clauses(text: str) -> list[tuple[str, str]]:
    """把合同文本切成 [(标题, 正文)] 列表；切不动就按段落兜底。"""
    text = text.strip()
    if not text:
        return []
    matches = list(_CLAUSE_HEAD.finditer(text))
    if len(matches) < 2:
        # 兜底：按空行/句号段落切
        paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
        return [(f"段落{i+1}", p) for i, p in enumerate(paras)]
    clauses: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            clauses.append((m.group(1).strip(), body))
    return clauses


# ---------- 风险规则 ----------


@dataclass
class RiskRule:
    rule_id: str
    severity: str  # risky=红 / warn=黄
    risk_type: str
    pattern: re.Pattern
    explanation: str
    suggestion: str
    statute_query: str = ""  # 用于检索对应法条的查询词


RULES: list[RiskRule] = [
    # ===== 红：可能无效 / 严重失衡 =====
    RiskRule(
        rule_id="waiver-injury",
        severity="risky",
        risk_type="人身损害免责无效",
        pattern=re.compile(r"(造成|致).{0,6}(人身|身体|伤害|伤亡).{0,10}(免责|不负责|不承担|免除)|免除.{0,8}(人身|伤害|伤亡)"),
        explanation="免除造成对方人身损害责任的免责条款依法无效，写了也不产生效力，还暴露缔约诚意问题。",
        suggestion="删除该免责表述。人身损害赔偿责任是法定责任，不能通过约定免除（民法典第五百零六条）。",
        statute_query="免责条款 人身损害 无效",
    ),
    RiskRule(
        rule_id="waiver-intentional",
        severity="risky",
        risk_type="故意/重大过失免责无效",
        pattern=re.compile(r"(故意|重大过失).{0,12}(免责|不负责|不承担|免除)|(免责|不负责).{0,12}(故意|重大过失)"),
        explanation="因故意或者重大过失造成对方财产损失的免责条款无效。",
        suggestion="删除对故意/重大过失情形的免责约定（民法典第五百零六条）。",
        statute_query="免责条款 故意 重大过失 无效",
    ),
    RiskRule(
        rule_id="exclude-main-right",
        severity="risky",
        risk_type="排除对方主要权利",
        pattern=re.compile(r"排除.{0,6}(主要)?权利|限制.{0,6}(主要)?权利|不得(提出|提起|主张|申请)(异议|抗辩|诉讼|仲裁|鉴定)|放弃(诉权|起诉|仲裁)"),
        explanation="格式条款排除/限制对方主要权利的，该条款无效；约定剥夺诉权、仲裁权的表述不受法律保护。",
        suggestion="删除排除对方主要权利的表述；争议解决方式应提供协商、调解、仲裁、诉讼等合法路径（民法典第四百九十七条）。",
        statute_query="格式条款 排除主要权利 无效",
    ),
    RiskRule(
        rule_id="unilateral-control",
        severity="risky",
        risk_type="单方解释/变更权",
        pattern=re.compile(r"(最终|单方|独家)(解释|解释权|变更|修改|调整)权|随时(单方)?(变更|修改|解除|终止)(?!.*协商)"),
        explanation="保留单方最终解释权或任意变更权的条款违背公平原则，可能被认定无效。",
        suggestion="改为双方协商一致变更；如需调整机制，明确触发条件、通知期限和补偿安排（民法典第四百九十六、四百九十七条）。",
        statute_query="格式条款 公平原则 单方变更",
    ),
    RiskRule(
        rule_id="unlimited-liability",
        severity="risky",
        risk_type="无限责任条款",
        pattern=re.compile(r"(一切|任何|全部|所有)(损失|责任|后果|风险).{0,10}(均由|由.{0,6}承担|承担)"),
        explanation="让一方承担'一切/任何损失'的责任范围无限扩大，权利义务明显失衡，存在被认定无效或调减的风险。",
        suggestion="将责任范围限定为直接损失，并设置上限（如合同金额的一定比例），排除间接损失须明示且公平（民法典第四百九十七条）。",
        statute_query="格式条款 加重对方责任 无效",
    ),
    RiskRule(
        rule_id="blank-clause",
        severity="risky",
        risk_type="空白条款风险",
        pattern=re.compile(r"（\s{2,}）|_{4,}|：\s*$|：\s*（\s*）"),
        explanation="条款留白（空白填写处）在签约后可能被单方补填，引发争议且举证困难。",
        suggestion="填写完整后再签署；空白处划线注销并由双方签章确认，切勿签署留白合同。",
        statute_query="合同 签署 空白 举证",
    ),
    # ===== 黄：模糊 / 隐患 =====
    RiskRule(
        rule_id="penalty-high",
        severity="warn",
        risk_type="违约金过高",
        pattern=re.compile(
            r"(每日|每天|按日).{0,16}(违约金|罚息|滞纳金)"
            r"|(违约金|罚息|滞纳金).{0,20}(日万分之|每日|每天|千分之|万分之)"
            r"|千分之[三四五六七八九]|万分之[五六七八九]|百分之[三四五六七八九十]"
        ),
        explanation="违约金约定过分高于实际损失的，对方可请求法院或仲裁机构适当减少；过高的约定未必能全额获得支持。",
        suggestion="违约金建议与可能损失相当（司法实践常参考 LPR 的 1.3-1.5 倍或损失的 30%）；约定损失赔偿计算方法更稳妥（民法典第五百八十五条）。",
        statute_query="违约金 过高 调减",
    ),
    RiskRule(
        rule_id="deposit-over-20",
        severity="warn",
        risk_type="定金超过20%",
        pattern=re.compile(r"定金.{0,20}[3-9]\d%|定金.{0,20}百分之[三四五六七八九十]"),
        explanation="定金数额不得超过主合同标的额的 20%，超过部分不产生定金效力。",
        suggestion="定金比例调至合同金额 20% 以内；超出部分可改列为预付款并写明其性质（民法典第五百八十六条）。",
        statute_query="定金 百分之二十 上限",
    ),
    RiskRule(
        rule_id="vague-terms",
        severity="warn",
        risk_type="模糊表述",
        pattern=re.compile(r"尽快|合理(期间|期限|时间|费用)|及时|视情况|相应(的)?(补偿|调整|处理)|必要时|原则上"),
        explanation="'尽快/合理期间/及时'等模糊表述无客观标准，履行中极易产生争议。",
        suggestion="全部改为可量化标准：明确天数、金额、计算方式或引用的客观标准（如'收到发票后 15 个工作日内'）。",
        statute_query="合同 履行 期限 明确",
    ),
    RiskRule(
        rule_id="perpetual-confidentiality",
        severity="warn",
        risk_type="保密期限无限",
        pattern=re.compile(r"(永久|无限期|无期限).{0,8}(保密|竞业|不披露)|保密.{0,10}(永久|无限期|无期限)"),
        explanation="永久保密/竞业义务期限过长，超出合理范围的部分可能不被支持。",
        suggestion="保密期限建议 2-5 年（按商业秘密生命周期），竞业限制期限不超过 2 年且需支付补偿（劳动合同法第二十四条）。",
        statute_query="竞业限制 期限 补偿",
    ),
    RiskRule(
        rule_id="non-compete-no-comp",
        severity="warn",
        risk_type="竞业限制无补偿",
        pattern=re.compile(r"竞业(限制|禁止|条款)(?!.{0,30}(补偿|补偿金|经济补偿))"),
        explanation="约定竞业限制但未约定经济补偿的，劳动者履行后可主张补偿；标准不明易生纠纷。",
        suggestion="明确竞业限制补偿金标准（不低于离职前 12 个月平均工资的 30%）、支付方式与期限（劳动合同法第二十三条）。",
        statute_query="竞业限制 经济补偿 标准",
    ),
    RiskRule(
        rule_id="auto-renew",
        severity="warn",
        risk_type="自动续约陷阱",
        pattern=re.compile(r"自动续(约|期|签)|期满前.{0,12}未(提出|通知).{0,12}(续|延)"),
        explanation="自动续约条款使合同在你无意识下延续，可能持续产生付费义务。",
        suggestion="改为到期自然终止，或续约须双方书面确认；如保留自动续约，须约定单方不续约的便捷退出方式。",
        statute_query="合同 续约 终止",
    ),
    RiskRule(
        rule_id="oral-modification",
        severity="warn",
        risk_type="口头变更效力",
        pattern=re.compile(r"口头(协议|承诺|变更|约定).{0,12}(有效|生效|具有)|微信.{0,8}(承诺|约定).{0,12}(有效|生效)"),
        explanation="口头/微信约定的变更发生争议时举证困难；'口头承诺有效'的表述并不能解决举证问题。",
        suggestion="任何变更均以双方签署的书面补充协议为准，并在合同中明确书面形式要求（民法典第五百四十三条）。",
        statute_query="合同变更 书面形式",
    ),
    RiskRule(
        rule_id="acceptance-vague",
        severity="warn",
        risk_type="验收标准缺失",
        pattern=re.compile(r"验收合格|验收(通过|完成)(?!.{0,20}(标准|明细|规范|清单))"),
        explanation="仅约定'验收合格'而无客观标准，验收结论完全取决于一方主观判断。",
        suggestion="附验收标准清单/样品封存/第三方检测机构约定，并明确验收期限与视为验收通过的规则。",
        statute_query="承揽 验收 标准 质量",
    ),
    RiskRule(
        rule_id="payment-vague",
        severity="warn",
        risk_type="付款条件模糊",
        pattern=re.compile(r"(款项|费用|报酬).{0,12}另行(商定|协商|约定)|付款.{0,8}(另行|之后再说|待定)|价格.{0,8}(待定|另行)"),
        explanation="核心对价条款留待'另行商定'，合同主要条款不明确，可能影响合同成立与履行。",
        suggestion="签署前补齐金额、币种、支付节点、发票类型；确实无法确定的，明确暂定价与最终结算机制。",
        statute_query="合同 价款 报酬 明确",
    ),
]


@dataclass
class RuleHit:
    rule: RiskRule
    matched_text: str = ""


@dataclass
class ClauseAnnotation:
    index: int
    heading: str
    text: str
    severity: str  # risky / warn / ok
    hits: list[RuleHit] = field(default_factory=list)


def annotate_clause(index: int, heading: str, body: str) -> ClauseAnnotation:
    ann = ClauseAnnotation(index=index, heading=heading, text=body, severity="ok")
    for rule in RULES:
        m = rule.pattern.search(body)
        if m:
            ann.hits.append(RuleHit(rule=rule, matched_text=m.group(0)))
            if rule.severity == "risky":
                ann.severity = "risky"  # 红优先于黄
            elif ann.severity != "risky":
                ann.severity = "warn"
    return ann


class ContractScanService:
    def __init__(self, retriever):
        self.retriever = retriever
        self._cite_cache: dict[str, list[Citation]] = {}

    def _citations_for_rule(self, rule: RiskRule) -> list[Citation]:
        """按规则的法条查询词检索引用（缓存，避免重复检索）。"""
        if not rule.statute_query:
            return []
        if rule.rule_id in self._cite_cache:
            return self._cite_cache[rule.rule_id]
        cites = self.retriever.retrieve(rule.statute_query, top_k=2)
        self._cite_cache[rule.rule_id] = cites
        return cites

    def scan(self, text: str) -> ContractScanResponse:
        clauses = split_clauses(text)
        annotations = [annotate_clause(i, h, b) for i, (h, b) in enumerate(clauses)]

        out_clauses: list[ContractClause] = []
        all_cites: dict[str, Citation] = {}
        summary = {"risky": 0, "warn": 0, "ok": 0}

        for ann in annotations:
            summary[ann.severity] += 1
            citation_ids: list[str] = []
            explanations: list[str] = []
            suggestions: list[str] = []
            risk_types: list[str] = []
            for hit in ann.hits:
                risk_types.append(hit.rule.risk_type)
                explanations.append(f"【{hit.rule.risk_type}】命中「{hit.matched_text}」——{hit.rule.explanation}")
                suggestions.append(hit.rule.suggestion)
                for c in self._citations_for_rule(hit.rule):
                    all_cites[c.statute_id] = c
                    if c.statute_id not in citation_ids:
                        citation_ids.append(c.statute_id)

            out_clauses.append(
                ContractClause(
                    index=ann.index,
                    heading=ann.heading,
                    text=ann.text,
                    risk_level=ann.severity,  # type: ignore[arg-type]
                    risk_type="、".join(dict.fromkeys(risk_types)),
                    explanation="\n".join(explanations) if explanations else "未命中已知风险模式。",
                    suggestion="\n".join(dict.fromkeys(suggestions)) if suggestions else "条款表述未见明显风险，仍建议结合商业背景整体审查。",
                    citation_ids=citation_ids,
                )
            )

        return ContractScanResponse(
            clauses=out_clauses,
            summary=summary,
            citations=list(all_cites.values()),
        )


def extract_text_from_pdf(data: bytes) -> str:
    """PDF 文本抽取（轻量 pypdf；未安装时抛错并给出安装提示）。"""
    try:
        import io

        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "未安装 PDF 解析依赖。请执行：pip install pypdf；或直接把合同文本粘贴到输入框。"
        ) from exc
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)
