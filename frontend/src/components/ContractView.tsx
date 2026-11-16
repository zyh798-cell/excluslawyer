"use client";

import { useState } from "react";
import type { ContractClause, ContractScanResponse, StatuteTimeline } from "@/lib/api";
import { getStatuteTimeline } from "@/lib/api";
import LegalDisclaimer from "@/components/LegalDisclaimer";

const RISK_META = {
  risky: { label: "高风险", cls: "bg-danger/15 text-danger", border: "border-l-danger" },
  warn: { label: "中风险", cls: "bg-warn/15 text-warn", border: "border-l-warn" },
  ok: { label: "低风险", cls: "bg-ok/15 text-ok", border: "border-l-ok" },
} as const;

/**
 * P1-5 视图：合同条款红黄绿标注 + 汇总条 + 时效 diff 弹层。
 */
export default function ContractView({ result }: { result: ContractScanResponse }) {
  const [timeline, setTimeline] = useState<StatuteTimeline | null>(null);
  const [loadingId, setLoadingId] = useState("");

  async function showTimeline(statuteId: string) {
    if (loadingId) return;
    setLoadingId(statuteId);
    try {
      setTimeline(await getStatuteTimeline(statuteId));
    } catch {
      setTimeline(null);
    } finally {
      setLoadingId("");
    }
  }

  return (
    <section className="card p-5">
      <h2 className="text-base font-semibold text-fg">合同风险扫描（逐条红黄绿）</h2>

      {/* 汇总条 */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="chip bg-danger/15 text-danger">高风险 × {result.summary.risky ?? 0}</span>
        <span className="chip bg-warn/15 text-warn">中风险 × {result.summary.warn ?? 0}</span>
        <span className="chip bg-ok/15 text-ok">低风险 × {result.summary.ok ?? 0}</span>
        <span className="ml-auto text-xs text-fg-subtle">
          共 {result.clauses.length} 条款 · 规则引擎标注，仅供参考
        </span>
      </div>

      {/* 条款卡片 */}
      <div className="mt-4 space-y-3">
        {result.clauses.map((c: ContractClause) => {
          const meta = RISK_META[c.risk_level];
          return (
            <div key={c.index} className={`rounded-lg border border-line border-l-4 bg-surface-sunken/50 p-4 ${meta.border}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`chip ${meta.cls}`}>{meta.label}</span>
                <span className="text-sm font-medium text-fg-muted">{c.heading}</span>
                {c.risk_type && <span className="text-xs text-fg-subtle">{c.risk_type}</span>}
              </div>
              <p className="mt-2 text-sm leading-6 text-fg-muted">{c.text}</p>
              {c.risk_level !== "ok" && (
                <>
                  <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-fg-subtle">{c.explanation}</p>
                  <p className="mt-1.5 whitespace-pre-wrap text-xs leading-5 text-accent-soft">
                    修改建议：{c.suggestion}
                  </p>
                </>
              )}
              {c.citation_ids.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {c.citation_ids.map((id) => (
                    <button
                      key={id}
                      className="chip border border-line font-mono text-fg-subtle hover:bg-surface-hover"
                      onClick={() => showTimeline(id)}
                      title="查看法条时效与修订 diff"
                      aria-label={`查看 ${id} 时效追踪`}
                    >
                      {id}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 时效 diff 弹层（P1-7） */}
      {timeline && (
        <div className="mt-4 rounded-lg border border-accent/40 bg-surface-sunken/60 p-4" role="region" aria-label="法条时效追踪">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-fg-muted">
              时效追踪 · {timeline.law_title} {timeline.article_no}
            </h3>
            <button
              className="btn btn-ghost px-2 py-1 text-xs"
              onClick={() => setTimeline(null)}
              aria-label="关闭时效追踪"
            >
              关闭
            </button>
          </div>
          <p className="mt-2 text-xs leading-5 text-warn">{timeline.advice}</p>
          {timeline.revisions.map((r, i) => (
            <div key={i} className="mt-3 rounded border border-line p-3">
              <p className="text-xs font-medium text-fg-muted">
                {r.date} · {r.version}
              </p>
              <p className="mt-1 text-xs text-fg-subtle">{r.change_summary}</p>
              {r.old_excerpt && (
                <p className="mt-2 border-l-2 border-danger/60 pl-2 text-xs leading-5 text-fg-subtle">
                  旧文本：{r.old_excerpt}
                </p>
              )}
              {r.new_excerpt && (
                <p className="mt-1 border-l-2 border-ok/60 pl-2 text-xs leading-5 text-fg-muted">
                  新文本：{r.new_excerpt}
                </p>
              )}
            </div>
          ))}
          {!timeline.revisions.length && (
            <p className="mt-2 text-xs text-fg-subtle">暂无修订记录；生效日期 {timeline.effective_date ?? "未知"}</p>
          )}
        </div>
      )}
      <LegalDisclaimer className="mt-4" />
    </section>
  );
}
