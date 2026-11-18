/**
 * 品牌标识：内联 SVG（无位图、无 emoji），亮暗主题共用，随文字色走 CSS 变量。
 * 尺寸自适应，aria-hidden（页面已有可见文字标识，无需重复朗读）。
 */
export default function BrandMark({ size = 36 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="presentation"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id="excluslawyer-brand-ring" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="rgb(var(--c-accent))" />
          <stop offset="100%" stopColor="rgb(var(--c-accent-soft))" />
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="30" fill="none" stroke="url(#excluslawyer-brand-ring)" strokeWidth="2.5" />
      <circle cx="32" cy="32" r="25" fill="none" stroke="rgb(var(--c-line))" strokeWidth="1.5" />
      {/* 天平：法律推理的通用符号 */}
      <g
        stroke="rgb(var(--c-accent-soft))"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      >
        <path d="M32 16v32" />
        <path d="M20 48h24" />
        <path d="M16 24h32" />
        <path d="M16 24l-7 11h14z" />
        <path d="M48 24l-7 11h14z" />
        <circle cx="32" cy="16" r="2.6" fill="rgb(var(--c-accent-soft))" stroke="none" />
      </g>
    </svg>
  );
}
