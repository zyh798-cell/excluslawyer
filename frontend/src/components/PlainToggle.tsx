"use client";

import { MessageSquareText, Scale } from "lucide-react";
import { usePlainMode } from "@/lib/plain-mode";

/**
 * 通俗模式开关（大白话解释层）。
 *
 * - role="switch" + aria-checked，可访问名明确；
 * - 状态来自全局 store（lib/plain-mode），对话页 / KG / 模拟法庭共用、全站同步；
 * - 热区 ≥44px；图标内联 SVG，无 emoji。
 */
export default function PlainToggle({ className = "" }: { className?: string }) {
  const [mode, setMode] = usePlainMode();
  const plain = mode === "plain";

  return (
    <button
      type="button"
      role="switch"
      aria-checked={plain}
      aria-label="通俗模式（大白话解释优先）"
      onClick={() => setMode(plain ? "pro" : "plain")}
      className={`btn ${plain ? "btn-primary" : "btn-ghost"} min-h-[44px] px-3 py-1.5 text-xs ${className}`}
      title={plain ? "当前：先看大白话，法条原文收进可展开区" : "当前：直接展示专业分析"}
    >
      {plain ? <MessageSquareText size={14} aria-hidden /> : <Scale size={14} aria-hidden />}
      {plain ? "通俗模式：开" : "通俗模式：关"}
    </button>
  );
}
