"use client";

import { useState } from "react";
import {
  FileSearch,
  FileText,
  Gavel,
  GitBranch,
  Loader2,
  Scale,
  ThumbsDown,
  ThumbsUp,
  History,
  Wrench,
} from "lucide-react";
import ByokSettings from "@/components/ByokSettings";
import CaseView from "@/components/CaseView";
import CitationPanel from "@/components/CitationPanel";
import ContractView from "@/components/ContractView";
import FactPanel from "@/components/FactPanel";
import LegalDisclaimer from "@/components/LegalDisclaimer";
import OpinionView from "@/components/OpinionView";
import { SkeletonCard } from "@/components/Skeleton";
import ToolboxView from "@/components/ToolboxView";
import MockTrialView from "@/components/MockTrialView";
import { showToast } from "@/components/Toast";
import {
  AskResponse,
  ByokConfig,
  CaseSearchResponse,
  ConsultGraphResponse,
  ContractScanResponse,
  OpinionResponse,
  askByok,
  askServer,
  consultGraph,
  generateOpinion,
  scanContract,
  searchCases,
  sendFeedback,
} from "@/lib/api";

const JURISDICTIONS = [
  { code: "CN", label: "中国" },
  { code: "JP", label: "日本" },
  { code: "KR", label: "韩国" },
  { code: "SG", label: "新加坡" },
];

const MODES = [
  { id: "consult", label: "法律咨询", icon: Scale },
  { id: "contract", label: "合同风险扫描", icon: FileText },
  { id: "cases", label: "类案参考", icon: FileSearch },
  { id: "trial", label: "模拟法庭", icon: Gavel },
  { id: "tools", label: "工具箱", icon: Wrench },
] as const;

type Mode = (typeof MODES)[number]["id"];

