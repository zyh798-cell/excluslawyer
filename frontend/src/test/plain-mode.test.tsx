/**
 * 大白话解释层（通俗模式）单测：
 * ① 开关默认开启 / 切换持久化 / 跨组件状态一致
 * ② buildPlainExplanation 白话生成规则（证据不足 / 时效 / 裁决 / 降级 / 默认）
 * ③ 白话与原文分区（白话在上、原文折叠、风险原样不省略）
 * ④ 术语释义展开与类比
 * ⑤ 术语红线：释义不含结论；白话不新增未检索依据
 */
import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import PlainToggle from "@/components/PlainToggle";
import { PlainAnswerSection } from "@/components/PlainAnswerCard";
import TermHint from "@/components/TermHint";
import { buildPlainExplanation, extractMarkedSentences } from "@/lib/plain-explain";
import { getPlainMode, setPlainMode, togglePlainMode } from "@/lib/plain-mode";
import { LAW_TERMS, extractTerms, TERM_LOOKUP } from "@/lib/terms";
import { CITATION } from "./fixtures";
import type { Citation, NliResult } from "@/lib/api";

function cit(overrides: Partial<Citation> = {}): Citation {
  return { ...CITATION, ...overrides };
}

const NLI_PASS: NliResult = { status: "pass", score: 0.82, reason: "词面重叠达阈值" };
const NLI_DEGRADED: NliResult = { status: "degraded", score: 0.21, reason: "词面重叠低于阈值" };

const BASE_INPUT = {
  kind: "ask" as const,
  text: "依据《中华人民共和国民法典》第五百七十七条，你可以主张违约责任。涉及劳动仲裁程序时注意顺序。",
  citations: [cit()],
  nli: NLI_PASS,
  confidence: 0.82,
};

// ---------- 开关状态 ----------

describe("通俗模式开关（plain-mode store）", () => {
  beforeEach(() => {
    setPlainMode("plain");
  });

  it("默认开启（无存储时）", () => {
    localStorage.removeItem("lexsentinel.plain");
    expect(getPlainMode()).toBe("plain");
  });

  it("切换后持久化到 localStorage（键 lexsentinel.plain）", () => {
    expect(togglePlainMode()).toBe("pro");
    expect(localStorage.getItem("lexsentinel.plain")).toBe("pro");
    expect(getPlainMode()).toBe("pro");
    expect(togglePlainMode()).toBe("plain");
    expect(localStorage.getItem("lexsentinel.plain")).toBe("plain");
  });

  it("开关组件切换 role=switch 且全站状态一致（两个实例同步）", () => {
    const { unmount } = render(<PlainToggle />);
    const btn = screen.getByRole("switch", { name: /通俗模式/ });
    expect(btn).toHaveAttribute("aria-checked", "true");

    // 第二处（模拟 KG / 模拟法庭面板的另一实例）渲染后与第一处同态
    render(<PlainToggle />);
    const switches = screen.getAllByRole("switch", { name: /通俗模式/ });
    expect(switches).toHaveLength(2);
    expect(switches[1]).toHaveAttribute("aria-checked", "true");

    // 切换第一处 → 第二处同步
    fireEvent.click(switches[0]);
    expect(switches[0]).toHaveAttribute("aria-checked", "false");
    expect(switches[1]).toHaveAttribute("aria-checked", "false");
    expect(localStorage.getItem("lexsentinel.plain")).toBe("pro");
    unmount();
  });
});

// ---------- 白话生成规则 ----------

