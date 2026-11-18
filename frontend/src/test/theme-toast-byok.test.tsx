/** 主题切换（无闪烁内联脚本+类切换）、Toast 弹窗、ByokSettings 设置面板。 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import ThemeToggle from "@/components/ThemeToggle";
import ToastHost, { showToast } from "@/components/Toast";
import ByokSettings from "@/components/ByokSettings";
import { applyTheme, toggleTheme, getStoredTheme } from "@/lib/theme";

describe("主题切换", () => {
  it("toggleTheme 切换 html.dark 类并持久化 localStorage（首帧内联脚本同键）", () => {
    document.documentElement.classList.remove("dark");
    const next = toggleTheme();
    expect(next).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(getStoredTheme()).toBe("dark"); // THEME_INIT 脚本读的同一个键

    const back = toggleTheme();
    expect(back).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(getStoredTheme()).toBe("light");
  });

  it("ThemeToggle 按钮有 aria-label 且点击切换主题", () => {
    applyTheme("dark");
    render(<ThemeToggle />);
    const btn = screen.getByRole("button", { name: /切换到亮色主题/ });
    fireEvent.click(btn);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});

describe("Toast 弹窗", () => {
  it("showToast 触发渲染并带 role=status", async () => {
    render(<ToastHost />);
    act(() => showToast("测试提示", "ok"));
    expect(await screen.findByText("测试提示")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});

describe("ByokSettings 设置面板", () => {
  it("展开面板、输入保存 localStorage、一键清除", async () => {
    const onChange = vi.fn();
    render(<ByokSettings onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: /展开或收起 BYOK 设置/ }));
    const keyInput = screen.getByLabelText("API Key");
    fireEvent.change(keyInput, { target: { value: "sk-test-12345678" } });
    await waitFor(() => expect(onChange).toHaveBeenCalled());

    const stored = JSON.parse(localStorage.getItem("excluslawyer.byok")!);
    expect(stored.apiKey).toBe("sk-test-12345678"); // 只在 localStorage

    fireEvent.click(screen.getByRole("button", { name: /一键清除 BYOK 配置/ }));
    // 一键清除 = 移除存储键（隐私设计）
    expect(localStorage.getItem("excluslawyer.byok")).toBeNull();
  });

  it("安全自检：密钥混入后端载荷会被守卫拦截", async () => {
    const onChange = vi.fn();
    render(<ByokSettings onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /展开或收起 BYOK 设置/ }));
    fireEvent.change(screen.getByLabelText("API Key"), { target: { value: "sk-leak-abcdef123" } });

    fireEvent.click(screen.getByRole("button", { name: /运行密钥泄露风险自检/ }));
    await screen.findByText(/密钥存储位置/);
    expect(screen.getByText(/后端载荷守卫/)).toBeInTheDocument();
    // 全部通过时无 ✗ 项
    expect(screen.queryByText(/✗/)).not.toBeInTheDocument();
  });
});
