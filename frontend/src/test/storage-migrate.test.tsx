/**
 * 品牌更名后的 localStorage 键迁移单测。
 *
 * 背景：产品品牌由「LexSentinel」更名为「EXCLUSLAYWER」，localStorage 键前缀
 * 随之由 lexsentinel.* 改为 excluslawyer.*。本文件锁定「旧键读时迁移」行为：
 * 改名之前用户保存的 BYOK API Key、主题与通俗模式偏好都不得丢失。
 */
import { describe, expect, it, vi } from "vitest";
import { readWithMigration } from "@/lib/storage-migrate";
import { loadByokConfig } from "@/lib/api";
import { getStoredTheme } from "@/lib/theme";

describe("存储键迁移工具 readWithMigration", () => {
  it("新键存在时直接命中，不触碰旧键", () => {
    localStorage.setItem("excluslawyer.theme", "dark");
    localStorage.setItem("lexsentinel.theme", "light");

    expect(readWithMigration("excluslawyer.theme", "lexsentinel.theme")).toBe("dark");
    // 新键命中时旧键保持原样（不误删）
    expect(localStorage.getItem("lexsentinel.theme")).toBe("light");
  });

  it("仅有旧键时迁移到新键并清理旧键", () => {
    localStorage.setItem("lexsentinel.theme", "light");

    expect(readWithMigration("excluslawyer.theme", "lexsentinel.theme")).toBe("light");
    expect(localStorage.getItem("excluslawyer.theme")).toBe("light");
    expect(localStorage.getItem("lexsentinel.theme")).toBeNull();
  });

  it("新旧键都不存在时返回 null", () => {
    expect(readWithMigration("excluslawyer.theme", "lexsentinel.theme")).toBeNull();
  });

  it("迁移幂等：重复读取不改变结果", () => {
    localStorage.setItem("lexsentinel.theme", "dark");

    expect(readWithMigration("excluslawyer.theme", "lexsentinel.theme")).toBe("dark");
    expect(readWithMigration("excluslawyer.theme", "lexsentinel.theme")).toBe("dark");
    expect(localStorage.getItem("lexsentinel.theme")).toBeNull();
  });
});

describe("各模块的旧键迁移", () => {
  it("BYOK：旧键中的 API Key 迁移到新键，用户无需重新输入", () => {
    localStorage.setItem(
      "lexsentinel.byok",
      JSON.stringify({ baseUrl: "https://api.deepseek.com/v1", apiKey: "sk-legacy-123", model: "deepseek-chat" })
    );

    const cfg = loadByokConfig();
    expect(cfg.apiKey).toBe("sk-legacy-123");
    expect(cfg.baseUrl).toBe("https://api.deepseek.com/v1");
    expect(localStorage.getItem("excluslawyer.byok")).not.toBeNull();
    expect(localStorage.getItem("lexsentinel.byok")).toBeNull();
  });

  it("主题：旧键的暗色偏好迁移到新键", () => {
    localStorage.setItem("lexsentinel.theme", "dark");

    expect(getStoredTheme()).toBe("dark");
    expect(localStorage.getItem("excluslawyer.theme")).toBe("dark");
    expect(localStorage.getItem("lexsentinel.theme")).toBeNull();
  });

  it("通俗模式：模块初始化时把旧键迁移到新键", async () => {
    localStorage.setItem("lexsentinel.plain", "pro");
    vi.resetModules();

    const mod = await import("@/lib/plain-mode");
    expect(mod.getPlainMode()).toBe("pro");
    expect(localStorage.getItem("excluslawyer.plain")).toBe("pro");
    expect(localStorage.getItem("lexsentinel.plain")).toBeNull();
  });
});
