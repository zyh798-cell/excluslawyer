"use client";

import { useState } from "react";
import { Calculator, Loader2, Search } from "lucide-react";
import {
  CalcResponse,
  CompareResponse,
  calculate,
  compare,
} from "@/lib/api";
import KgPanel from "@/components/KgPanel";
import LegalDisclaimer from "@/components/LegalDisclaimer";
import { showToast } from "@/components/Toast";

const CALC_TYPES = [
  {
    id: "economic_compensation",
    label: "经济补偿（劳动合同法47）",
    fields: [
      { key: "years", label: "工作年限（年，可带小数）", def: "3" },
      { key: "monthly_salary", label: "月工资（元）", def: "10000" },
      { key: "region_avg_salary", label: "当地社平月工资（元，可空）", def: "" },
    ],
  },
  {
    id: "double_wage",
    label: "未签合同二倍工资（劳动合同法82）",
    fields: [
      { key: "monthly_salary", label: "月工资（元）", def: "8000" },
      { key: "months_uncovered", label: "未签合同月数（最多11）", def: "7" },
    ],
  },
  {
    id: "personal_injury",
    label: "人身损害赔偿（民法典1179）",
    fields: [
      { key: "medical", label: "医疗费（元）", def: "30000" },
      { key: "lost_income", label: "误工费（元）", def: "20000" },
      { key: "nursing", label: "护理费（元）", def: "" },
      { key: "disability_level", label: "伤残等级（1-10，无则空）", def: "10" },
      { key: "annual_income", label: "人均可支配收入（元/年）", def: "50000" },
    ],
  },
  {
    id: "liquidated_damages",
    label: "违约金合理性（民法典585）",
    fields: [
      { key: "agreed_penalty", label: "约定违约金（元）", def: "200000" },
      { key: "actual_loss", label: "实际损失（元）", def: "100000" },
    ],
  },
  {
    id: "limitation_check",
    label: "诉讼时效判断（民法典188）",
    fields: [
      { key: "damage_date", label: "权利受损之日（YYYY-MM-DD）", def: "2023-01-01" },
      { key: "known_date", label: "知道受损之日（可空）", def: "" },
    ],
  },
] as const;

/**
 * P2-11/12 工具箱：赔偿计算器 + 多法域对比（知识图谱见 KgPanel）。
 */
