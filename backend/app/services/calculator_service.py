"""P2-11 赔偿/量刑计算器：规则引擎驱动，计算过程透明可复核。

五个计算器（分法域维护公式，当前为大陆法系·中国）：
1. economic_compensation  经济补偿（劳动合同法第四十七条）
2. double_wage            未签合同二倍工资（劳动合同法第八十二条）
3. personal_injury        人身损害赔偿（民法典第一千一百七十九条）
4. liquidated_damages     违约金合理性参考（民法典第五百八十五条）
5. limitation_check       诉讼时效判断（民法典第一百八十八条）

原则：输出每一项的计算过程 + 法条依据 + 假设条件，绝不藏黑箱。
"""

from datetime import date, datetime

from app.models.schemas import CalcItem, CalcRequest, CalcResponse


def _f(params: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(params.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _d(params: dict, key: str) -> date | None:
    raw = params.get(key)
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


# ---------- 1. 经济补偿（劳动合同法47）----------

def economic_compensation(p: dict) -> CalcResponse:
    years = _f(p, "years")                    # 本单位工作年限
    monthly = _f(p, "monthly_salary")         # 月工资（离职前12个月平均）
    region_avg = _f(p, "region_avg_salary")   # 当地上年度职工月平均工资（用于3倍封顶）
    items: list[CalcItem] = []

    base = monthly
    capped = False
    if region_avg > 0 and monthly > region_avg * 3:
        base = region_avg * 3
        capped = True
        items.append(CalcItem(label="月工资基数（3倍封顶）", amount=base,
                              note=f"月工资 {monthly:.0f} 超过社平工资3倍（{region_avg * 3:.0f}），按3倍封顶"))
    else:
        items.append(CalcItem(label="月工资基数", amount=base, note="按离职前12个月平均工资"))

    # 年限折算：6个月以上不满1年按1年；不满6个月按半个月
    eff_years = int(years)
    months_extra = round((years - eff_years) * 12)
    if months_extra >= 6:
        eff_years += 1
        months_part = 0
    else:
        months_part = months_extra
    if capped:
        eff_years = min(eff_years, 12)  # 封顶12年
        items.append(CalcItem(label="年限封顶", amount=None, note=f"3倍封顶情形最高按12年计算，实际计 {eff_years} 年"))

    total = base * eff_years
    if months_part > 0:
        total += base * 0.5
        items.append(CalcItem(label="不满6个月部分", amount=base * 0.5, note=f"剩余 {months_part} 个月不满6个月，按半个月工资计"))
    items.insert(0, CalcItem(label=f"工作年限折算", amount=float(eff_years), note=f"{years} 年折算为 {eff_years} 年（含不满6个月折半规则）"))

    return CalcResponse(
        calc_type="economic_compensation",
        total=round(total, 2),
        items=items,
        formula="经济补偿 = 月工资基数 × 折算年限（不满6个月的另加半个月工资；3倍封顶地区年限最高12年）",
        basis=["CN-LDF-47"],
        caveats=["月工资指劳动合同解除或终止前12个月的平均工资", "高薪劳动者受社平工资3倍与12年双重封顶限制"],
    )


# ---------- 2. 二倍工资（劳动合同法82）----------

def double_wage(p: dict) -> CalcResponse:
    monthly = _f(p, "monthly_salary")
    months = min(_f(p, "months_uncovered"), 11)  # 用工满1年视为订立无固定期限，差额最多11个月
    items = [
        CalcItem(label="月工资", amount=monthly, note="以应得工资为基数"),
        CalcItem(label="未签合同月数", amount=months, note="超过一个月不满一年部分，最多按11个月"),
        CalcItem(label="二倍工资差额", amount=round(monthly * months, 2), note="已发一倍工资之外的差额部分"),
    ]
    return CalcResponse(
        calc_type="double_wage",
        total=round(monthly * months, 2),
        items=items,
        formula="二倍工资差额 = 月工资 × 未签书面合同月数（最多11个月）",
        basis=["CN-LDF-82"],
        caveats=[
            "自用工之日起满一个月的次日开始计算，最长11个月",
            "劳动争议仲裁时效为1年，注意起算点",
            "二倍工资差额性质各地裁判口径有差异（工资说/惩罚性赔偿说），个案以当地口径为准",
        ],
    )


# ---------- 3. 人身损害赔偿（民法典1179）----------

# 伤残赔偿系数（十级10% … 一级100%），伤残赔偿金 = 基准 × 20年 × 系数
_DISABILITY_RATE = {1: 1.0, 2: 0.9, 3: 0.8, 4: 0.7, 5: 0.6, 6: 0.5, 7: 0.4, 8: 0.3, 9: 0.2, 10: 0.1}


def personal_injury(p: dict) -> CalcResponse:
    items: list[CalcItem] = []
    total = 0.0
    for key, label in [
        ("medical", "医疗费"),
        ("lost_income", "误工费"),
        ("nursing", "护理费"),
        ("nutrition", "营养费"),
        ("hospital_allowance", "住院伙食补助费"),
        ("transport", "交通费"),
        ("assistive_devices", "辅助器具费"),
    ]:
        v = _f(p, key)
        if v > 0:
            items.append(CalcItem(label=label, amount=v, note="按实际票据/证明主张"))
            total += v

    level = int(_f(p, "disability_level"))
    if 1 <= level <= 10:
        income_base = _f(p, "annual_income") or 50000  # 受诉法院所在地上一年度人均可支配收入（需替换实际值）
        rate = _DISABILITY_RATE[level]
        comp = income_base * 20 * rate
        items.append(
            CalcItem(
                label=f"残疾赔偿金（{level}级伤残）",
                amount=round(comp, 2),
                note=f"{income_base:.0f} 元/年 × 20年 × 系数{rate}",
            )
        )
        total += comp
    if p.get("death"):
        comp = (_f(p, "annual_income") or 50000) * 20
        items.append(CalcItem(label="死亡赔偿金", amount=comp, note="人均可支配收入 × 20年（60周岁以上递减）"))
        total += comp
    if not items:
        items.append(CalcItem(label="（未填任何项目）", amount=0, note="请至少填写医疗费等一项"))

    return CalcResponse(
        calc_type="personal_injury",
        total=round(total, 2),
        items=items,
        formula="赔偿总额 = Σ实际支出项目 + 残疾/死亡赔偿金（人均可支配收入 × 20年 × 伤残系数）",
        basis=["CN-MINFA-1179", "CN-MINFA-1165"],
        caveats=[
            "残疾赔偿金/死亡赔偿金基准应使用受诉法院所在地上一年度官方统计数据（当前为占位值，请替换）",
            "60周岁以上年龄每增加一岁减少一年；75周岁以上按5年计算",
            "精神损害抚慰金另计，由法院酌定",
        ],
    )


# ---------- 4. 违约金合理性参考（民法典585）----------

def liquidated_damages(p: dict) -> CalcResponse:
    agreed = _f(p, "agreed_penalty")
    loss = _f(p, "actual_loss")
    items = [
        CalcItem(label="约定违约金", amount=agreed),
        CalcItem(label="实际损失（主张方举证）", amount=loss),
    ]
    if loss <= 0:
        return CalcResponse(
            calc_type="liquidated_damages",
            total=None,
            items=items,
            formula="需先举证实际损失，才能评估违约金是否过高",
            basis=["CN-MINFA-585"],
            caveats=["请填入实际损失金额后重新计算"],
        )
    upper = loss * 1.3
    ratio = agreed / loss if loss else 0
    too_high = agreed > upper
    items.append(
        CalcItem(
            label="司法调减参考上限（损失×1.3）",
            amount=round(upper, 2),
            note="司法实践常以损失上浮30%作为过高判断参考（各地口径有差异）",
        )
    )
    items.append(CalcItem(label="违约金/损失比", amount=round(ratio, 2), note="超过1.3倍时被调减的风险上升"))
    note = (
        f"约定违约金为损失的 {ratio:.2f} 倍，"
        + ("超过1.3倍参考线，存在被调减风险，建议主动下调或补充损失计算依据。" if too_high else "在参考区间内，获得支持的可能性较高。")
    )
    items.append(CalcItem(label="结论", amount=None, note=note))
    return CalcResponse(
        calc_type="liquidated_damages",
        total=round(min(agreed, upper), 2) if too_high else agreed,
        items=items,
        formula="参考可支持区间 = 实际损失 × [1.0, 1.3]；过分高于损失的可请求法院/仲裁机构调减",
        basis=["CN-MINFA-585"],
        caveats=["1.3 倍为常见参考而非法定硬线，法院综合合同履行、过错、预期利益裁量"],
    )


# ---------- 5. 诉讼时效判断（民法典188）----------

def limitation_check(p: dict) -> CalcResponse:
    damage_date = _d(p, "damage_date")
    known_date = _d(p, "known_date") or damage_date
    items: list[CalcItem] = []
    if not known_date:
        return CalcResponse(
            calc_type="limitation_check",
            total=None,
            items=[CalcItem(label="（缺日期）", amount=None, note="请填入权利受损之日或知道权利受损之日")],
            formula="诉讼时效 = 知道或应当知道权利受损之日起3年",
            basis=["CN-MINFA-188"],
            caveats=["自权利受损之日起超过20年的，法院不予保护"],
        )
    items.append(CalcItem(label="知道或应当知道权利受损之日", amount=None, note=str(known_date)))
    deadline = known_date.replace(year=known_date.year + 3)
    today = date.today()
    remaining = (deadline - today).days
    items.append(CalcItem(label="3年时效届满日", amount=None, note=str(deadline)))
    if remaining < 0:
        verdict = f"⚠️ 按普通3年时效，已于 {deadline} 届满（逾期 {-remaining} 天），存在时效抗辩风险"
    elif remaining < 180:
        verdict = f"⚠️ 距时效届满仅剩 {remaining} 天，建议立即书面主张权利以中断时效"
    else:
        verdict = f"时效剩余 {remaining} 天（至 {deadline}）"
    items.append(CalcItem(label="结论", amount=None, note=verdict))
    return CalcResponse(
        calc_type="limitation_check",
        total=float(max(remaining, 0)),
        items=items,
        formula="普通诉讼时效3年，自权利人知道或者应当知道权利受到损害以及义务人之日起计算",
        basis=["CN-MINFA-188"],
        caveats=[
            "存在中断（书面催告/起诉/承认）与中止事由的，期间重新计算或不计算",
            "劳动争议仲裁时效为1年，与民事3年时效不同",
            "最长权利保护期20年",
        ],
    )


_DISPATCH = {
    "economic_compensation": economic_compensation,
    "double_wage": double_wage,
    "personal_injury": personal_injury,
    "liquidated_damages": liquidated_damages,
    "limitation_check": limitation_check,
}


class CalculatorService:
    def calculate(self, req: CalcRequest) -> CalcResponse:
        fn = _DISPATCH[req.calc_type]
        return fn(req.params)
