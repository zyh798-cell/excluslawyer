"""P2-9 模拟法庭：多智能体对抗推演沙盘。

角色：用户（原告/被告任一方）× 对方律师 × 法官。
流程：开庭陈述 → [用户发言 → 对方反驳 → 法官评析] × 3 轮 → 模拟判决。

生成路径：LLM 可用时三角色走 LLM（角色化 system prompt）；
否则规则版——反驳来自攻击点库（证据/时效/因果/可预见/过错相抵/程序），
评析与判决只组织已知要素，**不编造案情、不出具正式判决**（免责声明硬性附带）。
"""

import itertools
import uuid
from dataclasses import dataclass, field

from app.core.llm import LLMConfig, generate
from app.core.security import wrap_untrusted
from app.models.schemas import (
    FactSet,
    TrialSession,
    TrialStartRequest,
    TrialTurn,
    TrialTurnRequest,
)
from app.rag.retriever import Retriever
from app.services.facts_service import structure_facts
from app.services.opinion_service import _detect_topic

MAX_ROUNDS = 3

# ---- 攻击点库：对方律师的武器架 ----
ATTACK_LIBRARY: dict[str, list[str]] = {
    "evidence": [
        "【证据抗辩】对方就该项主张未能提供充分证据，依举证责任分配规则应承担不利后果。",
        "【证据抗辩】对方证据多为复印件/聊天截图，真实性、完整性、关联性均可质疑，建议申请鉴定或要求出示原件。",
        "【证据抗辩】对方所述事实缺乏客观证据佐证，属单方陈述，不能单独作为定案依据。",
    ],
    "limitation": [
        "【时效抗辩】对方主张的权利自知道或应当知道权利受损之日起可能已逾三年诉讼时效（民法典第一百八十八条），请求依法驳回。",
        "【时效抗辩】劳动争议申请仲裁的时效期间为一年，对方部分主张可能已超过仲裁时效。",
    ],
    "causality": [
        "【因果抗辩】损害与我方行为之间不存在法律上的因果关系，系第三方原因或市场风险所致。",
        "【因果抗辩】对方扩大损失的部分与我方无关，扩大的损失无权要求赔偿。",
    ],
    "foreseeability": [
        "【可预见规则】即便构成违约，赔偿范围也不得超过违约方订立合同时预见到或者应当预见到的损失（民法典第五百八十四条但书）。",
    ],
    "comparative": [
        "【过错相抵】对方对损害的发生也有过错，依法应当减轻我方责任（民法典第一千一百七十三条）。",
    ],
    "procedural": [
        "【程序抗辩】劳动争议未经仲裁前置程序，直接起诉不符合受理条件。",
        "【程序抗辩】双方合同约定争议提交仲裁解决，法院无管辖权。",
    ],
    "clause": [
        "【合同抗辩】双方已有明确约定，应按合同条款确定权利义务，对方无权另行主张。",
        "【格式条款抗辩】对方未履行提示说明义务的主张不能成立，该条款已以显著方式提示。",
    ],
}

# 轮次 → 主题攻击顺序（保证每轮打法不同）
_ROUND_THEMES = [
    ["evidence", "limitation"],
    ["causality", "foreseeability", "comparative"],
    ["procedural", "clause", "evidence"],
]

_SESSIONS: dict[str, TrialSession] = {}


@dataclass
class _AttackPlan:
    counter: itertools.cycle = field(default_factory=lambda: itertools.cycle([]))


def _topic_defenses(topic: str) -> list[str]:
    if topic == "劳动":
        return ATTACK_LIBRARY["procedural"][:1] + ATTACK_LIBRARY["limitation"][1:]
    if topic == "合同":
        return ATTACK_LIBRARY["foreseeability"] + ATTACK_LIBRARY["clause"]
    if topic == "侵权":
        return ATTACK_LIBRARY["comparative"] + ATTACK_LIBRARY["causality"]
    return []


