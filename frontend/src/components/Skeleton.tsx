/**
 * 骨架屏：加载态占位（shimmer 动画在 prefers-reduced-motion 下自动关闭）。
 */
export function Skeleton({
  className = "",
  style,
}: {
  className?: string;
  style?: React.CSSProperties;
}) {
  return <div className={`skeleton ${className}`} style={style} aria-hidden="true" />;
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="card p-5" aria-busy="true" aria-live="polite">
      <span className="sr-only">加载中</span>
      <Skeleton className="h-4 w-2/5" />
      <div className="mt-4 space-y-2.5">
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton key={i} className="h-3.5" style={{ width: `${92 - i * 11}%` }} />
        ))}
      </div>
    </div>
  );
}
