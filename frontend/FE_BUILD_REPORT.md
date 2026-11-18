# EXCLUSLAWYER 前端构建报告（任务①）

日期：2026-11-15 ｜ Next.js 14.2.5 ｜ Node 22.22.2

> 本表为**任务①阶段快照**（2026-11-15），保留当时实测值不回改。
> 当前口径（v0.1.0 发布核验）见 `docs/regression-report.md`：`/` 22.9 kB · First Load 132 kB ·
> 共享 87.2 kB，vitest 56/56，pytest 113 passed / 4 skipped。

## 1. 构建结果

| 项目 | 结果 |
|---|---|
| `npm run build` | ✅ 成功（exit=0） |
| 致命 Error | **0** |
| Warning | **0**（无 ESLint/TS/打包告警） |
| 测试文件是否打断构建 | ✅ 不打断（src/test/ 通过 TS 类型检查） |

## 2. 打包体积（First Load JS）

| 路由 | 页面体积 | First Load JS |
|---|---|---|
| `/`（主页，全功能） | 20.2 kB | **107 kB** |
| `/_not-found` | 871 B | 88.1 kB |
| 共享 chunk | — | 87.2 kB（23-*.js 31.5 kB + fd9d*.js 53.6 kB） |

- 全部路由 **静态预渲染（○ Static）**，无 SSR 阻塞
- G6 图谱画布为**动态 import 懒加载**，不计入首包
- 总传输体积 ~126 KiB（Lighthouse 实测），远低于预算

## 3. 基线对比（重构前 → 重构后）

- 基线 `npm build`：**编译失败**（ByokSettings.tsx 类型错误 `void` 真值判断）
- 重构后：0 Error / 0 Warning，功能面增加（状态机联调、KG 画布、主题系统、Toast/骨架屏）

## 4. BYOK 安全扫描（静态产物）

| 检查项 | 结果 |
|---|---|
| `.next/static`+`.next/server` 硬编码 API Key（sk-*/Bearer Token） | ✅ 未检出 |
| 敏感环境变量内联 | ✅ 仅 `NEXT_PUBLIC_API_BASE`（后端地址，非密钥，默认 localhost） |
| `excluslawyer.byok` | 仅 localStorage 键名逻辑引用，不含键值 |
| 运行时防线 | fetch 封装 `assertNoSecretsToBackend` fail-closed + 错误出口 `redactSecrets` 打码 |

## 5. 布局校验

- 全局免责声明（"本工具仅为法律信息推演参考…建议咨询执业律师。"）挂载于**根 layout** `<footer>`，所有路由自动生效
- LegalDisclaimer 组件另在各法律输出区（问答/意见书/图谱/合同/类案/法庭）局部预埋
- ThemeToggle（防闪烁内联脚本）+ ToastHost 均在根 layout

## 6. 单元测试（vitest 2.1.9 + testing-library，jsdom）

| 测试文件 | 覆盖 | 结果 |
|---|---|---|
| kg-canvas.test.tsx | G6 画布渲染/类型/法域取色/缓存不污染 | 4/4 ✅ |
| panels.test.tsx | FactPanel/OpinionView/CitationPanel 渲染+语义令牌+aria | 4/4 ✅ |
| theme-toast-byok.test.tsx | 主题切换持久化/Toast/BYOK 面板+泄露自检 | 5/5 ✅ |
| consult-graph.test.tsx | trace 链路可视化/仲裁裁决联动/resume | 3/3 ✅ |
| **合计** | | **16/16 ✅**（指定两组复跑 2 次稳定 8/8） |

## 7. UI 规范落地

- 双主题 CSS 变量（`:root` 亮 / `html.dark` 暗，RGB 三元组支持透明度）
- 玻璃拟态 `.card`（backdrop-filter + `@supports not` 降级实体卡片）
- 新拟态 `.neu/.neu-inset/.neu-btn`（WCAG AA 对比度文字色）
- `prefers-reduced-motion: reduce` 全局动画降级
- 法域色系（中红/日洋红/韩青/新琥珀）走 CSS 变量，图谱画布动态取色跟随主题
