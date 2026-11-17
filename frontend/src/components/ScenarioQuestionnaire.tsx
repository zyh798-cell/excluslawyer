"use client";

import { useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Check, Sparkles } from "lucide-react";
import ScenarioIcon from "@/components/ScenarioIcon";
import { buildScenarioSummary, type Scenario } from "@/config/scenarios";

/**
 * 场景分步问卷：把生活场景的零散信息收集成结构化案情摘要。
 *
 * - 一次一个问题，底部「上一步 / 下一步」推进，右上角进度与步数提示；
 * - 必填项未填时下一步禁用并给出原因（不静默跳过）；
 * - 最后一步生成结构化摘要，回传给调用方预填提问框 —— 用户仍可自由修改后再发送。
 */
export default function ScenarioQuestionnaire({
  scenario,
  onBack,
  onComplete,
}: {
  scenario: Scenario;
  onBack: () => void;
  onComplete: (summary: string) => void;
}) {
  const [step, setStep] = useState(0);
  const [values, setValues] = useState<Record<string, string>>({});

  const fields = scenario.fields;
  const field = fields[step];
  const isLast = step === fields.length - 1;
  const current = values[field.key] ?? "";
  const missingRequired = Boolean(field.required) && current.trim().length === 0;

  const progress = useMemo(
    () => Math.round(((step + 1) / fields.length) * 100),
    [step, fields.length]
  );

  function setValue(v: string) {
    setValues((prev) => ({ ...prev, [field.key]: v }));
  }

  function goNext() {
    if (missingRequired) return;
    if (isLast) {
      onComplete(buildScenarioSummary(scenario, values));
      return;
    }
    setStep((s) => Math.min(s + 1, fields.length - 1));
  }

  function goBack() {
    if (step === 0) {
      onBack();
      return;
    }
    setStep((s) => Math.max(s - 1, 0));
  }

  return (
    <section
      className="card p-5"
      aria-label={`${scenario.name} 情况问卷`}
      data-testid="scenario-questionnaire"
    >
      <header className="flex flex-wrap items-center gap-2">
        <span className="neu-inset flex h-9 w-9 items-center justify-center rounded-xl text-accent-soft">
          <ScenarioIcon name={scenario.icon} size={18} />
        </span>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-fg">{scenario.name} · 情况问卷</h3>
          <p className="text-xs text-fg-subtle">
            第 {step + 1} / {fields.length} 步 · 填完自动生成案情摘要，可修改后再发送
          </p>
        </div>
        <button
          type="button"
          className="btn btn-ghost ml-auto min-h-[44px] px-3 py-1.5 text-xs"
          onClick={onBack}
          aria-label="退出问卷，返回场景列表"
        >
          <ArrowLeft size={14} aria-hidden /> 退出
        </button>
      </header>

      {/* 进度条 */}
      <div
        className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-[rgb(var(--c-surface-hover))]"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress}
        aria-label="问卷进度"
      >
        <div
          className="h-full rounded-full bg-[rgb(var(--c-accent))] transition-[width] duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* 当前问题 */}
      <div className="mt-5">
        <label
          className="block text-sm font-medium text-fg"
          htmlFor={`scenario-field-${field.key}`}
        >
          {field.label}
          {field.required && <span className="ml-1 text-danger">*</span>}
        </label>
        {field.hint && <p className="mt-1 text-xs text-fg-subtle">{field.hint}</p>}

        <div className="mt-2">
          {field.type === "textarea" ? (
            <textarea
              id={`scenario-field-${field.key}`}
              className="textarea h-24 resize-y"
              placeholder={field.placeholder}
              value={current}
              onChange={(e) => setValue(e.target.value)}
            />
          ) : field.type === "select" ? (
            <select
              id={`scenario-field-${field.key}`}
              className="select"
              value={current}
              onChange={(e) => setValue(e.target.value)}
            >
              <option value="">请选择…</option>
              {field.options?.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          ) : (
            <input
              id={`scenario-field-${field.key}`}
              className="input"
              type={field.type === "number" ? "number" : field.type === "date" ? "date" : "text"}
              placeholder={field.placeholder}
              value={current}
              onChange={(e) => setValue(e.target.value)}
            />
          )}
        </div>

        {missingRequired && (
          <p className="mt-2 text-xs text-danger" role="alert">
            这一项是必填的，填完才能继续。
          </p>
        )}
      </div>

      {/* 底部操作 */}
      <div className="mt-5 flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn btn-ghost min-h-[44px]"
          onClick={goBack}
          aria-label={step === 0 ? "返回场景列表" : "上一步"}
        >
          <ArrowLeft size={15} aria-hidden /> {step === 0 ? "返回场景列表" : "上一步"}
        </button>
        <button
          type="button"
          className="btn btn-primary ml-auto min-h-[44px]"
          onClick={goNext}
          disabled={missingRequired}
          aria-label={isLast ? "生成案情摘要" : "下一步"}
        >
          {isLast ? <Sparkles size={15} aria-hidden /> : null}
          {isLast ? "生成案情摘要" : "下一步"}
          {isLast ? null : <ArrowRight size={15} aria-hidden />}
        </button>
      </div>

      {/* 已填要点回显 */}
      <div className="mt-4 border-t border-line pt-3">
        <p className="flex items-center gap-1.5 text-xs font-medium text-fg-muted">
          <Check size={13} aria-hidden /> 已填写要点
        </p>
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {fields
            .filter((f) => (values[f.key] ?? "").trim().length > 0)
            .map((f) => (
              <li key={f.key} className="chip border border-line text-fg-subtle">
                {f.label}：{values[f.key]}
              </li>
            ))}
          {fields.every((f) => (values[f.key] ?? "").trim().length === 0) && (
            <li className="text-xs text-fg-subtle">尚未填写任何内容</li>
          )}
        </ul>
      </div>
    </section>
  );
}
