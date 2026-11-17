import type { Metadata } from "next";
import "./globals.css";
import ThemeToggle from "@/components/ThemeToggle";
import ToastHost from "@/components/Toast";
import WarningIcon from "@/components/WarningIcon";
import { LEGAL_DISCLAIMER } from "@/lib/disclaimer";

export const metadata: Metadata = {
  title: "LexSentinel — 多法域法律推理引擎",
  description:
    "每条法律结论必挂现行有效法条原文。开源 · 多法域 · 双视角对抗 · BYOK。仅供参考，不构成法律意见。",
};

// 防主题闪烁（FOUC→CLS）：首帧前同步主题类（与 lib/theme.ts 同一存储键）
const THEME_INIT = `try{var t=localStorage.getItem('lexsentinel.theme');var d=t?t==='dark':window.matchMedia('(prefers-color-scheme: dark)').matches;document.documentElement.classList.toggle('dark',d);}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body>
        <header className="border-b border-line">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
            <div className="flex items-center gap-3">
              <span className="text-xl font-bold tracking-tight text-fg">
                Lex<span className="text-accent-soft">Sentinel</span>
              </span>
              <span className="chip bg-accent/15 text-accent-soft">法律副驾 · 不是聊天套壳</span>
            </div>
            <div className="flex items-center gap-4">
              <p className="text-xs text-fg-subtle">
                每条结论必挂法条原文 · 检索不到就说证据不足
              </p>
              <ThemeToggle />
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
        <footer className="mx-auto max-w-7xl px-6 pb-10 text-center">
          <p className="disclaimer inline-block text-left">
            <WarningIcon className="mr-1 inline-block align-[-2px]" />
            {LEGAL_DISCLAIMER}
          </p>
          <p className="mt-2 text-xs text-fg-subtle">AGPL-3.0 开源</p>
        </footer>
        <ToastHost />
      </body>
    </html>
  );
}
