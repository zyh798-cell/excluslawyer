/**
 * 大白话解释生成器（普通人友好层 P0 第二项）。
 *
 * 设计红线（与任务要求一一对应）：
 * 1. 只做「结构化翻译」：所有内容均来自后端返回的 answer/overall、citations、NLI、风险字段，
 *    用确定性模板组织——不做任何 LLM 调用、不新增任何未检索到的法律依据；
 * 2. 风险与限制「原样保留」：证据不足、时效过期、NLI 降级、高风险等原文行直接进 warnings，
 *    不转写、不省略、不弱化；
 * 3. 法律判断的实质内容不转写：白话层说明「依据构成 / 可信度 / 需要注意什么」，
 *    并把法条原文收进可展开区——结论以原文为准，白话与原文并列、互不覆盖。
 */

import type { Citation, NliResult } from "@/lib/api";
import { extractTerms, type LawTerm } from "@/lib/terms";

export type PlainContextKind = "ask" | "opinion" | "graph" | "verdict";

export interface PlainExplanationInput {
  kind: PlainContextKind;
  /** 专业主文（answer / opinion 主文 / verdict.overall） */
  text: string;
  citations: Citation[];
  nli: NliResult | null;
  confidence?: number | null;
  /** 意见书风险等级（后端字段直译进 warnings，不淡化） */
  riskLevel?: "high" | "medium" | "low" | null;
  /** 后端风险提示行，原样保留 */
  riskNotes?: string[];
  /** 模拟裁判逐条结论 */
  decisions?: string[];
  /** 时效已过期 */
  limitationExpired?: boolean;
}

export interface PlainExplanation {
  /** 一句话：对你这件事意味着什么 */
  headline: string;
  /** 2–4 句解释理由 */
  reasons: string[];
  /** 风险/限制原样行（不转写、不省略） */
  warnings: string[];
  /** 命中的法律术语（渲染为可点击释义） */
  terms: LawTerm[];
}

const RISK_LABELS: Record<string, string> = { high: "高", medium: "中", low: "低" };

/** 把专业主文按句切分（。！？\n），返回包含任一标记词的完整句子。 */
export function extractMarkedSentences(text: string, markers: string[]): string[] {
  if (!text) return [];
  const sentences = text
    .split(/(?<=[。！？!?])|\n+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const s of sentences) {
    if (markers.some((m) => s.includes(m)) && !seen.has(s)) {
      seen.add(s);
      out.push(s);
    }
  }
  return out;
}

const WARN_MARKERS = [
  "证据不足",
  "引用支撑校验降级",
  "已过诉讼时效",
  "时效届满",
  "时效过期",
  "超过诉讼时效",
  "诉讼时效已",
];

function hasEvidenceGap(text: string): boolean {
  return text.includes("证据不足");
}

function hasLimitationExpired(text: string): boolean {
  return (
    /时效[^。]{0,12}(届满|过期|已过|超过)/.test(text) ||
    text.includes("超过诉讼时效") ||
    text.includes("已过诉讼时效")
  );
}

function hasDegraded(text: string, nli: NliResult | null): boolean {
  return Boolean(nli && nli.status === "degraded") || text.includes("降级");
}

/** 主依据句：只列 law_title + article_no（来自 citations，绝不新增）。 */
function basisSentence(citations: Citation[]): string {
  const n = citations.length;
  if (n === 0) {
    return "这次没有检索到能支撑主张的法条，按铁律标注「证据不足」——不会编造依据，建议补充信息后再问。";
  }
  const valid = citations.filter((c) => c.effective_status === "effective");
  const others = n - valid.length;
  const shown = valid
    .slice(0, 3)
    .map((c) => `《${c.law_title}》${c.article_no}`)
    .join("、");
  const head =
    n <= 3
      ? `这次分析引用了 ${n} 条法条：${shown}`
      : `这次分析引用了 ${n} 条法条，主要是：${shown} 等`;
  const tail = others > 0 ? `；另有 ${others} 条为已修订或其他状态，原文区有标注` : "，均为现行有效";
  return `${head}${tail}。每条原文都完整放在下方，可逐条核对。`;
}

/** 程序提示句：只提示「原文中提到了什么」，不做行动指引（程序指引为 WIP）。 */
function procedureSentence(text: string): string | null {
  if (text.includes("仲裁前置") || (text.includes("劳动") && text.includes("仲裁"))) {
    return "原文提到这类纠纷通常要先经过劳动仲裁（仲裁前置），具体程序要求以原文与官方渠道为准。";
  }
  if (text.includes("仲裁")) {
    return "原文中提到了仲裁程序，是否适用、如何启动以原文说明为准。";
  }
  if (text.includes("起诉") || text.includes("诉讼")) {
    return "原文中提到了诉讼程序，具体流程与材料要求以官方渠道为准。";
  }
  if (text.includes("投诉") || text.includes("12315")) {
    return "原文中提到了投诉渠道，具体方式以官方平台为准。";
  }
  return null;
}

