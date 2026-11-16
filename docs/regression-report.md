# Regression Report — 任务③模拟法庭深化迭代回归验证报告

> [English](../README.md) | [简体中文](../README.zh-CN.md) | [日本語](../README.ja.md) | [한국어](../README.ko.md)
>
> 生成时间：2026-11-16 · 环境：Windows 11 / Python 3.13.12 / Node（Next.js 14）
> 测试解释器：`C:/Users/ZTL/.workbuddy/binaries/python/versions/3.13.12/python.exe`

---

## 1. 结论速览

| 项目 | 结果 | 判定 |
| --- | --- | --- |
| 后端全量（pytest） | **113 passed · 4 skipped · 0 failed**（117 collected） | ✅ |
| 前端全量（vitest） | **16 / 16** | ✅ |
| #42 模拟法庭路由回归（test_trial_graph.py） | **11 / 11** | ✅ |
| Golden Set 主集（100 条） | 未破坏，四指标达标 | ✅ |
| 庭审 Golden Set（10 例） | 行为闸门 + 四指标达标 | ✅ |
| 生产构建（next build） | **exit 0 · 0 警告** | ✅ |
| tsc --noEmit（TrialView 移除后） | 0 错误 | ✅ |
| Lighthouse（/mock-trial） | 100 分 · LCP 1.9 s · CLS 0 · TBT 0 ms | ✅ |
| INP | 无交互样本 N/A，**待真实交互复测** | ⚠️ 不阻断 |

> 备注：任务③收尾核对基线为 pytest 108 passed；本次遗留项处理新增 5 例回归用例
> （`test_verdict_nli.py` 2 例 + `test_p2.py` compare 案由过滤 3 例）→ 现值 113 passed。
> 收尾核对记录的 "#42 13/13" 为断言口径手记，测试集合实测为 **11 例**（collect-only 确认），全部通过。

## 2. 后端回归矩阵（pytest，16.3 s 全量）

| 测试文件 | 用例数 | 结果 | 覆盖范围 |
| --- | --- | --- | --- |
| test_p2.py | 20 | ✅ | 时效计算器、多法域对比（含 3 例案由过滤新增）、P2 轮次制庭审 |
| test_pipeline.py | 16 | ✅ | 官源数据管道、SG PDF 切分、归一化 |
| test_p1.py | 15 | ✅ | 检索/引用/校验主链路、BYOK 演示模式 |
| test_kg.py | 12 | ✅ | 知识图谱查询、ANALOGOUS_TO 对照、快照回退 |
| test_trial_graph.py | 11 | ✅ | #42 庭审状态机：全链路裁决/双视角/挂条阈值/时效挂起/会话恢复/导出/SSE |
| test_graph.py | 9 | ✅ | 咨询状态机（LangGraph consult）、NLI 降级节点、interrupt/resume |
| test_opinion.py | 7 | ✅ | 五段式意见书、对抗视角 |
| test_api.py | 7 | ✅ | REST 路由契约、注入防护、错误码 |
| test_facts.py | 6 | ✅ | 事实结构化、时间线 |
| test_retriever.py | 4 | ✅ | 2-gram 闸门、STATUS_WEIGHT、reranker 回退 |
| test_kg_neo4j.py | 4 | ⏭️ skipped | Neo4j 真库验证（需 `docker compose up -d neo4j`，CI 默认跳过） |
| test_verdict_nli.py | 2 | ✅ | **新增**：小结要件复述通过 NLI / 降级标注证据不足不静默 |
| test_golden_trial.py | 2 | ✅ | 庭审 Golden 10 例指标闸门 + 与主集独立性 |
| test_golden.py | 2 | ✅ | 主集 Golden 100 条四指标闸门 |

关键命令复现：

```bash
cd backend
python -m pytest tests/ -q          # 113 passed, 4 skipped
python -m pytest tests/test_trial_graph.py -q   # 11 passed
```

## 3. Golden Set 指标

**主集 `data/golden_set.json`（100 条：66 应引 + 15 证据不足 + 10 拒答 + 9 注入）**

| 指标 | 结果 | 门槛 |
| --- | --- | --- |
| 行为闸门（refusal/insufficient/grounded） | 100 / 100 | 全通过 |
| 引用召回 citation_recall | 100 % | ≥ 98 % |
| 幻觉率 hallucination_rate | **0 %** | ≤ 3 % |
| 结论-证据一致性（NLI 非 degraded 比例） | 100 % | ≥ 90 % |
| 时效判定准确率 timeliness_accuracy | 100 % | ≥ 99 % |

**庭审集 `data/golden_set_trial.json`（10 例：grounded 4 / insufficient 2 / refusal 1 / limitation 3）**

- 行为闸门全过；citation_recall ≥ 0.98、hallucination ≤ 0.03、timeliness ≥ 0.99；
- limitation 用例支持 `checked: false` 期望（如"去年"相对时间不锁 risk_level，防时间漂移）。

## 4. 前端回归（vitest 16/16 + 构建）

| 测试文件 | 用例 | 覆盖 |
| --- | --- | --- |
| src/test/consult-graph.test.tsx | 4 | 咨询状态机交互、中断恢复 |
| src/test/kg-canvas.test.tsx | 4 | 图谱画布渲染、节点点击 |
| src/test/panels.test.tsx | 4 | 引用面板/事实面板/裁决卡片 |
| src/test/theme-toast-byok.test.tsx | 4 | 双主题、Toast、BYOK 设置 |

- `next build`：exit 0，**0 警告**；`/mock-trial` 路由 chunk 2.95 kB / First Load 100 kB；
- `npx tsc --noEmit`：0 错误（含旧版 TrialView.tsx 移除后无悬空引用）。

## 5. 性能（Lighthouse 12 · /mock-trial）

| 指标 | 结果 | 预算 |
| --- | --- | --- |
| Performance | 100 | — |
| LCP | **1.9 s** | < 2.5 s ✅ |
| CLS | **0** | < 0.1 ✅ |
| TBT | 0 ms | — |
| INP | N/A（无交互样本） | < 200 ms ⚠️ 待真实交互复测 |

## 6. 覆盖范围说明

**已覆盖**：检索主链路（含闸门/权重/回退）、LangGraph 咨询与庭审双状态机（含 interrupt/resume/短路）、
SSE 流式协议、会话快照/恢复、MD/PDF 导出、时效联动与过期挂起、双视角对抗、注入拒答、
BYOK fail-closed、跨法域对比（含案由过滤）、KG 查询与快照回退、Golden Set 双集指标闸门、前端五类组件。

**未覆盖 / 已知限制**（详见 [known-issues.md](known-issues.md)）：

- NLI P0 为词面重叠启发式，非语义蕴含模型（P1 WIP）；
- Lighthouse INP 需真实交互样本复测；
- test_kg_neo4j 依赖 Docker Neo4j，CI 默认 skip；
- P2 轮次制 `/api/trial/start|turn` 与 P3 状态机并存（兼容保留）；
- 外法域（JP/KR/SG）对比条目为概要种子，标注"需官源核对"。