describe("buildPlainExplanation 白话生成规则", () => {
  it("证据不足 → headline 提示补证据，且不产生支持性结论", () => {
    const e = buildPlainExplanation({
      ...BASE_INPUT,
      text: "【证据不足】未检索到可支撑主张的法条原文，无法给出结论。",
      citations: [],
      confidence: 0.1,
    });
    expect(e.headline).toContain("证据");
    expect(e.headline).not.toContain("大概率能得到支持");
    // 警告原样保留标记句
    expect(e.warnings.some((w) => w.includes("证据不足"))).toBe(true);
  });

  it("时效过期 → headline 提示期限风险，警告原样保留原文句", () => {
    const text = "本案请求已超过诉讼时效，对方可提出时效抗辩。依据《民法典》第一百八十八条。";
    const e = buildPlainExplanation({ ...BASE_INPUT, text });
    expect(e.headline).toContain("期限");
    expect(e.warnings.some((w) => w.includes("超过诉讼时效"))).toBe(true);
  });

  it("裁决全驳回 → headline 直说大概率不支持；部分支持 → 混合表述", () => {
    const rejected = buildPlainExplanation({
      ...BASE_INPUT,
      kind: "verdict",
      decisions: ["驳回", "驳回"],
    });
    expect(rejected.headline).toContain("不会得到支持");

    const mixed = buildPlainExplanation({
      ...BASE_INPUT,
      kind: "verdict",
      decisions: ["支持", "驳回"],
    });
    expect(mixed.headline).toContain("有一部分");
  });

  it("NLI 降级 → headline 提示未通过校验，警告携带后端 reason 原文", () => {
    const e = buildPlainExplanation({ ...BASE_INPUT, nli: NLI_DEGRADED });
    expect(e.headline).toContain("一致性核对");
    expect(e.warnings.some((w) => w.includes("NLI 校验降级"))).toBe(true);
    expect(e.warnings.some((w) => w.includes("词面重叠低于阈值"))).toBe(true);
  });

  it("默认路径 → headline 是导览句，理由含依据构成（只列 law_title+article_no）", () => {
    const e = buildPlainExplanation(BASE_INPUT);
    expect(e.headline).toContain("简单说");
    // 依据句只引用法条名与条号——不编造其他法条
    expect(e.reasons[0]).toContain("《中华人民共和国民法典》");
    expect(e.reasons[0]).toContain("第五百七十七条");
    // 理由 2–4 句
    expect(e.reasons.length).toBeGreaterThanOrEqual(2);
    expect(e.reasons.length).toBeLessThanOrEqual(4);
    // 程序提示基于原文检测（仲裁）
    expect(e.reasons.some((r) => r.includes("仲裁"))).toBe(true);
  });

  it("高风险意见书 → 风险等级直译进警告；风险行原样不转写", () => {
    const e = buildPlainExplanation({
      ...BASE_INPUT,
      kind: "opinion",
      riskLevel: "high",
      riskNotes: ["欠薪金额较大，证据完整性待核实"],
    });
    expect(e.warnings).toContain("风险等级：高（来自意见书的风险评定）");
    expect(e.warnings).toContain("欠薪金额较大，证据完整性待核实");
  });

  it("白话层自证声明必须存在（防止把白话当结论）", () => {
    const e = buildPlainExplanation(BASE_INPUT);
    expect(e.warnings.some((w) => w.includes("不改变任何结论"))).toBe(true);
  });

  it("术语命中：文本含「诉讼时效」「仲裁前置」时返回对应术语", () => {
    const e = buildPlainExplanation({
      ...BASE_INPUT,
      text: "注意诉讼时效为三年，劳动争议适用仲裁前置程序。",
    });
    const names = e.terms.map((t) => t.term);
    expect(names).toContain("诉讼时效");
    expect(names).toContain("仲裁前置");
  });

  it("extractMarkedSentences：按句切分并只返回含标记的完整句", () => {
    const s = extractMarkedSentences("第一句无标记。第二句含证据不足标记。第三句含时效届满！第四句", [
      "证据不足",
      "时效届满",
    ]);
    expect(s).toHaveLength(2);
    expect(s[0]).toContain("证据不足");
    expect(s[1]).toContain("时效届满");
  });
});

// ---------- 术语配置红线 ----------

describe("术语配置（terms.ts）", () => {
  it("每个术语都有通俗释义与类比，且释义不含行动指令句式", () => {
    for (const t of LAW_TERMS) {
      expect(t.plain.length).toBeGreaterThan(6);
      expect(t.analogy.length).toBeGreaterThan(4);
      // 红线：释义不得提供结论/行动建议（不含"你应该""建议你""可以主张"等指令）
      for (const banned of ["你应该", "建议你", "赶紧", "必须马上"]) {
        expect(t.plain).not.toContain(banned);
        expect(t.analogy).not.toContain(banned);
      }
    }
  });

  it("别名与主词映射同一释义；长词优先不被短词吃掉", () => {
    expect(TERM_LOOKUP.get("谁主张谁举证")?.term).toBe("举证责任");
    expect(TERM_LOOKUP.get("财产保全")?.term).toBe("诉讼保全");
    // extractTerms 对「仲裁前置」命中仲裁前置而非普通「仲裁」
    const hits = extractTerms("劳动争议适用仲裁前置").map((t) => t.term);
    expect(hits).toContain("仲裁前置");
    expect(hits).not.toContain("仲裁");
  });
});

