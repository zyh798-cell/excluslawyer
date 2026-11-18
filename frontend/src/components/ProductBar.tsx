"use client";

import BrandMark from "@/components/BrandMark";
import { JURISDICTION_LABELS, type JurisdictionCode } from "@/config/scenarios";

/**
 * 首页顶部产品标识 + 法域选择器。
 *
 * - 标识：内联 SVG 天平徽记（无位图），文案说明产品定位；
 * - 法域：分段按钮（radiogroup），点击即切换全局法域，与咨询卡内的 select 双向同步；
 * - 热区 ≥44×44px，窄屏 375px 优先（换行不溢出）。
 */
export default function ProductBar({
  jurisdiction,
  onJurisdictionChange,
}: {
  jurisdiction: JurisdictionCode;
  onJurisdictionChange: (j: JurisdictionCode) => void;
}) {
  return (
    <section
      className="card flex flex-wrap items-center gap-x-4 gap-y-3 p-4 sm:p-5"
      aria-label="产品标识与法域选择"
    >
      <BrandMark size={40} />
      <div className="min-w-0">
        <p className="text-base font-bold tracking-tight text-fg">
          EXCLUS<span className="text-accent-soft">LAWYER</span>
        </p>
        <p className="mt-0.5 text-xs leading-5 text-fg-subtle">
          多法域法律推理引擎 · 每条结论必挂现行法条原文，检索不到就说「证据不足」
        </p>
      </div>

      <div className="ml-auto flex flex-col gap-1.5">
        <span className="text-xs font-medium text-fg-muted" id="jur-picker-label">
          适用法域
        </span>
        <div
          className="flex flex-wrap gap-1.5"
          role="radiogroup"
          aria-labelledby="jur-picker-label"
        >
          {(Object.keys(JURISDICTION_LABELS) as JurisdictionCode[]).map((code) => (
            <button
              key={code}
              type="button"
              role="radio"
              aria-checked={jurisdiction === code}
              onClick={() => onJurisdictionChange(code)}
              aria-label={`法域：${JURISDICTION_LABELS[code]}`}
              className={`min-h-[44px] rounded-xl border px-3 py-1.5 text-xs font-medium transition ${
                jurisdiction === code
                  ? "border-transparent text-accent-fg"
                  : "border-line text-fg-muted hover:text-fg"
              }`}
              style={
                jurisdiction === code
                  ? { background: "rgb(var(--c-accent))" }
                  : { background: "rgb(var(--c-surface-sunken))" }
              }
            >
              {JURISDICTION_LABELS[code]}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
