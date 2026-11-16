/** KgGraphCanvas：G6 画布渲染、类型无报错、法域取色走 CSS 变量。 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import KgGraphCanvas, { jurColorOf } from "@/components/KgGraphCanvas";
import { KG_RESULT } from "./fixtures";

// 替身 G6：记录构造与渲染调用（jsdom 无 canvas）
const renderSpy = vi.fn();
const destroySpy = vi.fn();
vi.mock("@antv/g6", () => ({
  Graph: class {
    constructor(_cfg: unknown) {}
    render() {
      renderSpy();
    }
    destroy() {
      destroySpy();
    }
  },
}));

describe("KgGraphCanvas", () => {
  it("渲染画布容器并带无障碍标签", async () => {
    render(<KgGraphCanvas result={KG_RESULT} jurFilter={null} />);
    const canvas = await screen.findByRole("img", { name: /知识图谱画布/ });
    expect(canvas).toBeInTheDocument();
    expect(canvas).toHaveAttribute("aria-label", expect.stringContaining("违约责任"));
  });

  it("G6 Graph.render 被调用且无异常抛出", async () => {
    render(<KgGraphCanvas result={KG_RESULT} jurFilter={null} />);
    await vi.waitFor(() => expect(renderSpy).toHaveBeenCalled());
  });

  it("法域过滤只影响展示，不抛错（缓存数据不动）", async () => {
    const before = JSON.stringify(KG_RESULT);
    render(<KgGraphCanvas result={KG_RESULT} jurFilter="JP" />);
    await vi.waitFor(() => expect(renderSpy).toHaveBeenCalled());
    expect(JSON.stringify(KG_RESULT)).toBe(before); // 入参缓存未被污染
  });

  it("jurColorOf 按法域前缀取 CSS 变量色", () => {
    // jsdom 中 getComputedStyle 返回空 → 回退色仍为合法颜色串，不抛错
    for (const id of ["s:CN-MINFA-577", "s:JP-MIN-415", "s:KR-MIN-390", "s:SG-EA-1", "c:breach"]) {
      expect(typeof jurColorOf(id)).toBe("string");
    }
  });
});
