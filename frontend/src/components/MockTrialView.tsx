"use client";

/**
 * P3 模拟法庭庭审工作台（LangGraph 状态机版）。
 *
 * 六分区：案情录入 / 诉状面板（双视角）/ 举证管理（时效联动）/
 * 辩论对话 / 滚动庭审记录 / 裁判结果（强制免责 + 溯源）。
 * SSE 流式逐段渲染；骨架屏加载态；导出 Markdown / PDF。
 */

import { useEffect, useRef, useState } from "react";
import {
  BookMarked,
  Download,
  FileText,
  Gavel,
  Loader2,
  Plus,
  ScrollText,
  Send,
  ShieldAlert,
  Swords,
  Trash2,
  User,
} from "lucide-react";
import LegalDisclaimer from "@/components/LegalDisclaimer";
import { Skeleton, SkeletonCard } from "@/components/Skeleton";
import { showToast } from "@/components/Toast";
import {
  Citation,
  LimitationRisk,
  TrialClaimInput,
  TrialClaimSupport,
  TrialEvent,
  TrialEvidenceInput,
  TrialGraphResponse,
  TrialTurn,
  TrialVerdict,
  TRIAL_DISCLAIMER,
  streamTrialGraph,
  trialExportLinks,
  trialGraphSession,
} from "@/lib/api";

const PHASE_LABEL: Record<string, string> = {
  create_case: "案件创建",
  fix_facts: "事实固定",
  file_complaint: "提交诉状",
  evidence_review: "举证质证",
  human_confirm: "人工确认",
  debate: "法庭辩论",
  closing: "总结陈词",
  adjudicate: "模拟裁判",
};

const SUPPORT_META: Record<TrialClaimSupport, { label: string; cls: string }> = {
  supported: { label: "充分", cls: "bg-ok/15 text-ok" },
  partial: { label: "偏弱", cls: "bg-warn/15 text-warn" },
  insufficient: { label: "证据不足", cls: "bg-danger/15 text-danger" },
};

const STRENGTH_LABEL: Record<string, string> = { strong: "强", medium: "中", weak: "弱" };
const MATCH_LABEL: Record<string, string> = { strong: "充分匹配", partial: "部分匹配", weak: "匹配不足" };

const LIMIT_META: Record<string, { label: string; cls: string }> = {
  safe: { label: "时效安全", cls: "bg-ok/15 text-ok" },
  warning: { label: "时效临界", cls: "bg-warn/15 text-warn" },
  expired: { label: "时效届满", cls: "bg-danger/15 text-danger" },
  unknown: { label: "时效未明", cls: "border border-line text-fg-muted" },
};

const DECISION_CLS: Record<string, string> = {
  支持: "bg-ok/15 text-ok",
  部分支持: "bg-warn/15 text-warn",
  驳回: "bg-danger/15 text-danger",
};

const TURN_META: Record<TrialTurn["role"], { label: string; cls: string; icon: typeof User }> = {
  user: { label: "你（当事人）", cls: "border-accent/50 bg-accent/10", icon: User },
  opponent: { label: "对方律师", cls: "border-danger/40 bg-danger/10", icon: Swords },
  judge: { label: "法官", cls: "border-warn/40 bg-warn/10", icon: Gavel },
};

function CitationInline({ citations, max = 4 }: { citations: Citation[]; max?: number }) {
  if (!citations.length) return null;
  return (
    <p className="mt-1.5 flex flex-wrap gap-1.5">
      {citations.slice(0, max).map((c) => (
        <a
          key={c.statute_id}
          href={c.source_url || "#"}
          target="_blank"
          rel="noreferrer"
          className="chip border border-accent/30 bg-accent/10 text-accent-soft hover-elastic"
          title={`${c.law_title}${c.article_no}：${c.text.slice(0, 80)}…`}
        >
          <BookMarked size={11} aria-hidden /> {c.statute_id}
        </a>
      ))}
    </p>
  );
}

