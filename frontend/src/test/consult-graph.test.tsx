/** 主页：trace 链路可视化 + 仲裁裁决 UI 状态联动（/api/consult/graph 挂起→恢复）。 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import Home from "@/app/page";
import { GRAPH_RESULT, GRAPH_RESUMED } from "./fixtures";

function mockFetch(routes: Record<string, unknown>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url).replace(/^https?:\/\/[^/]+/, "");
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    const key = `${init?.method ?? "GET"} ${path}`;
    const entry = routes[key];
    if (!entry) throw new Error(`未 mock 的请求：${key}`);
    // 恢复请求用 body.resume_decision 区分
    let payload = entry;
    if (path === "/api/consult/graph" && body.resume_decision) {
      payload = routes[`${key}#resume`] ?? entry;
    }
    return {
      ok: true,
      status: 200,
      json: async () => payload,
    } as Response;
  });
}

describe("主页 trace 可视化 + 仲裁裁决联动", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "POST /api/consult/graph": GRAPH_RESULT,
        "POST /api/consult/graph#resume": GRAPH_RESUMED,
      })
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("状态机咨询 → trace 节点链路渲染 + 挂起裁决 UI", async () => {
    render(<Home />);

    fireEvent.change(screen.getByLabelText("法律问题描述"), {
      target: { value: "对方不履行合同，能要求赔偿吗？" },
    });
    fireEvent.click(screen.getByRole("button", { name: /状态机深度咨询/ }));

    // 通俗模式（默认开）：trace 收进「法条原文与专业分析」可折叠区，先展开
    const details = await screen.findByText(/法条原文与专业分析（含执行轨迹）/, {
      selector: "summary",
    });
    fireEvent.click(details);

    // trace 链路可视化（每个节点一个 chip）
    await screen.findByText("intake(ok)");
    expect(screen.getByText("retrieve(1 hits, top=0.350)")).toBeInTheDocument();
    expect(screen.getByText("nli_verify(degraded, 0.1)")).toBeInTheDocument();

    // 仲裁裁决 UI（interrupted → alertdialog + 两个裁决按钮）在折叠区外，始终可见
    expect(screen.getByRole("alertdialog", { name: /NLI 降级人工裁决/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /批准带降级警示出稿/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /驳回不出结论/ })).toBeInTheDocument();
  });

  it("批准裁决 → resume 请求携带 thread_id 且 trace 追加终态", async () => {
    render(<Home />);
    fireEvent.change(screen.getByLabelText("法律问题描述"), {
      target: { value: "对方不履行合同，能要求赔偿吗？" },
    });
    fireEvent.click(screen.getByRole("button", { name: /状态机深度咨询/ }));

    // 展开 trace 折叠区（通俗模式默认开）
    fireEvent.click(await screen.findByText(/法条原文与专业分析（含执行轨迹）/, { selector: "summary" }));
    await screen.findByRole("alertdialog", { name: /NLI 降级人工裁决/ });

    fireEvent.click(screen.getByRole("button", { name: /批准带降级警示出稿/ }));

    // 恢复后 trace 追加 human_confirm(approve) + finalize（details 保持展开，追加内容直接可见）
    await screen.findByText("human_confirm(approve)");
    expect(screen.getByText(/finalize\(degraded/)).toBeInTheDocument();
    // 裁决 UI 消失
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    // 法律输出区预埋全局免责声明（可能多处，至少一处）
    expect(screen.getAllByText(/本工具仅为法律信息推演参考/).length).toBeGreaterThan(0);
    // 恢复请求确实带了 resume_decision 与 thread_id
    const calls = (globalThis.fetch as ReturnType<typeof mockFetch>).mock.calls;
    const last = JSON.parse(String(calls[calls.length - 1][1]!.body));
    expect(last.resume_decision).toBe("approve");
    expect(last.thread_id).toBe("consult-test123");
  });

  it("快速咨询按钮与 BYOK 面板共存（演示模式默认）", async () => {
    render(<Home />);
    expect(screen.getByRole("button", { name: /快速咨询/ })).toBeInTheDocument();
    expect(screen.getByText(/BYOK 设置/)).toBeInTheDocument();
    expect(screen.getByText(/未配置 · 演示模式/)).toBeInTheDocument();
  });
});