def _opponent_rebuttal(session: TrialSession, user_statement: str, topic: str) -> str:
    """规则版对方律师发言：按轮次主题从攻击点库取用（每轮打法不同）。"""
    themes = _ROUND_THEMES[min(session.round - 1, len(_ROUND_THEMES) - 1)]
    points: list[str] = []
    for theme in themes:
        points.append(ATTACK_LIBRARY[theme][0])
    points += _topic_defenses(topic)
    if not points:
        points = ATTACK_LIBRARY["evidence"][:1]
    head = "对方律师（反驳）：针对刚才的发言，我方意见如下：\n"
    return head + "\n".join(f"{i+1}. {p}" for i, p in enumerate(points[:3]))


def _judge_opening(fact_set: FactSet, topic: str) -> str:
    focus = []
    if fact_set.counts.get("to_verify", 0):
        focus.append("待核实事实的证明责任分配")
    if fact_set.counts.get("claim", 0):
        focus.append("主张事实与诉求金额的依据")
    if topic == "劳动":
        focus.append("劳动关系成立与否及工资标准的认定")
    elif topic == "合同":
        focus.append("违约行为、损失范围及可预见性的认定")
    elif topic == "侵权":
        focus.append("过错、因果关系及损害后果的认定")
    focus.append("诉讼/仲裁时效")
    return (
        "法官（开庭）：本庭归纳本案争议焦点如下——\n"
        + "\n".join(f"{i+1}. {f}" for i, f in enumerate(focus))
        + "\n\n请双方围绕争议焦点举证、质证、辩论。本模拟法庭的输出仅供推演参考，不具法律效力。"
    )


def _judge_round_comment(session: TrialSession, round_no: int) -> str:
    f = session.fact_set.counts
    return (
        f"法官（第{round_no}轮评析）："
        f"本案已确认事实 {f.get('confirmed', 0)} 项、待核实 {f.get('to_verify', 0)} 项、"
        f"主张 {f.get('claim', 0)} 项。"
        "双方应围绕举证责任继续推进：主张积极事实的一方承担举证责任，"
        "未能举证的承担不利后果。下一轮请就对方本轮观点逐项回应。"
    )


def _judge_verdict(session: TrialSession, topic: str) -> str:
    f = session.fact_set.counts
    strong = f.get("confirmed", 0) >= max(f.get("to_verify", 0) + f.get("assumption", 0), 1)
    lean = "原告方（主张方）的请求在已确认事实范围内较有可能获得支持" if strong else \
        "被告方的抗辩空间较大——主张方待核实/假设事实偏多，补齐证据前诉求难获全额支持"
    cites = "、".join(f"[{c.statute_id}]" for c in session.citations[:3]) or "无"
    return (
        "法官（模拟判决·仅供推演）：\n"
        f"一、倾向性意见：{lean}。\n"
        f"二、关键事实状态：已确认 {f.get('confirmed', 0)} / 待核实 {f.get('to_verify', 0)} / "
        f"假设 {f.get('assumption', 0)} / 主张 {f.get('claim', 0)}。\n"
        f"三、主要参考条文：{cites}。\n"
        "四、风险提示：若对方补齐证据或提出时效抗辩成立，上述倾向可能逆转。\n\n"
        "⚠️ 本模拟判决由推演沙盘生成，不构成法律意见、不具任何法律效力；"
        "真实诉讼结果取决于完整证据与庭审情况，请咨询执业律师。"
    )


