"use client";

import { useEffect, useState } from "react";
import { Loader2, Settings2, ShieldCheck, Trash2 } from "lucide-react";
import {
  ByokConfig,
  KeyLeakSelfCheck,
  clearByokConfig,
  loadByokConfig,
  runKeyLeakSelfCheck,
  saveByokConfig,
} from "@/lib/api";
import { showToast } from "@/components/Toast";

/**
 * BYOK 设置：API Key 只存浏览器 localStorage，绝不上传后端。
 * - 输入即持久化；一键清除 = 隐私按钮
 * - 「安全自检」跑密钥泄露风险三道防线核查（存储/后端载荷/日志出口）
 */
export default function ByokSettings({ onChange }: { onChange: (cfg: ByokConfig) => void }) {
  const [open, setOpen] = useState(false);
  const [cfg, setCfg] = useState<ByokConfig>({ baseUrl: "", apiKey: "", model: "" });
  const [check, setCheck] = useState<KeyLeakSelfCheck | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    const loaded = loadByokConfig();
    setCfg(loaded);
    onChange(loaded);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const persist = (next: ByokConfig) => {
    setCfg(next);
    saveByokConfig(next);
    onChange(next);
  };

  const clearAll = () => {
    persist({ baseUrl: "", apiKey: "", model: "" });
    clearByokConfig();
    showToast("BYOK 配置已清除（localStorage 已清空）", "ok");
    setCheck(null);
  };

  const runSelfCheck = () => {
    setChecking(true);
    try {
      const result = runKeyLeakSelfCheck();
      setCheck(result);
      showToast(
        result.ok ? "安全自检通过：密钥不会离开本机浏览器" : "安全自检发现问题，请查看明细",
        result.ok ? "ok" : "error"
      );
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="card">
      <button
        className="flex w-full items-center justify-between p-4 text-left"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label="展开或收起 BYOK 设置"
      >
        <span className="flex items-center gap-2 text-sm font-medium text-fg">
          <Settings2 size={16} className="text-accent-soft" aria-hidden />
          BYOK 设置（Key 只存本地浏览器）
        </span>
        <span className={`chip ${cfg.apiKey ? "bg-ok/15 text-ok" : "bg-surface-hover text-fg-muted"}`}>
          {cfg.apiKey ? "已配置 · 前端直连" : "未配置 · 演示模式"}
        </span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-line p-4">
          <label className="block text-xs text-fg-muted">
            LLM 服务商 Base URL（OpenAI 兼容）
            <input
              className="input mt-1"
              aria-label="LLM 服务商 Base URL"
              placeholder="https://api.deepseek.com/v1"
              value={cfg.baseUrl}
              onChange={(e) => persist({ ...cfg, baseUrl: e.target.value })}
            />
          </label>
          <label className="block text-xs text-fg-muted">
            API Key（仅存 localStorage，不发后端）
            <input
              type="password"
              className="input mt-1"
              aria-label="API Key"
              autoComplete="off"
              placeholder="sk-..."
              value={cfg.apiKey}
              onChange={(e) => persist({ ...cfg, apiKey: e.target.value })}
            />
          </label>
          <label className="block text-xs text-fg-muted">
            模型名
            <input
              className="input mt-1"
              aria-label="模型名"
              placeholder="deepseek-chat / gpt-4o / claude-sonnet-4-5"
              value={cfg.model}
              onChange={(e) => persist({ ...cfg, model: e.target.value })}
            />
          </label>
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] leading-4 text-fg-subtle">
              配置后走 BYOK 流程：检索 → 浏览器直连 LLM → 回后端做 NLI 校验。
              未配置时走服务端演示模式（只引法条不生成）。
            </p>
            <button className="btn btn-danger px-2.5 py-1.5 text-xs" onClick={clearAll} aria-label="一键清除 BYOK 配置">
              <Trash2 size={13} aria-hidden /> 一键清除
            </button>
          </div>

          {/* 密钥泄露风险自检 */}
          <div className="rounded-lg border border-line bg-surface-sunken/50 p-3">
            <div className="flex items-center justify-between">
              <p className="flex items-center gap-1.5 text-xs font-medium text-fg">
                <ShieldCheck size={14} aria-hidden className="text-ok" /> 密钥泄露风险自检
              </p>
              <button
                className="btn btn-ghost px-2.5 py-1 text-xs"
                onClick={runSelfCheck}
                disabled={checking}
                aria-label="运行密钥泄露风险自检"
              >
                {checking ? <Loader2 size={12} className="animate-spin" aria-hidden /> : null}
                运行自检
              </button>
            </div>
            {check && (
              <ul className="mt-2 space-y-1">
                {check.items.map((it, i) => (
                  <li key={i} className="text-[11px] leading-4 text-fg-muted">
                    <span className={it.passed ? "text-ok" : "text-danger"}>
                      {it.passed ? "✓" : "✗"} {it.name}
                    </span>
                    <span className="block text-fg-subtle">{it.detail}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
