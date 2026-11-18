/**
 * localStorage 键迁移工具。
 *
 * 背景：产品品牌在 v0.1.0 发布前由「LexSentinel」统一更名为「EXCLUSLAYWER」，
 * localStorage 键前缀随之由 lexsentinel.* 改为 excluslawyer.*。
 *
 * 策略：读取时若新键不存在但旧键存在，则把旧值写入新键并清理旧键。
 * 这样用户在改名之前保存的 BYOK API Key、主题与通俗模式偏好都不会丢失，
 * 无需重新输入或重设。迁移是幂等的（第二次读取时新键已存在，直接命中）。
 */

/**
 * 读取存储键，必要时从旧品牌键迁移。
 *
 * @param currentKey 新品牌键（excluslawyer.*）
 * @param legacyKey  旧品牌键（lexsentinel.*），仅用于一次性迁移
 * @returns 存储值；两者都不存在时返回 null
 */
export function readWithMigration(currentKey: string, legacyKey: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    const current = window.localStorage.getItem(currentKey);
    if (current !== null) return current;

    const legacy = window.localStorage.getItem(legacyKey);
    if (legacy === null) return null;

    window.localStorage.setItem(currentKey, legacy);
    window.localStorage.removeItem(legacyKey);
    return legacy;
  } catch {
    // 隐私模式下 localStorage 不可用，静默回退默认值
    return null;
  }
}
