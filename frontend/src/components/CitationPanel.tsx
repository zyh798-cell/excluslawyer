"use client";

import { useState } from "react";
import type { Citation, EffectiveStatus } from "@/lib/api";
import LegalDisclaimer from "@/components/LegalDisclaimer";

const STATUS_META: Record<EffectiveStatus, { label: string; cls: string }> = {
  effective: { label: "现行有效", cls: "bg-ok/15 text-ok" },
  amended: { label: "已修订", cls: "bg-warn/15 text-warn" },
  repealed: { label: "已废止", cls: "bg-danger/15 text-danger" },
  unknown: { label: "时效未知", cls: "bg-surface-hover text-fg-muted" },
};

/**
 * 溯源面板（P0-4）：右侧边栏展示引用法条，点击展开原文。
 * 时效状态用徽章硬标注——铁律 3 的可视化落点。
 */
export default function CitationPanel({ citations }: { citations: Citation[] }) {
  const [openId, setOpenId] = useState<string | null>(null);

  if (citations.length === 0) {
    return (
      <div className="card p-5 text-sm text-fg-muted">
        暂无引用。EXCLUSLAWYER 的铁律是：没有法条依据就不给结论——这叫「证据不足」，不叫「AI 幻觉」。
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-fg-muted">
        溯源面板 · 引用法条（{citations.length}）
      </h2>
      {citations.map((c) => {
        const meta = STATUS_META[c.effective_status] ?? STATUS_META.unknown;
        const open = openId === c.statute_id;
        return (
          <div key={c.statute_id} className="card overflow-hidden">
            <button
              className="flex w-full items-start justify-between gap-3 p-4 text-left hover:bg-surface-hover/60"
              onClick={() => setOpenId(open ? null : c.statute_id)}
              aria-expanded={open}
              aria-label={`${c.law_title} ${c.article_no}，${meta.label}，点击${open ? "收起" : "展开"}原文`}
            >
              <div>
                <p className="text-sm font-medium text-fg">
                  {c.law_title} {c.article_no}
                </p>
                <p className="mt-1 text-xs text-fg-subtle">
                  {c.jurisdiction} · {c.language} · 相关度 {c.score.toFixed(2)}
                </p>
              </div>
              <span className={`chip shrink-0 ${meta.cls}`}>{meta.label}</span>
            </button>
            {open && (
              <div className="border-t border-line bg-surface-sunken/50 p-4">
                <p className="text-sm leading-7 text-fg-muted">{c.text}</p>
                {c.gloss && (
                  <p className="mt-2 text-xs text-fg-subtle">中文释义：{c.gloss}</p>
                )}
                <dl className="mt-3 grid grid-cols-2 gap-2 text-xs text-fg-subtle">
                  <div>
                    <dt className="inline text-fg-subtle">生效日期：</dt>
                    <dd className="inline">{c.effective_date ?? "未知"}</dd>
                  </div>
                  <div>
                    <dt className="inline text-fg-subtle">ID：</dt>
                    <dd className="inline font-mono">{c.statute_id}</dd>
                  </div>
                </dl>
                {c.amended_history.length > 0 && (
                  <div className="mt-2 text-xs text-warn">
                    修订历史：{c.amended_history.join("；")}
                  </div>
                )}
                {c.source_url && (
                  <a
                    href={c.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-block text-xs text-accent-soft underline"
                    aria-label="打开官方法规源页面"
                  >
                    官方法规源 ↗
                  </a>
                )}
              </div>
            )}
          </div>
        );
      })}
      <LegalDisclaimer />
    </div>
  );
}
