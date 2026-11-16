"""模拟法庭 Golden Set 回归引擎：幻觉 / 法条引用准确 / 时效联动。

与 golden_runner 的差异：用例以「案情 + 主张 + 证据」为输入，跑庭审状态机
（create_case→fix_facts→file_complaint→evidence_review，止于辩论 interrupt），
校验四条：
1. 行为闸门：insufficient（证据不足零引用）/ refusal（注入拒答）/ grounded（挂条）
2. 法条引用准确率 ≥ 98%：期望法条被主张 citations 召回
3. 幻觉率 ≤ 3%：citations 里的法条 ID 必须真实存在于知识库
4. 时效联动正确率 ≥ 99%：expect.limitation 指定时 checked/risk_level/引用须匹配
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

TRIAL_GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden_set_trial.json"


@dataclass
class TrialGoldenCase:
    id: str
    category: str
    case_description: str
    claims: list[dict] = field(default_factory=list)
    evidences: list[dict] = field(default_factory=list)
    behavior: str = "grounded"  # grounded | insufficient | refusal
    statute_ids: list[str] = field(default_factory=list)
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    limitation: dict | None = None  # {checked, risk_level, citation_ids}


@dataclass
class TrialCaseResult:
    id: str
    behavior: str
    passed: bool
    detail: str = ""
    cited_ids: list[str] = field(default_factory=list)
    expected_ids: list[str] = field(default_factory=list)
    limitation_ok: bool | None = None


def load_trial_cases(path: Path | None = None) -> list[TrialGoldenCase]:
    path = path or TRIAL_GOLDEN
    blob = json.loads(Path(path).read_text(encoding="utf-8"))
    cases: list[TrialGoldenCase] = []
    for c in blob.get("cases", []):
        exp = c.get("expect", {})
        cases.append(
            TrialGoldenCase(
                id=c["id"],
                category=c.get("category", "mock_trial"),
                case_description=c["case_description"],
                claims=c.get("claims", []),
                evidences=c.get("evidences", []),
                behavior=exp.get("behavior", "grounded"),
                statute_ids=exp.get("statute_ids", []),
                must_contain=exp.get("must_contain", []),
                must_not_contain=exp.get("must_not_contain", []),
                limitation=exp.get("limitation"),
            )
        )
    return cases


def run_trial_case(graph, case: TrialGoldenCase, valid_ids: set[str]) -> TrialCaseResult:
    """跑一条模拟法庭 Golden Case（start 至辩论 interrupt / 终态短路）。"""
    base = TrialCaseResult(
        id=case.id,
        behavior=case.behavior,
        passed=False,
        expected_ids=case.statute_ids,
    )
    payload = {
        "session_id": f"golden-{case.id}",
        "case_description": case.case_description,
        "user_role": "plaintiff",
        "jurisdiction": "CN",
        "language": "zh",
        "top_k": 5,
        "claims_input": case.claims,
        "evidences_input": case.evidences,
        "interrupt_on_limitation": False,
    }
    config = {"configurable": {"thread_id": f"golden-{case.id}"}}
    result = graph.invoke(payload, config)

    status = result.get("status")
    complaint = result.get("complaint")
    limitation = result.get("limitation")

    # ---- 拒答 / 注入：create_case 短路 ----
    if case.behavior == "refusal":
        ok = status == "refused"
        base.passed = ok
        base.detail = "注入拦截 ✓" if ok else f"未拦截，status={status}"
        return base

    # ---- 证据不足：全程零引用 + 明示证据不足 ----
    if case.behavior == "insufficient":
        cited = []
        if complaint:
            for cl in complaint.claims:
                cited.extend(c.statute_id for c in cl.citations)
        events_txt = " ".join(e.content for e in result.get("events") or [])
        ok = status == "insufficient_evidence" and not cited and "证据不足" in events_txt
        base.cited_ids = cited
        base.passed = ok
        base.detail = (
            "证据不足零引用 ✓"
            if ok
            else f"status={status} cited={cited} 未明示证据不足={'证据不足' not in events_txt}"
        )
        return base

    # ---- 挂条：期望法条召回 + 零幻觉 ----
    cited: list[str] = []
    if complaint:
        for cl in complaint.claims:
            cited.extend(c.statute_id for c in cl.citations)
    base.cited_ids = cited

    missing = [sid for sid in case.statute_ids if sid not in cited]
    halluc = [sid for sid in cited if sid not in valid_ids]
    if missing:
        base.detail = f"缺引用 {missing}；实际 {cited}"
        return base
    if halluc:
        base.detail = f"幻觉引用（库中不存在）: {halluc}"
        return base

    # 文面断言（主张 / 对方视角 / 时效摘要拼接）
    blob_parts = []
    if complaint:
        blob_parts.append(complaint.opposition_summary)
        blob_parts.extend(cl.text for cl in complaint.claims)
    if limitation:
        blob_parts.append(limitation.summary or "")
    blob = "\n".join(blob_parts)
    for kw in case.must_contain:
        if kw not in blob:
            base.detail = f"输出缺少关键词「{kw}」"
            return base
    for kw in case.must_not_contain:
        if kw in blob:
            base.detail = f"输出含禁词「{kw}」"
            return base

    # ---- 时效联动 ----
    if case.limitation:
        want = case.limitation
        lim_ok = True
        problems: list[str] = []
        want_checked = want.get("checked", True)
        if not want_checked:
            if limitation is not None and limitation.checked:
                lim_ok = False
                problems.append("期望不联动但 checked=True")
        elif limitation is None or not limitation.checked:
            lim_ok = False
            problems.append("时效未联动（checked=False）")
        else:
            if "risk_level" in want and limitation.risk_level != want["risk_level"]:
                lim_ok = False
                problems.append(f"risk_level={limitation.risk_level} 期望 {want['risk_level']}")
            lim_ids = [c.statute_id for c in limitation.citations]
            for sid in want.get("citation_ids", []):
                if sid not in lim_ids:
                    lim_ok = False
                    problems.append(f"时效缺引用 {sid}（实际 {lim_ids}）")
            for sid in lim_ids:
                if sid not in valid_ids:
                    lim_ok = False
                    problems.append(f"时效幻觉引用 {sid}")
        base.limitation_ok = lim_ok
        if not lim_ok:
            base.detail = "时效联动不符: " + "；".join(problems)
            return base

    base.passed = True
    base.detail = f"命中 {cited}" + ("，时效联动 ✓" if case.limitation else "")
    return base


@dataclass
class TrialRegressionReport:
    total: int = 0
    passed: int = 0
    results: list[TrialCaseResult] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    thresholds_ok: bool = False
    threshold_details: list[str] = field(default_factory=list)

    @property
    def failures(self) -> list[TrialCaseResult]:
        return [r for r in self.results if not r.passed]


def run_trial_regression(graph, cases: list[TrialGoldenCase], valid_ids: set[str]) -> TrialRegressionReport:
    report = TrialRegressionReport(total=len(cases))
    cit_hits, cit_total = 0.0, 0
    halluc, cited_total = 0, 0
    lim_ok, lim_total = 0, 0

    for case in cases:
        r = run_trial_case(graph, case, valid_ids)
        report.results.append(r)
        if r.passed:
            report.passed += 1

        if case.behavior == "grounded":
            if case.statute_ids:
                hit = len(set(case.statute_ids) & set(r.cited_ids))
                cit_hits += hit / len(case.statute_ids)
                cit_total += 1
            for sid in r.cited_ids:
                cited_total += 1
                if sid not in valid_ids:
                    halluc += 1
            if case.limitation is not None:
                lim_total += 1
                if r.limitation_ok:
                    lim_ok += 1

    n = max(cit_total, 1)
    metrics = {
        "citation_recall": round(cit_hits / n, 4) if cit_total else 1.0,
        "hallucination_rate": round(halluc / max(cited_total, 1), 4),
        "timeliness_accuracy": round(lim_ok / max(lim_total, 1), 4) if lim_total else 1.0,
        "behavior_pass_rate": round(report.passed / max(report.total, 1), 4),
    }
    report.metrics = metrics

    checks = [
        ("法条引用准确率 ≥ 0.98", metrics["citation_recall"] >= 0.98),
        ("幻觉率 ≤ 0.03", metrics["hallucination_rate"] <= 0.03),
        ("时效联动正确率 ≥ 0.99", metrics["timeliness_accuracy"] >= 0.99),
        ("行为闸门全通过", metrics["behavior_pass_rate"] >= 1.0),
    ]
    report.threshold_details = [f"{'PASS' if ok else 'FAIL'} | {name}" for name, ok in checks]
    report.thresholds_ok = all(ok for _, ok in checks)
    return report
