"use client";

import type { OpinionResponse } from "@/lib/api";
import LegalDisclaimer from "@/components/LegalDisclaimer";
import { PlainAnswerSection } from "@/components/PlainAnswerCard";
import PlainToggle from "@/components/PlainToggle";

const RISK_META = {
  high: { label: "风险：高", cls: "bg-danger/15 text-danger" },
  medium: { label: "风险：中", cls: "bg-warn/15 text-warn" },
  low: { label: "风险：低", cls: "bg-ok/15 text-ok" },
};

/**
 * P0-3 视图：五段式法律意见书渲染。
 * 一、事实认定 二、法律适用 三、风险等级 四、行动建议 五、限制提示（+对抗模式第六段）
 *
 * 通俗模式（大白话解释层）：开启时白话结论在上、风险提示显性保留，
 * 五段式原文收进可展开区；关闭时恢复专业展示。开关状态全站同步。
 */
export default function OpinionView({ opinion }: { opinion: OpinionResponse }) {
  const risk = RISK_META[opinion.risk_level];

  const professional = (
    <div className="space-y-5">
      {/* 风险理由（透明可追溯） */}
      {opinion.risk_reasons.length > 0 && (
        <ul className="space-y-1 rounded-lg border border-line bg-surface-sunken/50 p-3">
          {opinion.risk_reasons.map((r, i) => (
            <li key={i} className="text-xs leading-5 text-fg-muted">
              · {r}
            </li>
          ))}
        </ul>
      )}

      {opinion.sections.map((s, i) => (
        <div key={i}>
          <h3 className="text-sm font-semibold text-accent-soft">{s.title}</h3>
          <article className="mt-1.5 whitespace-pre-wrap text-sm leading-7 text-fg-muted">
            {s.content}
          </article>
          {s.citation_ids.length > 0 && (
            <p className="mt-1.5 text-xs text-fg-subtle">
              本段引用：
              {s.citation_ids.map((id) => (
                <span key={id} className="chip ml-1 border border-line font-mono text-fg-subtle">
                  {id}
                </span>
              ))}
            </p>
          )}
        </div>
      ))}
    </div>
  );

  const opinionText = opinion.sections
    .filter((s) => s.title.includes("法律适用") || s.title.includes("风险"))
    .map((s) => s.content)
    .join("\n\n") ||
    opinion.sections.map((s) => s.content).join("\n\n");

  return (
    <section className="card p-5">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold text-fg">法律意见书（五段式）</h2>
        <span className={`chip ${risk.cls}`}>{risk.label}</span>
        <span className="chip bg-accent/15 text-accent-soft">
          {opinion.mode === "server" ? "LLM 生成" : "模板组装（无 LLM）"}
        </span>
        <span
          className={`chip ${
            opinion.nli.status === "degraded"
              ? "bg-danger/15 text-danger"
              : opinion.nli.status === "pass"
                ? "bg-ok/15 text-ok"
                : "bg-warn/15 text-warn"
          }`}
        >
          NLI：{opinion.nli.status === "pass" ? "一致" : opinion.nli.status === "degraded" ? "支撑不足·降级" : "未验证"}
        </span>
        <PlainToggle className="ml-auto" />
      </div>

      {/* 通俗模式：白话在上 + 风险原样保留；专业五段式收进可展开区 */}
      <PlainAnswerSection
        input={{
          kind: "opinion",
          text: opinionText,
          citations: opinion.citations,
          nli: opinion.nli,
          riskLevel: opinion.risk_level,
          riskNotes: opinion.risk_reasons,
        }}
        sourceLabel="五段式意见书原文（事实认定 / 法律适用 / 风险等级 / 行动建议 / 限制提示）"
        professional={professional}
        source={professional}
      />
      <LegalDisclaimer className="mt-4" />
    </section>
  );
}
