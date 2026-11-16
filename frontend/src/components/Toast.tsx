"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";

export type ToastKind = "ok" | "error" | "warn" | "info";

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

let toastId = 0;
const listeners = new Set<(t: ToastItem) => void>();

/** 全局 Toast 出口（替代 alert()，不阻塞无障碍焦点流）。 */
export function showToast(message: string, kind: ToastKind = "info") {
  const item: ToastItem = { id: ++toastId, kind, message };
  listeners.forEach((fn) => fn(item));
}

const ICONS = {
  ok: CheckCircle2,
  error: X,
  warn: AlertTriangle,
  info: Info,
} as const;

export default function ToastHost() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(() => {
    const onToast = (t: ToastItem) => {
      setItems((prev) => [...prev, t]);
      setTimeout(() => setItems((prev) => prev.filter((x) => x.id !== t.id)), 4200);
    };
    listeners.add(onToast);
    return () => {
      listeners.delete(onToast);
    };
  }, []);

  if (items.length === 0) return null;
  return (
    <div className="toast-stack" role="status" aria-live="polite" aria-atomic="false">
      {items.map((t) => {
        const Icon = ICONS[t.kind];
        return (
          <div key={t.id} className={`toast toast-${t.kind}`} role="alert">
            <Icon size={16} aria-hidden className="mt-0.5 shrink-0" />
            <span>{t.message}</span>
            <button
              aria-label="关闭提示"
              className="ml-2 shrink-0 rounded p-0.5 opacity-60 hover:opacity-100"
              onClick={() => setItems((prev) => prev.filter((x) => x.id !== t.id))}
            >
              <X size={13} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