/** 可信度句：后端 confidence + NLI 状态的直译。 */
function confidenceSentence(
  confidence: number | null | undefined,
  nli: NliResult | null,
  citations: Citation[]
): string | null {
  const nliPart = nli
    ? nli.status === "pass"
      ? "结论与法条原文的一致性校验通过"
      : nli.status === "degraded"
        ? "结论与法条原文的一致性校验未完全通过（已标注警示）"
        : "一致性校验未加载模型、未验证"
    : null;
  if (confidence == null && !nliPart) return null;
  const confPart =
    confidence != null ? `这次分析的可信度约为 ${Math.round(confidence * 100)}%` : null;
  const parts = [confPart, nliPart].filter(Boolean).join("，");
  return `${parts}。数字只代表模型自评，最终请以核对法条原文为准。`;
}

/** 时效提醒句（未过期但有涉及时效时提示别拖）。 */
function limitationReminderSentence(text: string): string | null {
  if (hasLimitationExpired(text)) return null;
  if (!text.includes("时效")) return null;
  return "原文涉及诉讼时效（权利受法律保护的期限）——这类期限通常不能中断拖延，越早确认越主动。";
}

export function buildPlainExplanation(input: PlainExplanationInput): PlainExplanation {
  const { text, citations, nli } = input;
  const evidenceGap = hasEvidenceGap(text);
  const expired = input.limitationExpired === true || hasLimitationExpired(text);
  const degraded = hasDegraded(text, nli);

  // ---- headline：一句话说清"对你意味着什么" ----
  let headline: string;
  if (evidenceGap) {
    headline =
      "目前手里的材料还不够，法律上暂时给不出对你有利的结论——先按下方提示补齐证据，再谈下一步。";
  } else if (expired) {
    headline =
      "你的主张很可能已经超过法律保护的期限（诉讼时效），要先弄清楚时间还来不来得及。";
  } else if (input.decisions && input.decisions.length > 0) {
    const supported = input.decisions.filter((d) => d === "支持").length;
    const rejected = input.decisions.filter((d) => d === "驳回").length;
    if (rejected === 0) {
      headline =
        "从这次模拟裁判看，你的各项主张都有依据支撑，大概率能得到支持——记得逐条核对下方原文。";
    } else if (supported === 0) {
      headline =
        "从这次模拟裁判看，你的主张大概率不会得到支持——重点看下方每条被驳的理由和缺口在哪。";
    } else {
      headline =
        "你的主张有一部分能成立、有一部分立不住——下面逐条说清是哪部分、为什么。";
    }
  } else if (degraded) {
    headline =
      "下面的结论还没通过与法条原文的一致性核对，只能作参考——请务必谨慎，别直接当作定论。";
  } else if (input.confidence != null && input.confidence < 0.4) {
    headline = "简单说：目前能给出的判断把握有限，请把下方依据逐条核对后再行动。";
  } else {
    headline = "简单说：你的事情在法律上有对应依据，可以往下看具体内容和需要注意的地方。";
  }

  // ---- reasons：2–4 句，全部锚定后端返回 ----
  const reasons: string[] = [basisSentence(citations)];
  const proc = procedureSentence(text);
  if (proc) reasons.push(proc);
  const conf = confidenceSentence(input.confidence, nli, citations);
  if (conf) reasons.push(conf);
  const limit = limitationReminderSentence(text);
  if (limit) reasons.push(limit);
  // 控制在 2–4 句（含首句）
  while (reasons.length < 2) {
    reasons.push("更多细节请展开下方「法条原文与专业分析」，以原文表述为准。");
    break;
  }

  // ---- warnings：原样保留，绝不转写、不省略 ----
  const warnings: string[] = [];
  // 1) 后端风险行原样
  for (const note of input.riskNotes ?? []) {
    if (note.trim()) warnings.push(note.trim());
  }
  // 2) 主文中的标记句原样
  warnings.push(...extractMarkedSentences(text, WARN_MARKERS));
  // 3) NLI 降级（用后端 reason 原文）
  if (nli && nli.status === "degraded") {
    warnings.push(
      `NLI 校验降级：结论与法条原文的支撑校验未通过（一致性 ${Math.round(nli.score * 100)}%）。${nli.reason || ""}`.trim()
    );
  }
  // 4) 风险等级直译（high/medium 必须显性呈现；low 不额外造警示噪声）
  if (input.riskLevel === "high" || input.riskLevel === "medium") {
    warnings.push(`风险等级：${RISK_LABELS[input.riskLevel]}（来自意见书的风险评定）`);
  }
  // 5) 时效过期（若主文标记句没覆盖到，用统一文案兜底）
  if (expired && !warnings.some((w) => w.includes("时效"))) {
    warnings.push("时效提示：相关请求可能已超过法律保护的期限，务必尽快核实关键时间点。");
  }
  // 6) 白话层自证声明（防止用户把白话当结论）
  warnings.push("以上白话只是对下方专业内容的说明，不改变任何结论——一切以法条原文与专业分析为准。");

  // ---- terms：文本命中即释义 ----
  const terms = extractTerms([headline, ...reasons, text.slice(0, 800)].join(" "));

  return { headline, reasons: reasons.slice(0, 4), warnings, terms };
}
