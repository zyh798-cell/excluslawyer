"use client";

/**
 * 双主题管理：html.dark 类切换 + localStorage 持久化 + 系统偏好兜底。
 * 与 layout 内联防闪烁脚本共用同一个存储键。
 */

export type Theme = "light" | "dark";

const THEME_STORAGE_KEY = "lexsentinel.theme";

export function getStoredTheme(): Theme | null {
  if (typeof window === "undefined") return null;
  try {
    const t = localStorage.getItem(THEME_STORAGE_KEY);
    return t === "light" || t === "dark" ? t : null;
  } catch {
    return null;
  }
}

export function getSystemTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function getActiveTheme(): Theme {
  return getStoredTheme() ?? getSystemTheme();
}

export function applyTheme(theme: Theme) {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", theme === "dark");
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    /* 隐私模式下 localStorage 不可用，忽略 */
  }
  // 通知图谱画布等订阅方重取 CSS 变量颜色
  window.dispatchEvent(new CustomEvent("lextheme", { detail: theme }));
}

export function toggleTheme(): Theme {
  const next: Theme = document.documentElement.classList.contains("dark") ? "light" : "dark";
  applyTheme(next);
  return next;
}