export default function Home() {
  // ---- 通用 ----
  const [mode, setMode] = useState<Mode>("consult");
  const [jurisdiction, setJurisdiction] = useState("CN");
  const [adversarial, setAdversarial] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [byok, setByok] = useState<ByokConfig>({ baseUrl: "", apiKey: "", model: "" });

  // ---- 咨询模式 ----
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [opinion, setOpinion] = useState<OpinionResponse | null>(null);
  const [graph, setGraph] = useState<ConsultGraphResponse | null>(null);

  // ---- 合同模式 ----
  const [contractText, setContractText] = useState("");
  const [contractResult, setContractResult] = useState<ContractScanResponse | null>(null);

  // ---- 类案模式 ----
  const [caseQuery, setCaseQuery] = useState("");
  const [caseResult, setCaseResult] = useState<CaseSearchResponse | null>(null);

  const canUseByok = Boolean(byok.apiKey && byok.baseUrl && byok.model);

  function resetResults() {
    setError("");
    setResult(null);
    setOpinion(null);
    setGraph(null);
  }

  async function onAsk() {
    if (!question.trim() || loading) return;
    setLoading(true);
    resetResults();
    try {
      const resp = canUseByok
        ? await askByok(question, jurisdiction, byok, adversarial)
        : await askServer(question, jurisdiction, 5, adversarial);
      setResult(resp);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "请求失败，请检查后端是否已启动";
      setError(msg);
      showToast(msg, "error");
    } finally {
      setLoading(false);
    }
  }

  /** LangGraph 状态机深度咨询（/api/consult/graph）：全程 trace + 人工裁决中断恢复。 */
  async function onGraphConsult(resume?: "approve" | "reject") {
    if (loading) return;
    if (!resume && !question.trim()) return;
    setLoading(true);
    if (!resume) resetResults();
    try {
      const resp = await consultGraph({
        question,
        jurisdiction,
        adversarial,
        interrupt_on_degraded: true,
        thread_id: resume ? graph?.thread_id : null,
        resume_decision: resume ?? null,
      });
      setGraph(resp);
      if (resp.interrupted) {
        showToast("NLI 校验降级，已挂起等待人工裁决", "warn");
      } else if (resp.status === "refused") {
        showToast("请求被安全策略拒绝", "error");
      } else {
        showToast(`状态机执行完成：${resp.status}`, "ok");
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "状态机执行失败";
      setError(msg);
      showToast(msg, "error");
    } finally {
      setLoading(false);
    }
  }

  async function onOpinion() {
    if (!question.trim() || loading) return;
    setLoading(true);
    resetResults();
    try {
      setOpinion(await generateOpinion(question, jurisdiction, adversarial));
    } catch (e) {
      const msg = e instanceof Error ? e.message : "请求失败，请检查后端是否已启动";
      setError(msg);
      showToast(msg, "error");
    } finally {
      setLoading(false);
    }
  }

  async function onScanContract() {
    if (!contractText.trim() || loading) return;
    setLoading(true);
    setError("");
    setContractResult(null);
    try {
      setContractResult(await scanContract(contractText, jurisdiction));
    } catch (e) {
      const msg = e instanceof Error ? e.message : "请求失败，请检查后端是否已启动";
      setError(msg);
      showToast(msg, "error");
    } finally {
      setLoading(false);
    }
  }

  async function onSearchCases() {
    if (!caseQuery.trim() || loading) return;
    setLoading(true);
    setError("");
    setCaseResult(null);
    try {
      setCaseResult(await searchCases(caseQuery));
    } catch (e) {
      const msg = e instanceof Error ? e.message : "请求失败，请检查后端是否已启动";
      setError(msg);
      showToast(msg, "error");
    } finally {
      setLoading(false);
    }
  }

  async function onFeedback(verdict: "useful" | "wrong" | "outdated") {
    if (!result) return;
    await sendFeedback(question, result.answer, verdict).catch(() => {});
    showToast(
      verdict === "useful" ? "感谢反馈！" : "已记录，样本将进入 Golden Set 迭代。",
      "ok"
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.6fr_1fr]">
      {/* 左：模式化主工作区 */}
      <div className="flex flex-col gap-5">
        {/* 模式切换 */}
        <nav className="flex flex-wrap gap-2" aria-label="功能模式切换">
          {MODES.map((m) => {
            const Icon = m.icon;
            return (
              <button
                key={m.id}
                aria-pressed={mode === m.id}
                aria-label={`切换到${m.label}`}
                className={`btn ${mode === m.id ? "btn-primary" : "btn-ghost"}`}
                onClick={() => setMode(m.id)}
              >
                <Icon size={16} aria-hidden /> {m.label}
              </button>
            );
          })}
        </nav>

        {/* ===== 法律咨询模式 ===== */}
        {mode === "consult" && (
          <>
            <section className="card p-5">
              <h1 className="text-lg font-semibold text-fg">法律咨询（检索 → 引用回答 / 五段式意见书）</h1>
              <p className="mt-1 text-xs text-fg-subtle">
                铁律：每条结论必挂现行有效法条原文；检索不到就说「证据不足」，不编造。
              </p>
              <textarea
                className="textarea mt-4 h-32 resize-y"
                placeholder="例如：公司拖欠我三个月工资，我打算离职并索赔，法律上怎么处理？"
                aria-label="法律问题描述"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onAsk();
                }}
              />
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <select
                  className="select w-auto"
                  value={jurisdiction}
                  aria-label="选择法域"
                  onChange={(e) => setJurisdiction(e.target.value)}
                >
                  {JURISDICTIONS.map((j) => (
                    <option key={j.code} value={j.code}>
                      法域：{j.label}
                    </option>
                  ))}
                </select>
                <label className="flex cursor-pointer items-center gap-2 text-xs text-fg-muted">
                  <input
                    type="checkbox"
                    checked={adversarial}
                    onChange={(e) => setAdversarial(e.target.checked)}
                    className="accent-accent"
                    aria-label="开启双视角对抗模式"
                  />
                  双视角对抗（附对方律师视角找漏洞）
                </label>
                <button
                  className="btn btn-ghost ml-auto"
                  onClick={() => onGraphConsult()}
                  disabled={loading || !question.trim()}
                  title="LangGraph 状态机全流程（含 NLI 降级人工裁决）"
                  aria-label="状态机深度咨询"
                >
                  {loading ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <GitBranch size={16} aria-hidden />}
                  状态机深度咨询
                </button>
                <button
                  className="btn btn-ghost"
                  onClick={onOpinion}
                  disabled={loading || !question.trim()}
                  title="事实结构化 + 检索 + 五段式意见书"
                  aria-label="生成法律意见书"
                >
                  {loading ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <FileText size={16} aria-hidden />}
                  生成法律意见书
                </button>
                <button
                  className="btn btn-primary"
                  onClick={onAsk}
                  disabled={loading || !question.trim()}
                  aria-label="快速咨询"
                >
                  {loading ? <Loader2 size={16} className="animate-spin" aria-hidden /> : null}
                  {loading ? "分析中…" : "快速咨询"}
                </button>
              </div>
            </section>

            {loading && <SkeletonCard lines={4} />}

            {opinion && (
              <>
                <OpinionView opinion={opinion} />
                <FactPanel factSet={opinion.fact_set} />
              </>
            )}

            {/* 状态机结果：trace + 中断裁决 */}
            {graph && (
              <section className="card p-5" aria-label="状态机执行结果">
                <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
                  <span className="chip bg-accent/15 text-accent-soft">状态机 · {graph.status}</span>
                  <span className="chip border border-line text-fg-muted">置信度 {(graph.confidence * 100).toFixed(0)}%</span>
                  {graph.nli && (
                    <span className={`chip ${graph.nli.status === "degraded" ? "bg-danger/15 text-danger" : "bg-ok/15 text-ok"}`}>
                      NLI：{graph.nli.status}
                    </span>
                  )}
                </div>

                {/* 执行轨迹（状态机透明性） */}
                <ol className="mb-3 flex flex-wrap gap-1" aria-label="状态机执行轨迹">
                  {graph.trace.map((t, i) => (
                    <li key={i} className="chip border border-line font-mono text-[11px] text-fg-subtle">
                      {t}
                    </li>
                  ))}
                </ol>

                <article className="whitespace-pre-wrap text-sm leading-7 text-fg-muted">{graph.answer}</article>

                {graph.adversarial_notes && (
                  <div className="mt-3 rounded-lg border border-danger/30 bg-danger/5 p-3">
                    <p className="text-xs font-semibold text-danger">对方律师视角</p>
                    <p className="mt-1 whitespace-pre-wrap text-xs leading-5 text-fg-muted">{graph.adversarial_notes}</p>
                  </div>
                )}

                {/* 人工裁决（interrupt 恢复） */}
                {graph.interrupted && (
                  <div className="mt-4 rounded-lg border border-warn/50 bg-warn/10 p-3" role="alertdialog" aria-label="NLI 降级人工裁决">
                    <p className="text-sm font-medium text-warn">
                      NLI 校验降级，已挂起等待人工裁决（thread：{graph.thread_id}）
                    </p>
                    <div className="mt-2 flex gap-2">
                      <button className="btn btn-primary px-3 py-1.5 text-xs" aria-label="批准带降级警示出稿" onClick={() => onGraphConsult("approve")}>
                        批准出稿（带降级警示）
                      </button>
                      <button className="btn btn-danger px-3 py-1.5 text-xs" aria-label="驳回不出结论" onClick={() => onGraphConsult("reject")}>
                        驳回（不出结论）
                      </button>
                    </div>
                  </div>
                )}

                <LegalDisclaimer className="mt-4" />
              </section>
            )}

            {result && (
              <section className="card p-5">
                <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
                  <span className="chip bg-accent/15 text-accent-soft">
                    模式：{result.mode === "server" ? "服务端生成" : "演示模式（摘录法条）"}
                  </span>
                  <span
                    className={`chip ${
                      result.nli.status === "degraded"
                        ? "bg-danger/15 text-danger"
                        : result.nli.status === "pass"
                          ? "bg-ok/15 text-ok"
                          : "bg-warn/15 text-warn"
                    }`}
                  >
                    NLI：
                    {result.nli.status === "pass"
                      ? "结论-依据一致"
                      : result.nli.status === "degraded"
                        ? "支撑不足·已降级"
                        : "未加载模型·未验证"}
                  </span>
                  <span className="chip border border-line text-fg-muted">
                    置信度 {(result.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <article className="whitespace-pre-wrap text-sm leading-7 text-fg-muted">{result.answer}</article>
                <div className="mt-5 flex items-center gap-2 border-t border-line pt-4">
                  <span className="text-xs text-fg-subtle">这条回答对你有帮助吗？</span>
                  <button
                    className="btn btn-ghost px-3 py-1.5 text-xs hover:text-ok"
                    onClick={() => onFeedback("useful")}
                    aria-label="标记回答有用"
                  >
                    <ThumbsUp size={13} aria-hidden /> 有用
                  </button>
                  <button
                    className="btn btn-ghost px-3 py-1.5 text-xs hover:text-danger"
                    onClick={() => onFeedback("wrong")}
                    aria-label="标记回答有误"
                  >
                    <ThumbsDown size={13} aria-hidden /> 有误
                  </button>
                  <button
                    className="btn btn-ghost px-3 py-1.5 text-xs hover:text-warn"
                    onClick={() => onFeedback("outdated")}
                    aria-label="标记引用过时"
                  >
                    <History size={13} aria-hidden /> 引用过时
                  </button>
                </div>
                <LegalDisclaimer className="mt-4" />
              </section>
            )}
          </>
        )}

        {/* ===== 合同风险扫描模式 ===== */}
        {mode === "contract" && (
          <>
            <section className="card p-5">
              <h1 className="text-lg font-semibold text-fg">合同风险扫描（逐条红黄绿标注）</h1>
              <p className="mt-1 text-xs text-fg-subtle">
                粘贴合同全文（支持"第X条"自动切分）。PDF 请用后端 API 提交（pip install pypdf）。
              </p>
              <textarea
                className="textarea mt-4 h-48 resize-y"
                placeholder="把合同全文粘贴到这里……"
                aria-label="合同全文"
                value={contractText}
                onChange={(e) => setContractText(e.target.value)}
              />
              <div className="mt-3 flex items-center gap-3">
                <button
                  className="btn btn-primary ml-auto"
                  onClick={onScanContract}
                  disabled={loading || !contractText.trim()}
                  aria-label="开始扫描合同"
                >
                  {loading ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <FileSearch size={16} aria-hidden />}
                  {loading ? "扫描中…" : "开始扫描"}
                </button>
              </div>
            </section>
            {loading && <SkeletonCard lines={5} />}
            {contractResult && <ContractView result={contractResult} />}
          </>
        )}

        {/* ===== 类案参考模式 ===== */}
        {mode === "cases" && (
          <>
            <section className="card p-5">
              <h1 className="text-lg font-semibold text-fg">类案参考（要素匹配 + 裁判结果分布）</h1>
              <p className="mt-1 text-xs text-fg-subtle">
                用要素关键词描述争议（案由/焦点/金额），匹配脱敏类案并统计裁判结果分布。
              </p>
              <textarea
                className="textarea mt-4 h-24 resize-y"
                placeholder="例如：公司未签劳动合同，申请仲裁要求二倍工资"
                aria-label="类案检索关键词"
                value={caseQuery}
                onChange={(e) => setCaseQuery(e.target.value)}
              />
              <div className="mt-3 flex items-center">
                <button
                  className="btn btn-primary ml-auto"
                  onClick={onSearchCases}
                  disabled={loading || !caseQuery.trim()}
                  aria-label="检索类案"
                >
                  {loading ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <FileSearch size={16} aria-hidden />}
                  {loading ? "检索中…" : "检索类案"}
                </button>
              </div>
            </section>
            {loading && <SkeletonCard lines={4} />}
            {caseResult && <CaseView result={caseResult} />}
          </>
        )}

        {/* ===== 模拟法庭模式 ===== */}
        {mode === "trial" && <MockTrialView />}

        {/* ===== 工具箱模式 ===== */}
        {mode === "tools" && <ToolboxView />}

        {error && (
          <p className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
      </div>

      {/* 右：BYOK 设置 + 溯源面板 */}
      <div className="flex flex-col gap-5">
        <ByokSettings onChange={setByok} />
        {mode === "consult" && <CitationPanel citations={opinion?.citations ?? result?.citations ?? graph?.citations ?? []} />}
        {mode === "contract" && contractResult && (
          <CitationPanel citations={contractResult.citations} />
        )}
        {mode === "cases" && (
          <div className="card p-5 text-xs leading-5 text-fg-subtle">
            类案参考的数据源为脱敏示例裁判文书（开发种子）。正式版接入官方公开裁判文书渠道，
            入库前统一做隐私脱敏（身份证/手机/住址）。
          </div>
        )}
      </div>
    </div>
  );
}
