"use client";

import type { FactSet, FactType } from "@/lib/api";

const FACT_META: Record<FactType, { label: string; cls: string; dot: string }> = {
  confirmed: { label: "已确认", cls: "bg-ok/15 text-ok", dot: "bg-ok" },
  to_verify: { label: "待核实", cls: "bg-warn/15 text-warn", dot: "bg-warn" },
  assumption: { label: "假设", cls: "bg-purple-400/15 text-purple-300", dot: "bg-purple-400" },
  claim: { label: "主张", cls: "bg-accent/15 text-accent-soft", dot: "bg-accent" },
};

const ORDER: FactType[] = ["confirmed", "to_verify", "assumption", "claim"];

/**
 * P0-2 视图：四类事实卡片 + 时间线卡片。
 * 分类色标：绿=已确认 黄=待核实 紫=假设 蓝=主张
 */
export default function FactPanel({ factSet }: { factSet: FactSet }) {
  return (
    <section className="card p-5">
      <h2 className="text-sm font-semibold text-fg-muted">
        案件事实结构化 · 四类事实（{factSet.facts.length} 条）
      </h2>
      <div className="mt-3 flex flex-wrap gap-2">
        {ORDER.map((t) => (
          <span key={t} className={`chip ${FACT_META[t].cls}`}>
            {FACT_META[t].label} × {factSet.counts[t] ?? 0}
          </span>
        ))}
      </div>

      {/* 四类事实卡片 */}
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {ORDER.map((t) => {
          const items = factSet.facts.filter((f) => f.fact_type === t);
          if (items.length === 0) return null;
          return (
            <div key={t} className="rounded-lg border border-line bg-surface-sunken/50 p-3">
              <p className={`chip ${FACT_META[t].cls}`}>{FACT_META[t].label}</p>
              <ul className="mt-2 space-y-1.5">
                {items.map((f, i) => (
                  <li key={i} className="text-xs leading-5 text-fg-muted">
                    <span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle ${FACT_META[t].dot}`} />
                    {f.text}
                    {f.date_label && <span className="ml-1 text-fg-subtle">（{f.date_label}）</span>}
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>

      {/* 时间线卡片 */}
      <h3 className="mt-5 text-xs font-semibold text-fg-subtle">时间线卡片（按时间排序）</h3>
      <ol className="mt-3 space-y-0 border-l border-line pl-4">
        {factSet.timeline.map((card, i) => {
          const meta = FACT_META[card.fact_type];
          return (
            <li key={i} className="relative pb-4 last:pb-0">
              <span
                className={`absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-surface-base ${meta.dot}`}
              />
              <p className="text-xs text-fg-subtle">
                {card.date_label}
                <span className={`ml-2 chip ${meta.cls}`}>{meta.label}</span>
              </p>
              <p className="mt-0.5 text-sm leading-6 text-fg-muted">{card.event_text}</p>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
