/** FactPanel / OpinionView / CitationPanel：渲染、语义令牌、aria 无障碍、全局免责。 */
import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import FactPanel from "@/components/FactPanel";
import OpinionView from "@/components/OpinionView";
import CitationPanel from "@/components/CitationPanel";
import { LEGAL_DISCLAIMER } from "@/lib/disclaimer";
import { CITATION, FACT_SET, OPINION } from "./fixtures";

describe("FactPanel 事实校验面板", () => {
  it("四类事实与时间线渲染", () => {
    render(<FactPanel factSet={FACT_SET} />);
    expect(screen.getByText(/四类事实（4 条）/)).toBeInTheDocument();
    expect(screen.getByText(/已确认 × 1/)).toBeInTheDocument();
    expect(screen.getByText(/待核实 × 1/)).toBeInTheDocument();
    expect(screen.getByText(/假设 × 1/)).toBeInTheDocument();
    expect(screen.getByText(/主张 × 1/)).toBeInTheDocument();
    expect(screen.getAllByText("公司拖欠三个月工资").length).toBeGreaterThan(0); // 事实卡+时间线各一处
    expect(screen.getByText(/时间线卡片/)).toBeInTheDocument();
  });
});

describe("OpinionView 观点展示", () => {
  it("五段式内容 + 风险徽章 + 免责声明预埋", () => {
    const { container } = render(<OpinionView opinion={OPINION} />);
    expect(screen.getByText("一、事实认定")).toBeInTheDocument();
    expect(screen.getByText("二、法律适用")).toBeInTheDocument();
    expect(screen.getByText(/风险：中/)).toBeInTheDocument();
    // 全局免责声明（⚠️ 前缀导致文本拆节点，用正则）
    expect(screen.getByText(/本工具仅为法律信息推演参考/)).toBeInTheDocument();
    // 语义令牌（主题变量映射类），不再是硬编码 slate/ink
    expect(container.querySelector(".text-fg")).not.toBeNull();
    expect(container.querySelector(".text-fg-muted")).not.toBeNull();
  });
});

describe("CitationPanel 引用展示", () => {
  it("时效徽章 + aria 展开/收起 + 官源链接", () => {
    render(<CitationPanel citations={[CITATION]} />);
    expect(screen.getByText("现行有效")).toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: /中华人民共和国民法典/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/当事人一方不履行合同义务/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /官方法规源/ })).toHaveAttribute("href", "https://flk.npc.gov.cn/");
    // 全局免责声明
    expect(screen.getByText(/本工具仅为法律信息推演参考/)).toBeInTheDocument();
  });

  it("无引用时提示证据不足铁律", () => {
    render(<CitationPanel citations={[]} />);
    expect(screen.getByText(/证据不足/)).toBeInTheDocument();
  });
});