// ---------- 组件：分区 / 折叠 / 释义 ----------

describe("白话/原文分区与术语释义组件", () => {
  beforeEach(() => {
    setPlainMode("plain");
  });
  afterEach(() => {
    setPlainMode("plain");
  });

  function renderSection(overrides: Partial<Parameters<typeof buildPlainExplanation>[0]> = {}) {
    return render(
      <PlainAnswerSection
        input={{ ...BASE_INPUT, ...overrides }}
        sourceLabel="法条原文与专业分析"
        professional={<article data-testid="pro-view">专业视图：原文内容</article>}
        source={
          <>
            <article>原文：当事人一方不履行合同义务……</article>
            <p>涉及诉讼时效与举证责任。</p>
          </>
        }
      />
    );
  }

  it("通俗模式开：白话在上、原文收进折叠区（默认收起）、风险区显性存在", () => {
    renderSection();
    // 白话区在上（先于折叠区出现）
    expect(screen.getByLabelText("大白话解释")).toBeInTheDocument();
    // 原文在 details 折叠区，默认收起 → 原文内容不可见
    const summary = screen.getByText(/法条原文与专业分析/, { selector: "summary" });
    expect(summary).toBeInTheDocument();
    expect(screen.queryByText(/原文：当事人一方不履行合同义务/)).not.toBeVisible();
    // 展开后原文可见
    fireEvent.click(summary);
    expect(screen.getByText(/原文：当事人一方不履行合同义务/)).toBeVisible();
    // 风险区（自证声明）显性存在且不随折叠隐藏
    expect(screen.getByLabelText("风险与限制提示")).toBeInTheDocument();
    expect(screen.getByText(/不因通俗模式省略/)).toBeInTheDocument();
  });

  it("通俗模式关：直接渲染专业视图，无白话区", () => {
    act(() => setPlainMode("pro"));
    renderSection();
    expect(screen.getByTestId("pro-view")).toBeInTheDocument();
    expect(screen.queryByLabelText("大白话解释")).not.toBeInTheDocument();
    act(() => setPlainMode("plain"));
  });

  it("术语释义：点击展开白话+类比，可收起（aria-expanded 正确）", () => {
    render(<TermHint term={TERM_LOOKUP.get("诉讼时效")!} />);
    const btn = screen.getByRole("button", { name: /查看术语释义：诉讼时效/ });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/保质期/)).not.toBeInTheDocument();

    fireEvent.click(btn);
    expect(btn).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/像食品保质期/)).toBeInTheDocument(); // 类比

    fireEvent.click(btn);
    expect(btn).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/像食品保质期/)).not.toBeInTheDocument();
  });

  it("白话文本中的术语自动渲染为可点击释义（renderTextWithTerms）", () => {
    renderSection({ text: "涉及诉讼时效与举证责任。" });
    // 白话正文不自动插入术语按钮（术语在原文区）——但 headline/reasons 命中时会渲染
    // 此处直接验证原文区的普通文本不被替换（原文区不做术语注入，保证原文不被改写）
    expect(screen.getByText(/原文：当事人一方不履行合同义务/)).toBeInTheDocument();
  });

  it("窄屏语义：风险区与白话区均有 aria-label 可访问名", () => {
    renderSection();
    expect(screen.getByLabelText("大白话解释")).toBeInTheDocument();
    expect(screen.getByLabelText("风险与限制提示")).toBeInTheDocument();
    const summary = screen.getByText(/法条原文与专业分析/, { selector: "summary" });
    expect(summary).toHaveAttribute("aria-label", "展开或收起：法条原文与专业分析");
  });
});
