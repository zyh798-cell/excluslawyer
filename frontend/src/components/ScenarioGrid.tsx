"use client";

import { ArrowRight } from "lucide-react";
import ScenarioIcon from "@/components/ScenarioIcon";
import {
  JURISDICTION_LABELS,
  SCENARIOS,
  type JurisdictionCode,
  type Scenario,
} from "@/config/scenarios";

/**
 * 生活场景卡片栅格（普通人友好层 P0 入口）。
 *
 * 布局：手机 1 列 / 平板 2 列 / 桌面 3 列 / 超宽 4 列。
 * 视觉：玻璃拟态卡片 + 悬停弹性（prefers-reduced-motion 下由全局 CSS 自动降级）。
 * 可访问：整卡为 button，热区 ≥44×44px；法域徽章与问题标签用真实文本，不靠图标猜义。
 */
export default function ScenarioGrid({
  onSelect,
  activeJurisdiction,
}: {
  onSelect: (scenario: Scenario) => void;
  activeJurisdiction: JurisdictionCode;
}) {
  return (
    <ul
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4"
      aria-label="生活场景入口"
    >
      {SCENARIOS.map((s) => {
        const matches = s.jurisdictions.includes(activeJurisdiction);
        return (
          <li key={s.id} className="flex">
            {/* 不设 aria-label：可访问名直接取自可见文本，避免 label-content-name-mismatch */}
            <button
              type="button"
              onClick={() => onSelect(s)}
              className="card hover-elastic group flex min-h-[132px] w-full flex-col gap-2 p-4 text-left"
            >
              <span className="flex items-center gap-2">
                <span className="neu-inset flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-accent-soft">
                  <ScenarioIcon name={s.icon} size={18} />
                </span>
                <span className="text-sm font-semibold text-fg">{s.name}</span>
                <ArrowRight
                  size={15}
                  aria-hidden
                  className="ml-auto text-fg-muted transition-transform group-hover:translate-x-0.5"
                />
              </span>

              <span className="text-xs leading-5 text-fg-muted">{s.summary}</span>

              <span className="mt-auto flex flex-wrap items-center gap-1.5 pt-1">
                {s.tags.map((t) => (
                  <span key={t} className="chip border border-line text-fg-muted">
                    {t}
                  </span>
                ))}
              </span>

              <span className="flex flex-wrap items-center gap-1.5">
                {s.jurisdictions.map((j) => (
                  <span
                    key={j}
                    className={`chip border jur-${j.toLowerCase()} ${
                      j === activeJurisdiction ? "font-semibold" : ""
                    }`}
                  >
                    {JURISDICTION_LABELS[j]}
                  </span>
                ))}
                {!matches && (
                  <span className="text-[11px] text-fg-muted">（选它将自动切换法域）</span>
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
