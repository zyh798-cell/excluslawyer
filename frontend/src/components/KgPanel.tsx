"use client";

import { useMemo, useState } from "react";
import {
  BookMarked,
  ChevronDown,
  ChevronUp,
  Loader2,
  Network,
  Search,
  Scale,
} from "lucide-react";
import { KgQueryResponse, kgQuery, kgStats } from "@/lib/api";
import LegalDisclaimer from "@/components/LegalDisclaimer";
import KgGraphCanvas from "@/components/KgGraphCanvas";
import { showToast } from "@/components/Toast";

/** 各法域官方法源门户（溯源链接）。 */
const OFFICIAL_SOURCES: Record<string, { name: string; url: string }> = {
  CN: { name: "国家法律法规数据库", url: "https://flk.npc.gov.cn/" },
  JP: { name: "e-Gov 法令検索", url: "https://laws.e-gov.go.jp/" },
  KR: { name: "국가법령정보센터", url: "https://www.law.go.kr/" },
  SG: { name: "Singapore Statutes Online", url: "https://sso.agc.gov.sg/" },
};

const JUR_FILTERS = [
  { code: null, label: "全部" },
  { code: "CN", label: "中国" },
  { code: "JP", label: "日本" },
  { code: "KR", label: "韩国" },
  { code: "SG", label: "新加坡" },
] as const;

const JUR_CHIP_CLS: Record<string, string> = {
  CN: "jur-cn",
  JP: "jur-jp",
  KR: "jur-kr",
  SG: "jur-sg",
};

function jurOf(statuteId: string): string {
  const m = /^(?:s:)?(CN|JP|KR|SG)-/.exec(statuteId);
  return m ? m[1] : "";
}

const CASE_PAGE_SIZE = 2;

/**
 * P2-10 知识图谱面板：多跳问答 + G6 画布 + 跨法域切换 + 判例展示。
 * - 法域切换只做展示层过滤（useMemo 派生），不改动/不重新拉取缓存数据
 * - 判例分页 + 超长折叠 + 各国官方法源溯源链接
 * - 切换法域走 View Transition（FLIP 共享转场），不支持时自动降级普通过渡
 */