export default function ToolboxView() {
  // ---- 计算器 ----
  const [calcType, setCalcType] = useState<string>(CALC_TYPES[0].id);
  const [params, setParams] = useState<Record<string, string>>({});
  const [calcResult, setCalcResult] = useState<CalcResponse | null>(null);
  // ---- 对比 ----
  const [cmpQ, setCmpQ] = useState("");
  const [cmpResult, setCmpResult] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState("");

  const calcDef = CALC_TYPES.find((c) => c.id === calcType)!;

  async function onCalc() {
    if (loading) return;
    setLoading("calc");
    try {
      const p: Record<string, unknown> = {};
      for (const f of calcDef.fields) {
        const v = params[f.key] ?? f.def;
        if (v !== "") p[f.key] = isNaN(Number(v)) ? v : Number(v);
      }
      setCalcResult(await calculate(calcType, p));
      showToast("计算完成（透明公式，仅供参考）", "ok");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "计算失败", "error");
    } finally {
      setLoading("");
    }
  }

  async function onCompare() {
    if (!cmpQ.trim() || loading) return;
    setLoading("cmp");
    try {
      setCmpResult(await compare(cmpQ));
    } catch (e) {
      showToast(e instanceof Error ? e.message : "对比失败", "error");
    } finally {
      setLoading("");
    }
  }

  return (
    <div className="flex flex-col gap-5">
      {/* 知识图谱（独立面板：G6 画布 + 法域切换 + 判例展示） */}
      <KgPanel />

      {/* 赔偿计算器 */}
      <section className="card p-5">
        <h2 className="flex items-center gap-2 text-base font-semibold text-fg">
          <Calculator size={17} className="text-accent-soft" aria-hidden /> 赔偿计算器（透明公式）
        </h2>
        <select
          className="select mt-3"
          value={calcType}
          aria-label="选择计算器类型"
          onChange={(e) => {
            setCalcType(e.target.value);
            setParams({});
            setCalcResult(null);
          }}
        >
          {CALC_TYPES.map((c) => (
            <option key={c.id} value={c.id}>{c.label}</option>
          ))}
        </select>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {calcDef.fields.map((f) => (
            <label key={f.key} className="text-xs text-fg-muted">
              {f.label}
              <input
                className="input mt-1"
                aria-label={f.label}
                value={params[f.key] ?? f.def}
                onChange={(e) => setParams({ ...params, [f.key]: e.target.value })}
              />
            </label>
          ))}
        </div>
        <button
          className="btn btn-primary mt-3"
          onClick={onCalc}
          disabled={loading === "calc"}
          aria-label="计算赔偿金额"
        >
          {loading === "calc" ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Calculator size={15} aria-hidden />}
          计算
        </button>
        {calcResult && (
          <div className="mt-3 rounded-lg border border-line bg-surface-sunken/50 p-4">
            <p className="text-lg font-semibold text-accent-soft">
              参考结果：{calcResult.total != null ? `¥ ${calcResult.total.toLocaleString()}` : "需补充参数"}
            </p>
            <table className="mt-2 w-full text-xs">
              <tbody>
                {calcResult.items.map((it, i) => (
                  <tr key={i} className="border-t border-line">
                    <td className="py-1.5 pr-2 text-fg-muted">{it.label}</td>
                    <td className="py-1.5 pr-2 text-fg">
                      {it.amount != null ? it.amount.toLocaleString() : ""}
                    </td>
                    <td className="py-1.5 text-fg-subtle">{it.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-fg-muted">公式：{calcResult.formula}</p>
            {calcResult.caveats.length > 0 && (
              <ul className="mt-1.5 space-y-0.5 text-xs text-warn">
                {calcResult.caveats.map((c, i) => (
                  <li key={i}>· {c}</li>
                ))}
              </ul>
            )}
            <LegalDisclaimer className="mt-3" />
          </div>
        )}
      </section>

      {/* 多法域对比 */}
      <section className="card p-5">
        <h2 className="text-base font-semibold text-fg">多法域对比（中/日/韩/新）</h2>
        <div className="mt-3 flex gap-2">
          <input
            className="input flex-1"
            placeholder="例如：诉讼时效是多久 / 违约金过高怎么调减"
            value={cmpQ}
            aria-label="多法域对比查询"
            onChange={(e) => setCmpQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onCompare()}
          />
          <button
            className="btn btn-primary"
            onClick={onCompare}
            disabled={loading === "cmp" || !cmpQ.trim()}
            aria-label="开始多法域对比"
          >
            {loading === "cmp" ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Search size={15} aria-hidden />}
            对比
          </button>
        </div>
        {cmpResult && (
          <div className="mt-3">
            <p className="text-sm font-medium text-accent-soft">主题：{cmpResult.topic}</p>
            <div className="mt-2 space-y-2">
              {cmpResult.rows.map((r) => (
                <div key={r.jurisdiction} className="rounded-lg border border-line bg-surface-sunken/50 p-3">
                  <p className="text-sm font-medium text-fg">
                    {r.jurisdiction_name}
                    <span className="ml-2 text-xs text-fg-subtle">{r.statute_ref}</span>
                  </p>
                  <p className="mt-1 text-sm leading-6 text-fg-muted">{r.rule_summary}</p>
                  {r.original_excerpt && (
                    <p className="mt-1.5 border-l-2 border-line pl-2 text-xs leading-5 text-fg-subtle">
                      原文（{r.language}）：{r.original_excerpt}
                      {r.gloss && <span className="block text-fg-subtle">释义：{r.gloss}</span>}
                    </p>
                  )}
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs leading-5 text-warn">要点：{cmpResult.takeaway}</p>
            <p className="mt-1 text-xs text-fg-subtle">{cmpResult.disclaimer}</p>
            <LegalDisclaimer className="mt-2" />
          </div>
        )}
      </section>
    </div>
  );
}
