"use client";

import { useSyncExternalStore } from "react";

/**
 * 通俗模式（大白话解释层）全局开关。
 *
 * - 默认开启；状态持久化到 localStorage（键 lexsentinel.plain）；
 * - 用 useSyncExternalStore 做模块级订阅，对话页 / KG 面板 / 模拟法庭裁决卡片
 *   共享同一份状态，任何一处切换全站同步；
 * - SSR 安全：服务端无 window 时返回默认值 true。
 */

export type PlainMode = "plain" | "pro";

const PLAIN_STORAGE_KEY = "lexsentinel.plain";
const DEFAULT_MODE: PlainMode = "plain";

let current: PlainMode = DEFAULT_MODE;
const listeners = new Set<() => void>();

function readStored(): PlainMode {
  if (typeof window === "undefined") return DEFAULT_MODE;
  try {
    return localStorage.getItem(PLAIN_STORAGE_KEY) === "pro" ? "pro" : DEFAULT_MODE;
  } catch {
    return DEFAULT_MODE; // 隐私模式 localStorage 不可用，回退默认
  }
}

// 首次读取（客户端）
if (typeof window !== "undefined") {
  current = readStored();
}

export function getPlainMode(): PlainMode {
  return current;
}

export function setPlainMode(mode: PlainMode) {
  if (mode === current) return;
  current = mode;
  try {
    localStorage.setItem(PLAIN_STORAGE_KEY, mode);
  } catch {
    /* 隐私模式下不可写，状态仍在本会话内生效 */
  }
  listeners.forEach((l) => l());
}

export function togglePlainMode(): PlainMode {
  const next: PlainMode = current === "plain" ? "pro" : "plain";
  setPlainMode(next);
  return next;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** 跨页面一致的通俗模式状态（对话页 / KG / 模拟法庭共用）。 */
export function usePlainMode(): [PlainMode, (m: PlainMode) => void] {
  const mode = useSyncExternalStore(
    subscribe,
    () => current,
    () => DEFAULT_MODE
  );
  return [mode, setPlainMode];
}

export const PLAIN_MODE_LABELS: Record<PlainMode, string> = {
  plain: "通俗模式",
  pro: "专业模式",
};