class TrialService:
    def __init__(self, retriever: Retriever):
        self.retriever = retriever

    def start(self, req: TrialStartRequest) -> TrialSession:
        fact_set = structure_facts(req.case_description)
        citations = self.retriever.retrieve(req.case_description, top_k=5, jurisdiction=req.jurisdiction)
        topic = _detect_topic(req.case_description)

        session = TrialSession(
            id=uuid.uuid4().hex[:12],
            user_role=req.user_role,
            case_description=req.case_description,
            fact_set=fact_set,
            citations=citations,
            round=1,
            turns=[],
            status="ongoing",
        )

        # 开庭：法官归纳焦点 + 对方律师开场
        session.turns.append(TrialTurn(role="judge", round=0, content=_judge_opening(fact_set, topic)))
        opening = (
            f"对方律师（开场陈述）：针对{'原告' if req.user_role == 'defendant' else '被告'}方的主张，"
            "我方将在证据、时效与因果关系三个层面提出抗辩，逐项拆解对方诉求。"
        )
        if citations:
            opening += f"\n（我方将重点围绕 {citations[0].law_title}{citations[0].article_no} 展开法律适用抗辩。）"
        session.turns.append(TrialTurn(role="opponent", round=0, content=opening))

        _SESSIONS[session.id] = session
        return session

    def turn(self, req: TrialTurnRequest) -> TrialSession:
        session = _SESSIONS.get(req.session_id)
        if session is None:
            raise KeyError(f"会话 {req.session_id} 不存在（服务重启后会话不保留）")
        if session.status != "ongoing":
            raise ValueError("本场模拟法庭已结束，请重新开庭")

        topic = _detect_topic(session.case_description)
        session.turns.append(
            TrialTurn(role="user", round=session.round, content=req.user_statement)
        )

        # LLM 可用时对方律师与法官走 LLM，否则规则版
        cfg = LLMConfig.from_settings()
        opponent_text = None
        judge_text = None
        if cfg.available:
            opponent_text = generate(
                _OPPONENT_SYS,
                self._ctx(session) + f"\n\n用户（{'原告' if session.user_role == 'plaintiff' else '被告'}）本轮发言：\n{wrap_untrusted(req.user_statement)}",
                cfg,
            )
            judge_text = generate(
                _JUDGE_SYS,
                self._ctx(session) + f"\n\n请对第 {session.round} 轮双方表现做简要评析。",
                cfg,
            )

        session.turns.append(
            TrialTurn(
                role="opponent",
                round=session.round,
                content=opponent_text or _opponent_rebuttal(session, req.user_statement, topic),
            )
        )

        if session.round >= MAX_ROUNDS:
            verdict = _judge_verdict(session, topic)
            session.turns.append(TrialTurn(role="judge", round=session.round, content=verdict))
            session.status = "closed"
        else:
            session.turns.append(
                TrialTurn(
                    role="judge",
                    round=session.round,
                    content=judge_text or _judge_round_comment(session, session.round),
                )
            )
            session.round += 1

        return session

    @staticmethod
    def _ctx(session: TrialSession) -> str:
        facts = "\n".join(f"[{f.fact_type}] {f.text}" for f in session.fact_set.facts)
        cites = "\n".join(f"[{c.statute_id}] {c.law_title}{c.article_no}：{c.text[:80]}" for c in session.citations[:3])
        return (
            f"{wrap_untrusted(session.case_description, '案情')}\n\n"
            f"{wrap_untrusted(facts, '结构化事实')}\n\n"
            f"{wrap_untrusted(cites, '相关法条')}\n\n"
            f"当前回合：第 {session.round}/{MAX_ROUNDS} 轮；用户角色：{session.user_role}"
        )


_OPPONENT_SYS = """你是模拟法庭中的对方律师。任务：针对用户（对方当事人）的发言做有力、专业的反驳。
要求：1) 只围绕证据、时效、因果关系、可预见性、过错相抵、程序等法定抗辩点展开；
2) 引用给定法条时用 [CIT-xxx]；3) 不得编造案情事实或法条；4) 语言犀利但专业，中文输出。"""

_JUDGE_SYS = """你是模拟法庭中的法官。任务：中立、简要评析本回合双方表现，指出举证责任分配与下一步应聚焦的问题。
不得出具正式判决；输出中文，控制在 200 字内。"""
