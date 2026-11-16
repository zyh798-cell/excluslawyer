"use client";

import type { CaseSearchResponse } from "@/lib/api";
import LegalDisclaimer from "@/components/LegalDisclaimer";

const RESULT_META = {
  支持: { cls: "bg-ok/15 text-ok", bar: "bg-ok" },
  部分支持: { cls: "bg-warn/15 text-warn", bar: "bg-warn" },
  驳回: { cls: "bg-danger/15 text-danger", bar: "bg-danger" },
} as const;

/**
 * P1-6 视图：类案列表 + 裁判结果分布条 + 支持率。
 */
export default function CaseView({ result }: { result: CaseSearchResponse }) {
  const total = Math.max(result.cases.length, 1);
  return (
    <section className="card p-5">
      <h2 className="text-base font-semibold text-fg">类案参考 · 裁判结果分布</h2>

      {/* 分布条 */}
      <div className="mt-3">
        <div
          className="flex h-3 w-full overflow-hidden rounded-full bg-surface-hover"
          role="img"
          aria-label={`裁判结果分布：支持 ${result.result_distribution["支持"] ?? 0}，部分支持 ${result.result_distribution["部分支持"] ?? 0}，驳回 ${result.result_distribution["驳回"] ?? 0}`}
        >
          {(["支持", "部分支持", "驳回"] as const).map((k) => {
            const n = result.result_distribution[k] ?? 0;
            if (!n) return null;
            return <div key={k} className={`${RESULT_META[k].bar}`} style={{ width: `${(n / total) * 100}%` }} />;
          })}
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {(["支持", "部分支持", "驳回"] as const).map((k) => (
            <span key={k} className={`chip ${RESULT_META[k].cls}`}>
              {k} {result.result_distribution[k] ?? 0} 件
            </span>
          ))}
          <span className="chip bg-accent/15 text-accent-soft">
            支持率 {(result.support_rate * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* 类案卡片 */}
      <div className="mt-4 space-y-3">
        {result.cases.map((c) => (
          <div key={c.id} className="rounded-lg border border-line bg-surface-sunken/50 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`chip ${RESULT_META[c.result].cls}`}>{c.result}</span>
              <span className="text-sm font-medium text-fg-muted">{c.title}</span>
            </div>
            <p className="mt-1 text-xs text-fg-subtle">
              {c.court} · {c.date} · 案由：{c.cause}
            </p>
            <p className="mt-2 text-sm leading-6 text-fg-muted">{c.facts_summary}</p>
            <p className="mt-2 border-l-2 border-accent/50 pl-2 text-xs leading-5 text-fg-subtle">
              裁判要旨：{c.holding}
            </p>
            <p className="mt-2 text-xs text-fg-subtle">
              诉请 {(c.amount_claimed / 10000).toFixed(1)} 万 · 支持 {(c.amount_supported / 10000).toFixed(1)} 万
            </p>
          </div>
        ))}
        {result.cases.length === 0 && (
          <p className="text-sm text-fg-muted">未命中相关类案，可换更具体的要素关键词（案由/争议焦点/金额）。</p>
        )}
      </div>

      <p className="mt-4 text-xs leading-5 text-fg-subtle">{result.disclaimers[0]}</p>
      <LegalDisclaimer className="mt-2" />
    </section>
  );
}