export default function MockTrialView() {
  // ---- 录入区 ----
  const [caseDesc, setCaseDesc] = useState("");
  const [userRole, setUserRole] = useState<"plaintiff" | "defendant">("plaintiff");
  const [claims, setClaims] = useState<TrialClaimInput[]>([
    { text: "", relief: "" },
    { text: "", relief: "" },
  ]);
  const [evidences, setEvidences] = useState<TrialEvidenceInput[]>([
    { title: "", evidence_type: "书证", description: "" },
  ]);
  const [interruptOnLimitation, setInterruptOnLimitation] = useState(false);
  const [sessionId, setSessionId] = useState("");

  // ---- 过程状态 ----
  const [resp, setResp] = useState<TrialGraphResponse | null>(null);
  const [streamEvents, setStreamEvents] = useState<TrialEvent[]>([]);
  const [streamTurns, setStreamTurns] = useState<TrialTurn[]>([]);
  const [streamTrace, setStreamTrace] = useState<string[]>([]);
  const [streamVerdict, setStreamVerdict] = useState<TrialVerdict | null>(null);
  const [statement, setStatement] = useState("");
  const [closingText, setClosingText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const eventsRef = useRef<HTMLDivElement>(null);

  // 滚动庭审记录：新事件自动滚到底
  const events = resp?.events?.length ? resp.events : streamEvents;
  useEffect(() => {
    const el = eventsRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  function resetStream() {
    setStreamEvents([]);
    setStreamTurns([]);
    setStreamTrace([]);
    setStreamVerdict(null);
  }

  async function runStream(body: Parameters<typeof streamTrialGraph>[0]) {
    setBusy(true);
    setError("");
    try {
      await streamTrialGraph(body, {
        onPhase: (node, trace) => {
          setStreamTrace((prev) => [...prev, ...(trace.length ? trace : [node])]);
        },
        onEvent: (ev) => setStreamEvents((prev) => [...prev, ev]),
        onTurn: (t) => setStreamTurns((prev) => [...prev, t]),
        onVerdict: (v) => setStreamVerdict(v),
        onDone: (snap) => {
          setResp(snap);
          resetStream();
          if (snap.status === "done") showToast("模拟裁判已作出（仅供推演）", "ok");
          else if (snap.status === "refused") showToast("输入含注入内容，已拒绝立案", "error");
          else if (snap.status === "insufficient_evidence") showToast("证据不足，审理终结", "warn");
          else if (snap.interrupted) showToast(`等待你的输入：${PHASE_LABEL[snap.phase] ?? snap.phase}`, "info");
        },
        onError: (msg) => {
          setError(msg);
          showToast(msg, "error");
        },
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "执行失败，请检查后端";
      setError(msg);
      showToast(msg, "error");
    } finally {
      setBusy(false);
    }
  }

  async function onStart() {
    if (!caseDesc.trim() || busy) return;
    resetStream();
    setResp(null);
    const sid = sessionId.trim() || `trial-${Date.now().toString(36)}`;
    setSessionId(sid);
    await runStream({
      session_id: sid,
      case_description: caseDesc,
      user_role: userRole,
      jurisdiction: "CN",
      language: "zh",
      top_k: 5,
      claims: claims.filter((c) => c.text.trim()),
      evidences: evidences.filter((e) => e.title.trim()),
      interrupt_on_limitation: interruptOnLimitation,
    });
  }

  async function onStep(payload: { statement?: string; closing?: string; decision?: string }) {
    if (!resp?.session_id || busy) return;
    await runStream({ session_id: resp.session_id, ...payload });
  }

  async function onRestore() {
    const sid = sessionId.trim();
    if (!sid) return;
    setBusy(true);
    setError("");
    try {
      const snap = await trialGraphSession(sid);
      setResp(snap);
      resetStream();
      showToast(`会话已恢复（${PHASE_LABEL[snap.phase] ?? snap.phase}）`, "ok");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "会话恢复失败";
      setError(msg);
      showToast(msg, "error");
    } finally {
      setBusy(false);
    }
  }

  function onExport(kind: "md" | "pdf") {
    const sid = resp?.session_id;
    if (!sid) return;
    const links = trialExportLinks(sid);
    const a = document.createElement("a");
    a.href = kind === "md" ? links.md : links.pdf;
    a.download = `trial-${sid}.${kind}`;
    a.click();
    showToast(kind === "md" ? "庭审记录（Markdown）开始下载" : "庭审记录（PDF）开始下载", "ok");
  }

  const complaint = resp?.complaint ?? null;
  const reviews = resp?.evidence_reviews ?? [];
  const limitation = resp?.limitation ?? null;
  const verdict = streamVerdict ?? resp?.verdict ?? null;
  const turns = resp?.debate_turns?.length ? resp.debate_turns : streamTurns;
  const trace = resp?.trace?.length ? resp.trace : streamTrace;
  const awaiting = resp?.interrupted ?? false;

  return (
    <div className="flex flex-col gap-5">
      {/* ============ 分区 1：案情录入 ============ */}
      <section className="card p-5" aria-label="案情录入区">
        <h1 className="text-lg font-semibold text-fg">模拟法庭 · 庭审推演工作台</h1>
        <p className="mt-1 text-xs text-fg-subtle">
          LangGraph 庭审状态机：案件创建 → 事实固定 → 提交诉状 → 举证质证 → 法庭辩论 → 总结陈词 → 模拟裁判。
          主张无检索依据即「证据不足」，结论必挂法条溯源。
        </p>

        {!resp && (
          <>
            <textarea
              className="textarea mt-4 h-28 resize-y"
              placeholder="陈述案情（时间、地点、金额、经过、诉求）……"
              aria-label="案情陈述"
              value={caseDesc}
              onChange={(e) => setCaseDesc(e.target.value)}
            />

            {/* 诉状主张录入 */}
            <div className="mt-4">
              <p className="text-xs font-medium text-fg-muted">诉状主张（逐项检索挂条）</p>
              <div className="mt-2 space-y-2">
                {claims.map((c, i) => (
                  <div key={i} className="flex gap-2">
                    <input
                      className="input flex-1"
                      placeholder={`主张 ${i + 1}：如「对方未履行合同义务，应当支付货款」`}
                      aria-label={`主张 ${i + 1} 内容`}
                      value={c.text}
                      onChange={(e) =>
                        setClaims((prev) => prev.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))
                      }
                    />
                    <input
                      className="input w-40"
                      placeholder="诉求（可选）"
                      aria-label={`主张 ${i + 1} 诉求`}
                      value={c.relief ?? ""}
                      onChange={(e) =>
                        setClaims((prev) => prev.map((x, j) => (j === i ? { ...x, relief: e.target.value } : x)))
                      }
                    />
                    <button
                      className="btn btn-ghost px-2"
                      aria-label={`删除主张 ${i + 1}`}
                      onClick={() => setClaims((prev) => prev.filter((_, j) => j !== i))}
                      disabled={claims.length <= 1}
                    >
                      <Trash2 size={14} aria-hidden />
                    </button>
                  </div>
                ))}
              </div>
              <button
                className="btn btn-ghost mt-2 px-3 py-1.5 text-xs"
                onClick={() => setClaims((prev) => [...prev, { text: "", relief: "" }])}
                aria-label="添加主张"
              >
                <Plus size={13} aria-hidden /> 添加主张
              </button>
            </div>

            {/* 证据录入 */}
            <div className="mt-4">
              <p className="text-xs font-medium text-fg-muted">在案证据（举证质证）</p>
              <div className="mt-2 space-y-2">
                {evidences.map((ev, i) => (
                  <div key={i} className="flex flex-wrap gap-2">
                    <input
                      className="input w-44"
                      placeholder={`证据 ${i + 1} 名称`}
                      aria-label={`证据 ${i + 1} 名称`}
                      value={ev.title}
                      onChange={(e) =>
                        setEvidences((prev) => prev.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)))
                      }
                    />
                    <select
                      className="select w-auto"
                      aria-label={`证据 ${i + 1} 类型`}
                      value={ev.evidence_type}
                      onChange={(e) =>
                        setEvidences((prev) =>
                          prev.map((x, j) => (j === i ? { ...x, evidence_type: e.target.value } : x))
                        )
                      }
                    >
                      {["书证", "物证", "电子数据", "证人证言", "鉴定意见", "当事人陈述", "其他"].map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                    <input
                      className="input flex-1"
                      placeholder="证据说明（来源、内容、时间）"
                      aria-label={`证据 ${i + 1} 说明`}
                      value={ev.description}
                      onChange={(e) =>
                        setEvidences((prev) =>
                          prev.map((x, j) => (j === i ? { ...x, description: e.target.value } : x))
                        )
                      }
                    />
                    <button
                      className="btn btn-ghost px-2"
                      aria-label={`删除证据 ${i + 1}`}
                      onClick={() => setEvidences((prev) => prev.filter((_, j) => j !== i))}
                      disabled={evidences.length <= 1}
                    >
                      <Trash2 size={14} aria-hidden />
                    </button>
                  </div>
                ))}
              </div>
              <button
                className="btn btn-ghost mt-2 px-3 py-1.5 text-xs"
                onClick={() =>
                  setEvidences((prev) => [...prev, { title: "", evidence_type: "书证", description: "" }])
                }
                aria-label="添加证据"
              >
                <Plus size={13} aria-hidden /> 添加证据
              </button>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <select
                className="select w-auto"
                value={userRole}
                aria-label="选择你的诉讼角色"
                onChange={(e) => setUserRole(e.target.value as "plaintiff" | "defendant")}
              >
                <option value="plaintiff">我当原告（主张方）</option>
                <option value="defendant">我当被告（抗辩方）</option>
              </select>
              <label className="flex cursor-pointer items-center gap-2 text-xs text-fg-muted">
                <input
                  type="checkbox"
                  checked={interruptOnLimitation}
                  onChange={(e) => setInterruptOnLimitation(e.target.checked)}
                  className="accent-accent"
                  aria-label="时效风险高时挂起人工确认"
                />
                时效风险高时挂起人工确认
              </label>
              <input
                className="input w-44"
                placeholder="会话 ID（可选）"
                aria-label="会话 ID"
                value={sessionId}
                onChange={(e) => setSessionId(e.target.value)}
              />
              <button className="btn btn-ghost" onClick={onRestore} disabled={busy || !sessionId.trim()} aria-label="恢复已有会话">
                恢复会话
              </button>
              <button
                className="btn btn-primary ml-auto"
                onClick={onStart}
                disabled={busy || !caseDesc.trim()}
                aria-label="开庭"
              >
                {busy ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Gavel size={16} aria-hidden />}
                {busy ? "庭审进行中…" : "开庭（SSE 流式）"}
              </button>
            </div>
          </>
        )}

        {resp && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <span className="chip bg-accent/15 text-accent-soft">
              阶段：{PHASE_LABEL[resp.phase] ?? resp.phase}
            </span>
            <span className={`chip ${awaiting ? "bg-warn/15 text-warn" : "bg-ok/15 text-ok"}`}>
              {awaiting ? "等待输入" : resp.status === "done" ? "审理终结" : resp.status}
            </span>
            <span className="chip border border-line text-fg-muted">会话 {resp.session_id}</span>
            <button
              className="btn btn-ghost ml-auto px-3 py-1.5 text-xs"
              onClick={() => {
                setResp(null);
                resetStream();
                setStatement("");
                setClosingText("");
              }}
              aria-label="重新开庭"
            >
              重新开庭
            </button>
          </div>
        )}
      </section>

      {/* 状态机 trace */}
      {trace.length > 0 && (
        <ol className="flex flex-wrap gap-1" aria-label="状态机执行轨迹">
          {trace.map((t, i) => (
            <li key={i} className="chip border border-line font-mono text-[11px] text-fg-subtle">
              {t}
            </li>
          ))}
        </ol>
      )}

      {busy && !resp && <SkeletonCard lines={5} />}

      {/* ============ 分区 2：诉状面板（双视角对抗） ============ */}
      {complaint && (
        <section className="card p-5" aria-label="诉状面板">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-fg">诉状与主张（含对方律师视角）</h2>
            <span className={`chip ${complaint.grounded ? "bg-ok/15 text-ok" : "bg-danger/15 text-danger"}`}>
              {complaint.grounded ? "有法条依据" : "全部证据不足"}
            </span>
            <span className="chip border border-line text-fg-muted">当事人：{complaint.party}</span>
          </div>

          <div className="mt-3 space-y-3">
            {complaint.claims.map((cl, i) => (
              <div key={i} className="neu-inset p-3.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`chip ${SUPPORT_META[cl.support].cls}`}>{SUPPORT_META[cl.support].label}</span>
                  <p className="flex-1 text-sm font-medium text-fg">
                    主张 {i + 1}：{cl.text}
                  </p>
                  {cl.relief && <span className="text-xs text-fg-subtle">诉求：{cl.relief}</span>}
                </div>
                <CitationInline citations={cl.citations} />
                {cl.holes.length > 0 && (
                  <div className="mt-2">
                    <p className="text-xs font-medium text-danger">对方律师 · 事实漏洞</p>
                    <ul className="mt-1 space-y-0.5">
                      {cl.holes.map((h, j) => (
                        <li key={j} className="text-xs leading-5 text-fg-muted">
                          · {h}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {cl.risks.length > 0 && (
                  <div className="mt-2">
                    <p className="text-xs font-medium text-warn">法律风险</p>
                    <ul className="mt-1 space-y-0.5">
                      {cl.risks.map((r, j) => (
                        <li key={j} className="text-xs leading-5 text-fg-muted">
                          · {r}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="mt-4 rounded-xl border border-danger/30 bg-danger/5 p-3.5">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-danger">
              <Swords size={13} aria-hidden /> 对方律师视角（双视角对抗）
            </p>
            <p className="mt-1.5 whitespace-pre-wrap text-xs leading-6 text-fg-muted">
              {complaint.opposition_summary}
            </p>
          </div>
          <LegalDisclaimer className="mt-4" />
        </section>
      )}

      {/* ============ 分区 3：举证管理 + 时效联动 ============ */}
      {(reviews.length > 0 || limitation) && (
        <section className="card p-5" aria-label="举证管理">
          <h2 className="text-sm font-semibold text-fg">举证质证与证据校验</h2>
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            {reviews.map((r, i) => (
              <div key={i} className="neu-inset p-3.5">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="flex-1 text-sm font-medium text-fg">{r.title}</p>
                  <span className="chip border border-line text-fg-muted">{r.evidence_type}</span>
                  <span
                    className={`chip ${
                      r.probative_strength === "strong"
                        ? "bg-ok/15 text-ok"
                        : r.probative_strength === "medium"
                          ? "bg-warn/15 text-warn"
                          : "bg-danger/15 text-danger"
                    }`}
                  >
                    证明力 {STRENGTH_LABEL[r.probative_strength] ?? r.probative_strength}
                  </span>
                  <span className="chip border border-line text-fg-subtle">
                    {MATCH_LABEL[r.element_match] ?? r.element_match}
                  </span>
                </div>
                <p className="mt-1.5 text-xs leading-5 text-fg-muted">{r.note}</p>
                {r.target_elements.length > 0 && (
                  <p className="mt-1 text-xs text-fg-subtle">指向要件：{r.target_elements.join("、")}</p>
                )}
                {r.defects.length > 0 && (
                  <ul className="mt-1.5 space-y-0.5">
                    {r.defects.map((d, j) => (
                      <li key={j} className="text-xs leading-5 text-danger">
                        ⚠ {d}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>

          {limitation && <LimitationCard limitation={limitation} />}
        </section>
      )}

      {/* ============ 分区 4：辩论对话窗口 ============ */}
      {(turns.length > 0 || awaiting) && (
        <section className="card p-5" aria-label="法庭辩论">
          <h2 className="text-sm font-semibold text-fg">
            {resp?.phase === "closing" ? "总结陈词" : resp?.phase === "human_confirm" ? "人工确认" : "法庭辩论"}
          </h2>

          <div className="mt-3 space-y-3">
            {turns.map((t, i) => {
              const meta = TURN_META[t.role] ?? TURN_META.user;
              const Icon = meta.icon;
              return (
                <div key={i} className={`rounded-xl border p-3.5 hover-elastic ${meta.cls}`}>
                  <p className="flex items-center gap-1.5 text-xs font-medium text-fg-muted">
                    <Icon size={13} aria-hidden /> {meta.label}
                    {t.round > 0 && <span className="text-fg-subtle">· 第 {t.round} 轮</span>}
                  </p>
                  <p className="mt-1.5 whitespace-pre-wrap text-sm leading-6 text-fg-muted">{t.content}</p>
                </div>
              );
            })}
            {busy && (
              <div className="neu-inset p-3.5">
                <Skeleton className="h-3.5 w-1/3" />
                <Skeleton className="mt-2.5 h-3.5" style={{ width: "82%" }} />
                <Skeleton className="mt-2 h-3.5" style={{ width: "64%" }} />
              </div>
            )}
          </div>

          {awaiting && resp?.phase === "human_confirm" && (
            <div className="mt-4 rounded-lg border border-warn/50 bg-warn/10 p-3" role="alertdialog" aria-label="时效风险人工确认">
              <p className="flex items-center gap-1.5 text-sm font-medium text-warn">
                <ShieldAlert size={15} aria-hidden /> {resp.pending || "时效风险过高，是否继续审理？"}
              </p>
              <div className="mt-2 flex gap-2">
                <button
                  className="btn btn-primary px-3 py-1.5 text-xs"
                  disabled={busy}
                  onClick={() => onStep({ decision: "approve" })}
                  aria-label="确认继续审理"
                >
                  继续审理
                </button>
                <button
                  className="btn btn-danger px-3 py-1.5 text-xs"
                  disabled={busy}
                  onClick={() => onStep({ decision: "reject" })}
                  aria-label="终止推演"
                >
                  终止推演
                </button>
              </div>
            </div>
          )}

          {awaiting && resp?.phase === "debate" && (
            <div className="mt-4 flex gap-2">
              <input
                className="input flex-1"
                placeholder={resp.pending || "发表你的辩论意见……"}
                aria-label="辩论发言"
                value={statement}
                onChange={(e) => setStatement(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && statement.trim()) {
                    onStep({ statement });
                    setStatement("");
                  }
                }}
              />
              <button
                className="btn btn-primary"
                disabled={busy || !statement.trim()}
                onClick={() => {
                  onStep({ statement });
                  setStatement("");
                }}
                aria-label="提交发言"
              >
                {busy ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Send size={16} aria-hidden />}
                发言
              </button>
            </div>
          )}

          {awaiting && resp?.phase === "closing" && (
            <div className="mt-4">
              <textarea
                className="textarea h-24 resize-y"
                placeholder={resp.pending || "发表你的总结陈词……"}
                aria-label="总结陈词"
                value={closingText}
                onChange={(e) => setClosingText(e.target.value)}
              />
              <button
                className="btn btn-primary mt-2"
                disabled={busy || !closingText.trim()}
                onClick={() => {
                  onStep({ closing: closingText });
                  setClosingText("");
                }}
                aria-label="提交总结陈词"
              >
                {busy ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <ScrollText size={16} aria-hidden />}
                提交陈词，进入模拟裁判
              </button>
            </div>
          )}
        </section>
      )}

      {/* ============ 分区 5：滚动庭审记录 ============ */}
      {events.length > 0 && (
        <section className="card p-5" aria-label="庭审记录">
          <h2 className="text-sm font-semibold text-fg">庭审记录（全链路可追溯）</h2>
          <div
            ref={eventsRef}
            className="neu-inset mt-3 max-h-80 overflow-y-auto p-3"
            aria-live="polite"
          >
            <ol className="space-y-2.5">
              {events.map((ev, i) => (
                <li key={i} className="rounded-lg border border-line bg-surface-raised/40 p-2.5">
                  <p className="flex flex-wrap items-center gap-1.5 text-xs">
                    <span className="chip border border-line text-fg-subtle">
                      {PHASE_LABEL[ev.phase] ?? ev.phase}
                    </span>
                    <span className="font-medium text-fg">{ev.title}</span>
                    <span className="text-fg-subtle">· {ev.role}</span>
                  </p>
                  <p className="mt-1 whitespace-pre-wrap text-xs leading-5 text-fg-muted">{ev.content}</p>
                  {ev.citation_ids?.length > 0 && (
                    <p className="mt-1 flex flex-wrap gap-1">
                      {ev.citation_ids.map((sid) => (
                        <span key={sid} className="chip bg-accent/10 text-accent-soft">
                          {sid}
                        </span>
                      ))}
                    </p>
                  )}
                </li>
              ))}
            </ol>
            {busy && (
              <div className="mt-2">
                <Skeleton className="h-3 w-1/4" />
              </div>
            )}
          </div>
        </section>
      )}

      {/* ============ 分区 6：裁判结果卡片 ============ */}
      {verdict && <VerdictCard verdict={verdict} onExport={onExport} />}

      {/* 证据不足 / 拒答终态 */}
      {resp && (resp.status === "insufficient_evidence" || resp.status === "refused") && !verdict && (
        <section className="card p-5" aria-label="审理终结">
          <p className="flex items-center gap-2 text-sm font-medium text-danger">
            <ShieldAlert size={16} aria-hidden />
            {resp.status === "refused"
              ? "立案被拒：输入包含不安全内容（注入检测拦截）。"
              : "审理终结【证据不足】：现有法条库未检索到可支撑依据，拒绝在无依据的情况下生成结论。"}
          </p>
          <LegalDisclaimer className="mt-4" />
        </section>
      )}

      {error && (
        <p className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

function LimitationCard({ limitation }: { limitation: LimitationRisk }) {
  const meta = LIMIT_META[limitation.risk_level] ?? LIMIT_META.unknown;
  return (
    <div className="mt-4 rounded-xl border border-warn/40 bg-warn/10 p-3.5" aria-label="时效联动">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-semibold text-warn">时效联动（诉讼时效计算器）</p>
        <span className={`chip ${meta.cls}`}>{meta.label}</span>
        {limitation.key_date && <span className="chip border border-line text-fg-subtle">起算 {limitation.key_date}</span>}
        {limitation.deadline && <span className="chip border border-line text-fg-subtle">届满 {limitation.deadline}</span>}
      </div>
      <p className="mt-1.5 text-xs leading-5 text-fg-muted">{limitation.summary}</p>
      {limitation.calc_items?.length > 0 && (
        <ul className="mt-1.5 space-y-0.5">
          {limitation.calc_items.map((it, i) => (
            <li key={i} className="text-xs leading-5 text-fg-subtle">
              · {it.label}
              {it.amount != null ? `：${it.amount}` : ""}
              {it.note ? `（${it.note}）` : ""}
            </li>
          ))}
        </ul>
      )}
      <CitationInline citations={limitation.citations} />
    </div>
  );
}

function VerdictCard({ verdict, onExport }: { verdict: TrialVerdict; onExport: (k: "md" | "pdf") => void }) {
  return (
    <section className="card-strong card p-5" aria-label="模拟裁判结果">
      {/* 强制前置免责 */}
      <p className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm font-semibold text-danger">
        {verdict.disclaimer || TRIAL_DISCLAIMER}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold text-fg">模拟裁判（逐条理由 + 法条溯源）</h2>
        <button className="btn btn-ghost ml-auto px-3 py-1.5 text-xs hover-elastic" onClick={() => onExport("md")} aria-label="导出 Markdown">
          <Download size={13} aria-hidden /> 导出 Markdown
        </button>
        <button className="btn btn-ghost px-3 py-1.5 text-xs hover-elastic" onClick={() => onExport("pdf")} aria-label="导出 PDF">
          <FileText size={13} aria-hidden /> 导出 PDF
        </button>
      </div>

      <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-fg-muted">{verdict.overall}</p>

      <div className="mt-4 space-y-3">
        {verdict.items.map((it, i) => (
          <div key={i} className="neu-inset p-3.5 hover-elastic">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`chip ${DECISION_CLS[it.decision] ?? "border border-line text-fg-muted"}`}>
                {it.decision}
              </span>
              <p className="flex-1 text-sm font-medium text-fg">
                主张 {i + 1}：{it.claim}
              </p>
            </div>
            <ul className="mt-2 space-y-1">
              {it.reasons.map((r, j) => (
                <li key={j} className="text-xs leading-6 text-fg-muted">
                  · {r}
                </li>
              ))}
            </ul>
            <p className="mt-1.5 flex flex-wrap gap-1.5">
              {it.citation_ids.map((sid) => (
                <span key={sid} className="chip bg-accent/10 text-accent-soft">
                  {sid}
                </span>
              ))}
            </p>
            {it.case_refs.length > 0 && (
              <p className="mt-1 text-xs text-fg-subtle">类案参考：{it.case_refs.join("；")}</p>
            )}
            {it.cross_refs.length > 0 && (
              <p className="mt-1 text-xs text-fg-subtle">跨法域对照：{it.cross_refs.join("；")}</p>
            )}
          </div>
        ))}
      </div>

      {verdict.risk_notes.length > 0 && (
        <div className="mt-4 rounded-lg border border-warn/40 bg-warn/10 p-3">
          <p className="text-xs font-semibold text-warn">风险提示</p>
          <ul className="mt-1 space-y-0.5">
            {verdict.risk_notes.map((n, i) => (
              <li key={i} className="text-xs leading-5 text-fg-muted">
                · {n}
              </li>
            ))}
          </ul>
        </div>
      )}

      {verdict.case_refs.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium text-fg-muted">判例参考（知识图谱）</p>
          <ul className="mt-1 space-y-0.5">
            {verdict.case_refs.map((c, i) => (
              <li key={i} className="text-xs leading-5 text-fg-subtle">
                · {c}
              </li>
            ))}
          </ul>
        </div>
      )}

      {verdict.cross_jurisdiction.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium text-fg-muted">跨法域对照</p>
          <ul className="mt-1 space-y-0.5">
            {verdict.cross_jurisdiction.map((r, i) => (
              <li key={i} className="text-xs leading-5 text-fg-subtle">
                · [{r.jurisdiction_name}] {r.rule_summary}
                {r.statute_ref ? `（${r.statute_ref}）` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      <CitationInline citations={verdict.citations} max={8} />
      <LegalDisclaimer className="mt-4" />
    </section>
  );
}
