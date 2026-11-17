/**
 * 场景化入口（普通人友好层 P0）：配置完整性、栅格渲染、问卷流转、摘要预填、法域联动。
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import Home from "@/app/page";
import {
  SCENARIOS,
  buildScenarioSummary,
  getScenario,
  JURISDICTION_LABELS,
  type JurisdictionCode,
  type Scenario,
} from "@/config/scenarios";

function mockFetch(routes: Record<string, unknown>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url).replace(/^https?:\/\/[^/]+/, "");
    const key = `${init?.method ?? "GET"} ${path}`;
    const entry = routes[key];
    if (!entry) throw new Error(`未 mock 的请求：${key}`);
    return { ok: true, status: 200, json: async () => entry } as Response;
  });
}

describe("场景配置（config/scenarios.ts）", () => {
  it("8 个生活场景齐全，字段与标签结构合规", () => {
    expect(SCENARIOS).toHaveLength(8);
    const ids = SCENARIOS.map((s) => s.id);
    expect(new Set(ids).size).toBe(8);
    for (const s of SCENARIOS) {
      expect(s.name.length).toBeGreaterThan(0);
      expect(s.summary.length).toBeGreaterThan(0);
      expect(s.tags.length).toBeGreaterThanOrEqual(2);
      expect(s.tags.length).toBeLessThanOrEqual(4);
      expect(s.jurisdictions.length).toBeGreaterThan(0);
      expect(s.fields.length).toBeGreaterThan(0);
      expect(s.askPrompt.length).toBeGreaterThan(0);
      // 每个字段都必须有 key / label / type
      for (const f of s.fields) {
        expect(f.key).toBeTruthy();
        expect(f.label).toBeTruthy();
        expect(["text", "textarea", "number", "select", "date"]).toContain(f.type);
        if (f.type === "select") {
          expect((f.options ?? []).length).toBeGreaterThan(0);
        }
      }
    }
  });

  it("八个场景覆盖用户指定的类别", () => {
    const names = SCENARIOS.map((s) => s.name).join("|");
    for (const kw of [
      "租房",
      "劳动",
      "消费",
      "婚姻",
      "交通事故",
      "借贷",
      "留学签证",
      "直接提问",
    ]) {
      expect(names).toContain(kw);
    }
  });

  it("getScenario 按 id 命中，未知 id 返回 undefined", () => {
    expect(getScenario("rental")?.name).toBe("租房与押金");
    expect(getScenario("other")?.name).toContain("直接提问");
    expect(getScenario("nope" as never)).toBeUndefined();
  });

  it("buildScenarioSummary 生成结构化案情摘要，未填字段跳过", () => {
    const s = getScenario("rental")!;
    const summary = buildScenarioSummary(s, {
      city: "杭州",
      dispute: "押金不退",
      contract: "",
      deposit: "2000",
    });
    expect(summary).toContain("【租房与押金】");
    expect(summary).toContain("城市：杭州");
    expect(summary).toContain("争议事项：押金不退");
    expect(summary).toContain("押金金额（元）：2000");
    expect(summary).toContain(s.askPrompt);
    // 空值字段不出现在摘要里
    expect(summary).not.toContain("是否签订书面合同：");
    // 摘要末尾以句号收束
    expect(summary.endsWith("。")).toBe(true);
  });

  it("buildScenarioSummary 无任何填写时仍保留场景名与诉求", () => {
    const s = getScenario("other")!;
    const summary = buildScenarioSummary(s, {});
    expect(summary).toContain("【其他 / 直接提问】");
    expect(summary).toContain(s.askPrompt);
  });
});

describe("场景入口渲染与交互（Home）", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", mockFetch({}));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("首页顶部展示产品标识 + 法域选择器 + 场景卡片栅格", () => {
    render(<Home />);

    // 产品标识（内联 SVG 天平徽记 + 名称）
    const bar = screen.getByRole("region", { name: "产品标识与法域选择" });
    expect(bar).toBeInTheDocument();
    expect(bar.querySelector("p")?.textContent).toBe("LexSentinel");
    const mark = document.querySelector('svg[viewBox="0 0 64 64"]');
    expect(mark).not.toBeNull();

    // 法域选择器（radiogroup，四个法域）
    const group = screen.getByRole("radiogroup", { name: "适用法域" });
    expect(group).toBeInTheDocument();
    for (const code of Object.keys(JURISDICTION_LABELS) as JurisdictionCode[]) {
      expect(
        screen.getByRole("radio", { name: `法域：${JURISDICTION_LABELS[code]}` })
      ).toBeInTheDocument();
    }

    // 8 张场景卡片（ul/li 语义列表 + 整卡为按钮）
    expect(screen.getByRole("list", { name: "生活场景入口" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(SCENARIOS.length);
    for (const s of SCENARIOS) {
      expect(screen.getByRole("button", { name: new RegExp(`^${s.name}`) })).toBeInTheDocument();
    }
  });

  it("保留直接自由提问的输入框与三个主按钮", () => {
    render(<Home />);
    expect(screen.getByLabelText("法律问题描述")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /快速咨询/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /生成法律意见书/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /状态机深度咨询/ })).toBeInTheDocument();
    // 原有法域 select 仍在（与顶部按钮双向同步）
    expect(screen.getByLabelText("选择法域")).toBeInTheDocument();
  });

  it("底部保留全局免责声明", () => {
    render(<Home />);
    expect(screen.getAllByText(/本工具仅为法律信息推演参考/).length).toBeGreaterThan(0);
  });

  it("点击场景 → 出现分步问卷，必填未填时下一步禁用", () => {
    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /^租房与押金/ }));

    const q = screen.getByTestId("scenario-questionnaire");
    expect(q).toBeInTheDocument();
    expect(screen.getByText(/第 1 \/ 6 步/)).toBeInTheDocument();

    // 必填字段（城市）为空 → 下一步禁用
    const next = screen.getByRole("button", { name: "下一步" });
    expect(next).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/城市/), { target: { value: "杭州" } });
    expect(screen.getByRole("button", { name: "下一步" })).toBeEnabled();
  });

  it("走完问卷 → 结构化摘要预填提问框，且用户仍可编辑", async () => {
    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /^劳动与离职/ }));

    // 第 1 步：入职时间（必填）
    fireEvent.change(screen.getByLabelText(/入职时间/), { target: { value: "2024 年 3 月" } });
    fireEvent.click(screen.getByRole("button", { name: "下一步" }));

    // 第 2 步：合同类型（必填，select）
    fireEvent.change(screen.getByLabelText(/合同类型/), { target: { value: "未签书面劳动合同" } });
    fireEvent.click(screen.getByRole("button", { name: "下一步" }));

    // 第 3 步：争议事项（必填）
    fireEvent.change(screen.getByLabelText(/争议事项/), { target: { value: "拖欠工资" } });

    // 剩余步骤均为选填：一直推进到末步
    for (let i = 0; i < 10; i++) {
      const next = screen.queryByRole("button", { name: "下一步" });
      if (!next) break;
      fireEvent.click(next);
    }

    // 末步：生成案情摘要
    expect(screen.getByRole("button", { name: "生成案情摘要" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "生成案情摘要" }));

    const box = screen.getByLabelText("法律问题描述") as HTMLTextAreaElement;
    await waitFor(() => expect(box.value).toContain("【劳动与离职】"));
    expect(box.value).toContain("入职时间：2024 年 3 月");
    expect(box.value).toContain("合同类型：未签书面劳动合同");
    expect(box.value).toContain("争议事项：拖欠工资");

    // 用户仍可自由修改
    fireEvent.change(box, { target: { value: box.value + " 另外还有加班费。" } });
    expect((screen.getByLabelText("法律问题描述") as HTMLTextAreaElement).value).toContain(
      "另外还有加班费。"
    );
  });

  it("问卷退出后可回到场景栅格", () => {
    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /^消费维权/ }));
    expect(screen.getByTestId("scenario-questionnaire")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /退出/ }));
    expect(screen.queryByTestId("scenario-questionnaire")).not.toBeInTheDocument();
    expect(screen.getByRole("list", { name: "生活场景入口" })).toBeInTheDocument();
  });

  it("场景法域与当前法域不一致时自动切换法域", () => {
    render(<Home />);
    // 当前默认 CN；「留学签证」覆盖四法域，仍为 CN
    fireEvent.click(screen.getByRole("button", { name: /^留学签证与学业事务/ }));
    expect((screen.getByLabelText("选择法域") as HTMLSelectElement).value).toBe("CN");

    // 切到 JP 后再选仅 CN 的场景 → 自动切回 CN
    fireEvent.click(screen.getByRole("radio", { name: "法域：日本" }));
    expect((screen.getByLabelText("选择法域") as HTMLSelectElement).value).toBe("JP");
    fireEvent.click(screen.getByRole("button", { name: /退出/ }));
    fireEvent.click(screen.getByRole("button", { name: /^租房与押金/ }));
    expect((screen.getByLabelText("选择法域") as HTMLSelectElement).value).toBe("CN");
  });

  it("顶部法域按钮与咨询区 select 双向同步", () => {
    render(<Home />);
    fireEvent.click(screen.getByRole("radio", { name: "法域：新加坡" }));
    expect((screen.getByLabelText("选择法域") as HTMLSelectElement).value).toBe("SG");
    fireEvent.change(screen.getByLabelText("选择法域"), { target: { value: "KR" } });
    expect(screen.getByRole("radio", { name: "法域：韩国" })).toHaveAttribute("aria-checked", "true");
  });

  it("场景配置本身可扩展：新增一条即自动出现在栅格（契约测试）", () => {
    const custom: Scenario = {
      id: "custom" as Scenario["id"],
      name: "自定义场景",
      summary: "测试用",
      tags: ["标签一", "标签二"],
      jurisdictions: ["CN"],
      icon: "message-circle",
      fields: [{ key: "k", label: "字段", type: "text" }],
      askPrompt: "请分析。",
    };
    expect(custom.name).toBe("自定义场景");
    expect(custom.tags.length).toBeGreaterThanOrEqual(2);
  });
});
