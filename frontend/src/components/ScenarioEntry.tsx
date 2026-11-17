"use client";

import { useState } from "react";
import { Check, Sparkles } from "lucide-react";
import ScenarioGrid from "@/components/ScenarioGrid";
import ScenarioQuestionnaire from "@/components/ScenarioQuestionnaire";
import { Skeleton } from "@/components/Skeleton";
import { showToast } from "@/components/Toast";
import type { JurisdictionCode, Scenario } from "@/config/scenarios";

/**
 * 场景化入口（普通人友好层 P0）。
 *
 * 流程：场景卡片 → 分步问卷 → 生成结构化案情摘要 → 回传给提问框（用户可再编辑）。
 * 说明：本层纯前端采集，不新增后端问卷逻辑；最终仍复用既有 /api/ask 流程。
 */
export default function ScenarioEntry({
  jurisdiction,
  onJurisdictionChange,
  onSummary,
}: {
  jurisdiction: JurisdictionCode;
  onJurisdictionChange: (j: JurisdictionCode) => void;
  onSummary: (summary: string, scenario: Scenario) => void;
}) {
  const [active, setActive] = useState<Scenario | null>(null);
  const [done, setDone] = useState<{ scenario: Scenario; summary: string } | null>(null);
  const [generating, setGenerating] = useState(false);

  function selectScenario(s: Scenario) {
    setDone(null);
    setActive(s);
    // 场景若与当前法域不匹配，自动切到该场景关联的第一个法域（普通人不需要懂法域差异）
    if (!s.jurisdictions.includes(jurisdiction)) {
      onJurisdictionChange(s.jurisdictions[0]);
    }
  }

  async function complete(summary: string) {
    if (!active) return;
    setGenerating(true);
    // 摘要生成是同步的；用一次微任务让「整理中」骨架可见，避免预填跳变突兀
    await Promise.resolve();
    setGenerating(false);
    setDone({ scenario: active, summary });
    setActive(null);
    onSummary(summary, active);
    showToast("案情摘要已填入提问框，可修改后再发送", "ok");
  }

  return (
    <div className="flex flex-col gap-4">
      {!active && (
        <section className="card p-5" aria-label="生活场景选择">
          <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h2 className="text-base font-semibold text-fg">不知道从哪问起？选一个常见场景</h2>
            <p className="text-xs text-fg-subtle">
              选场景后按提示填几步，案情摘要会自动填进提问框；也可以直接在下方面板自由提问。
            </p>
          </header>
          <div className="mt-4">
            <ScenarioGrid onSelect={selectScenario} activeJurisdiction={jurisdiction} />
          </div>
        </section>
      )}

      {active && (
        <ScenarioQuestionnaire
          scenario={active}
          onBack={() => setActive(null)}
          onComplete={complete}
        />
      )}

      {generating && (
        <div className="card p-4" aria-busy="true" aria-live="polite">
          <span className="sr-only">正在整理案情摘要</span>
          <Skeleton className="h-4 w-1/3" />
          <div className="mt-3 space-y-2">
            <Skeleton className="h-3.5" style={{ width: "88%" }} />
            <Skeleton className="h-3.5" style={{ width: "72%" }} />
          </div>
        </div>
      )}

      {done && !active && (
        <div className="card flex flex-wrap items-center gap-2 p-4 text-xs" role="status">
          <Check size={15} className="text-ok" aria-hidden />
          <span className="text-fg-muted">
            已按「{done.scenario.name}」整理案情摘要并填入提问框，可直接修改后发送。
          </span>
          <button
            type="button"
            className="btn btn-ghost ml-auto min-h-[44px] px-3 py-1.5"
            onClick={() => selectScenario(done.scenario)}
            aria-label="重新填写该场景问卷"
          >
            <Sparkles size={13} aria-hidden /> 重新填写
          </button>
        </div>
      )}
    </div>
  );
}
