"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { Theme, applyTheme, getActiveTheme, toggleTheme } from "@/lib/theme";

/** 双主题切换按钮（html.dark 类切换 + localStorage 持久化）。 */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    setTheme(getActiveTheme());
  }, []);

  return (
    <button
      type="button"
      aria-label={theme === "dark" ? "切换到亮色主题" : "切换到暗色主题"}
      title={theme === "dark" ? "切换到亮色主题" : "切换到暗色主题"}
      className="neu-btn flex h-9 w-9 items-center justify-center"
      onClick={() => {
        const next = toggleTheme();
        setTheme(next);
      }}
    >
      {theme === "dark" ? <Sun size={16} aria-hidden /> : <Moon size={16} aria-hidden />}
    </button>
  );
}

/** 供非 React 场景同步主题（如 G6 画布重绘）。 */
export function syncThemeClass(theme: Theme) {
  applyTheme(theme);
}