export default function KgPanel() {
  const [q, setQ] = useState("");
  const [result, setResult] = useState<KgQueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [jurFilter, setJurFilter] = useState<string | null>(null);
  const [casePage, setCasePage] = useState(0);
  const [collapsed, setCollapsed] = useState<Record<number, boolean>>({});

  async function onQuery() {
    if (!q.trim() || loading) return;
    setLoading(true);
    try {
      const r = await kgQuery(q);
      setResult(r); // 全量缓存，法域切换只过滤展示
      setJurFilter(null);
      setCasePage(0);
      setCollapsed({});
      if (!r.matched_node) showToast("图谱中未命中对应概念，换个法律术语试试", "warn");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "图谱查询失败", "error");
    } finally {
      setLoading(false);
    }
  }

  function switchJurisdiction(code: string | null) {
    if (code === jurFilter) return;
    const apply = () => {
      setJurFilter(code);
      setCasePage(0);
    };
    // FLIP/View Transition 共享转场（不支持则普通切换）
    const doc = document as Document & { startViewTransition?: (cb: () => void) => void };
    if (typeof doc.startViewTransition === "function" && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      doc.startViewTransition(apply);
    } else {
      apply();
    }
  }

  /** 展示层派生：按法域过滤条文 chips / 画布节点，绝不改写 result 缓存。 */
  const shownStatutes = useMemo(() => {
    if (!result) return [];
    return result.statute_ids.filter((id) => !jurFilter || jurOf(id) === jurFilter);
  }, [result, jurFilter]);

  const cases = useMemo(() => result?.related_cases ?? [], [result]);
  const casePages = Math.max(1, Math.ceil(cases.length / CASE_PAGE_SIZE));
  const pageCases = cases.slice(casePage * CASE_PAGE_SIZE, (casePage + 1) * CASE_PAGE_SIZE);

  return (
    <section className="card p-5">
      <h2 className="flex items-center gap-2 text-base font-semibold text-fg">
        <Network size={17} className="text-accent-soft" aria-hidden /> 法律知识图谱 · 多跳问答
      </h2>

      <div className="mt-3 flex gap-2">
        <input
          className="input flex-1"
          placeholder="例如：违约责任的构成要件是什么 / Chwee Kin Keong 标价错误"
          value={q}
          aria-label="知识图谱查询问题"
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onQuery()}
        />
        <button
          className="btn btn-primary"
          onClick={onQuery}
          disabled={loading || !q.trim()}
          aria-label="查询知识图谱"
        >
          {loading ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Search size={15} aria-hidden />}
          查询
        </button>
      </div>

      {/* 法域切换（展示过滤 + View Transition 转场） */}
      <div className="mt-3 flex flex-wrap items-center gap-2" role="group" aria-label="按法域过滤">
        {JUR_FILTERS.map((j) => (
          <button
            key={j.code ?? "all"}
            aria-pressed={jurFilter === j.code}
            aria-label={`过滤${j.label}法域节点`}
            className={`kg-jur-chip chip border ${
              j.code ? JUR_CHIP_CLS[j.code] : "border-line text-fg-muted"
            } ${jurFilter === j.code ? "ring-2 ring-accent/50" : ""}`}
            onClick={() => switchJurisdiction(j.code)}
          >
            {j.label}
          </button>
        ))}
        <span className="ml-auto text-xs text-fg-subtle">
          节点色系：中国红 · 日本洋红 · 韩国青 · 新加坡琥珀（跟随主题变量）
        </span>
      </div>

      {result && (
        <div className="mt-3">
          {/* G6 画布（懒加载；仅此面板有 Canvas 负载，聊天页为零） */}
          <KgGraphCanvas result={result} jurFilter={jurFilter} />

          {/* 文字版结构化展开 */}
          <div className="mt-3 rounded-lg border border-line bg-surface-sunken/50 p-4">
            <p className="whitespace-pre-wrap text-sm leading-6 text-fg-muted">{result.answer}</p>

            {shownStatutes.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1" aria-label="引用条文">
                {shownStatutes.map((id) => {
                  const jur = jurOf(id);
                  return (
                    <span key={id} className={`chip border font-mono text-xs ${JUR_CHIP_CLS[jur] ?? "border-line text-fg-subtle"}`}>
                      {id}
                    </span>
                  );
                })}
              </div>
            )}

            {/* 溯源链接到各法域官方法源 */}
            {shownStatutes.length > 0 && (
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                <BookMarked size={13} aria-hidden className="text-fg-subtle" />
                {Object.entries(
                  shownStatutes.reduce<Record<string, number>>((acc, id) => {
                    const j = jurOf(id);
                    if (j) acc[j] = (acc[j] ?? 0) + 1;
                    return acc;
                  }, {})
                ).map(([j, n]) => (
                  <a
                    key={j}
                    href={OFFICIAL_SOURCES[j]?.url}
                    target="_blank"
                    rel="noreferrer"
                    className={`chip border underline-offset-2 hover:underline ${JUR_CHIP_CLS[j] ?? "border-line"}`}
                    aria-label={`打开${OFFICIAL_SOURCES[j]?.name ?? j}官方法源`}
                  >
                    {OFFICIAL_SOURCES[j]?.name ?? j}（{n} 条）↗
                  </a>
                ))}
              </div>
            )}
          </div>

          {/* 判例展示：分页 + 折叠 */}
          {cases.length > 0 && (
            <div className="mt-3 rounded-lg border border-line bg-surface-sunken/50 p-4">
              <h3 className="flex items-center gap-1.5 text-sm font-semibold text-fg">
                <Scale size={14} aria-hidden className="text-accent-soft" />
                关联判例（{cases.length}，每页 {CASE_PAGE_SIZE} 条）
              </h3>
              <ul className="mt-2 space-y-2">
                {pageCases.map((c, i) => {
                  const globalIdx = casePage * CASE_PAGE_SIZE + i;
                  const long = c.length > 120;
                  const open = !collapsed[globalIdx];
                  return (
                    <li key={globalIdx} className="rounded-lg border border-line bg-surface-raised/60 p-3">
                      <p className="text-xs leading-5 text-fg-muted">
                        {long && !open ? c.slice(0, 110) + "…" : c}
                      </p>
                      <div className="mt-1.5 flex items-center gap-2">
                        {long && (
                          <button
                            className="btn btn-ghost px-2 py-1 text-xs"
                            aria-expanded={open}
                            aria-label={open ? "折叠判例详情" : "展开判例全文"}
                            onClick={() => setCollapsed({ ...collapsed, [globalIdx]: open })}
                          >
                            {open ? <ChevronUp size={12} aria-hidden /> : <ChevronDown size={12} aria-hidden />}
                            {open ? "折叠" : "展开全文"}
                          </button>
                        )}
                        <a
                          href={OFFICIAL_SOURCES.SG.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-accent-soft underline-offset-2 hover:underline"
                          aria-label="打开新加坡官方法源核对判例"
                        >
                          SSO 官方法源 ↗
                        </a>
                      </div>
                    </li>
                  );
                })}
              </ul>
              {casePages > 1 && (
                <nav className="mt-2 flex items-center gap-2" aria-label="判例分页">
                  <button
                    className="btn btn-ghost px-2.5 py-1 text-xs"
                    disabled={casePage === 0}
                    aria-label="上一页判例"
                    onClick={() => setCasePage(casePage - 1)}
                  >
                    上一页
                  </button>
                  <span className="text-xs text-fg-subtle">
                    {casePage + 1} / {casePages}
                  </span>
                  <button
                    className="btn btn-ghost px-2.5 py-1 text-xs"
                    disabled={casePage >= casePages - 1}
                    aria-label="下一页判例"
                    onClick={() => setCasePage(casePage + 1)}
                  >
                    下一页
                  </button>
                </nav>
              )}
            </div>
          )}

          <p className="mt-2 text-xs text-fg-subtle">{result.disclaimer}</p>
          <LegalDisclaimer className="mt-2" />
        </div>
      )}
    </section>
  );
}
