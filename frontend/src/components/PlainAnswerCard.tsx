"use client";

import { ChevronDown, ShieldAlert } from "lucide-react";
import { renderTextWithTerms } from "@/components/TermHint";
import { usePlainMode } from "@/lib/plain-mode";
import {
  buildPlainExplanation,
  type PlainExplanation,
  type PlainExplanationInput,
} from "@/lib/plain-explain";

/**
 * 白话/原文分区卡（大白话解释层的通用展示容器）。
 *
 * 分区结构（通俗模式开）：
 *   ① 大白话结论区（headline + reasons，术语可点击释义）
 *   ② 风险提示区（原样行，绝不省略）
 *   ③ 法条/依据溯源区（可折叠 <details>，专业内容原样放这里）
 *
 * 通俗模式关：直接渲染专业区（恢复现有展示，不套白话层）。
 */
export default function PlainAnswerCard({
  explanation,
  sourceLabel = "法条原文与专业分析",
  source,
  className = "",
}: {
  explanation: PlainExplanation;
  /** 专业内容节点（法条原文 / 要件分析 / 裁决明细等，原样传入） */
  source: React.ReactNode;
  sourceLabel?: string;
  className?: string;
}) {
  return (
    <div className={`flex flex-col gap-4 ${className}`}>
      {/* ① 大白话结论区（上） */}
      <section aria-label="大白话解释" className="neu-inset p-4">
        <p className="text-sm font-semibold leading-7 text-fg">
          {renderTextWithTerms(explanation.headline)}
        </p>
        <ul className="mt-2.5 space-y-1.5">
          {explanation.reasons.map((r, i) => (
            <li key={i} className="flex gap-1.5 text-xs leading-6 text-fg-muted">
              <span aria-hidden className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-accent/60" />
              <span>{renderTextWithTerms(r)}</span>
            </li>
          ))}
        </ul>
        <p className="mt-2.5 text-[11px] leading-5 text-fg-subtle">
          带下划线的词可以点开看通俗释义（附类比）。白话只是说明，结论以原文为准。
        </p>
      </section>

      {/* ② 风险提示区（原样行，先于折叠区展示，确保不被折叠隐藏） */}
      {explanation.warnings.length > 0 && (
        <section
          aria-label="风险与限制提示"
          className="rounded-xl border border-warn/40 bg-warn/10 p-3.5"
        >
          <p className="flex items-center gap-1.5 text-xs font-semibold text-warn">
            <ShieldAlert size={13} aria-hidden /> 风险与限制（原样保留，不因通俗模式省略）
          </p>
          <ul className="mt-1.5 space-y-1">
            {explanation.warnings.map((w, i) => (
              <li key={i} className="whitespace-pre-wrap text-xs leading-5 text-fg-muted">
                · {w}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ③ 法条/依据溯源区（可折叠，专业内容原样） */}
      <details className="card group p-0">
        <summary
          className="flex min-h-[44px] cursor-pointer flex-wrap items-center gap-2 px-4 py-2.5 text-xs font-medium text-fg-muted [&::-webkit-details-marker]:hidden"
          aria-label={`展开或收起：${sourceLabel}`}
        >
          <ChevronDown
            size={14}
            aria-hidden
            className="transition-transform group-open:rotate-180"
          />
          {sourceLabel}
          <span className="ml-auto text-[11px] text-fg-subtle">点击展开 / 收起</span>
        </summary>
        <div className="border-t border-line px-4 pb-4 pt-3">{source}</div>
      </details>
    </div>
  );
}

/**
 * 接入封装：按全局通俗模式开关决定渲染白话分区卡还是原专业内容。
 * 各结果区（对话/意见书/状态机/裁决）统一走这里，保证跨页面行为一致。
 */
export function PlainAnswerSection({
  input,
  source,
  sourceLabel,
  className,
  professional,
}: {
  input: PlainExplanationInput;
  source: React.ReactNode;
  sourceLabel?: string;
  className?: string;
  /** 通俗模式关闭时渲染的专业视图（即现有展示，原样） */
  professional: React.ReactNode;
}) {
  const [mode] = usePlainMode();
  if (mode === "pro") return <>{professional}</>;
  const explanation = buildPlainExplanation(input);
  return (
    <PlainAnswerCard
      explanation={explanation}
      source={source}
      sourceLabel={sourceLabel}
      className={className}
    />
  );
}
