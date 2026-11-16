# Mock Court — 模拟法庭状态机设计说明

> [English](../README.md) | [简体中文](../README.zh-CN.md) | [日本語](../README.ja.md) | [한국어](../README.ko.md)
>
> 任务③交付文档。本文描述模拟法庭（LangGraph 庭审状态机）的阶段流转、API 路由形态与关键机制；
> 深度实现细节（checkpointer 序列化、SSE 分帧、导出 Schema 全字段）见 [mock-trial.md](mock-trial.md)。

---

## 1. 状态机总览

代码落点：`backend/app/graph/trial_build.py`（图装配）· `trial_nodes.py`（节点）· `trial_state.py`（状态）·
`backend/app/services/trial_flow_service.py`（规则引擎）。

```
START
  │
  ▼
create_case ──── 注入命中 ──────────────────▶ end_refused（拒答短路）
  │
  ▼
fix_facts
  │
  ▼
file_complaint（三级挂条阈值：supported / partial / insufficient）
  │
  ▼
evidence_review（要件匹配 + 证明力 + 瑕疵 + 时效联动）
  │
  ├─ interrupt_on_limitation 且时效高风险 ─▶ human_confirm（interrupt 挂起）
  │                                            │ approve        │ reject
  │                                            ▼                ▼
  │                                          debate          end（终止，不出裁决）
  │                                            │
  ▼                                            │
debate ◀──── debate_round < max_rounds（默认 3 轮 × 双方）────┘
  │（每轮 interrupt 驱动：statement 逐方发言）
  ▼
closing（总结陈词，interrupt 驱动：closing 输入）
  │
  ▼
adjudicate（模拟裁判 → 终态 done / insufficient_evidence）
  │
  ▼
END（会话快照落盘 data/trial_sessions/{id}.json）
```

**七个阶段**（`TrialPhase`）：`create_case`（案件创建）→ `fix_facts`（事实固定）→ `file_complaint`（诉状）→
`evidence_review`（举证质证）→ `debate`（法庭辩论，最多 3 轮）→ `closing`（总结陈词）→ `adjudicate`（模拟裁判）。

- **人工决策点**：`human_confirm`（时效过期挂起）与 debate/closing 的逐轮输入均走 LangGraph `interrupt()`；
  恢复用 `Command(resume=...)`，结果含 `"__interrupt__"` 即为挂起。
- **短路**：create_case 注入扫描命中 → `end_refused`；主张全部 insufficient 且无任何法条命中 →
  `adjudicate` 直接以 `insufficient_evidence` 终态（裁决仍出，对应主张逐条"驳回·证据不足"）。
- **持久化**：`SqliteSaver`（`data/trial_checkpoints.sqlite`，跨重启恢复图状态）+ 会话快照 JSON（原子写，
  ID 白名单 `^[A-Za-z0-9_\-]{1,64}$`）。前端刷新后可凭 `session_id` 恢复。

## 2. Trial 路由清单（8 条）

P3 状态机 6 条（`backend/app/api/trial_routes.py`）+ P2 轮次制 2 条（`backend/app/api/routes.py`）。

### 2.1 P3 状态机（`/api/trial`，响应均为 `TrialGraphResponse` 会话快照）

| # | 方法 · 路径 | 请求体 | 说明 |
| --- | --- | --- | --- |
| 1 | `POST /api/trial/graph/start` | `TrialGraphStartRequest` | 启动庭审，从 create_case 跑到首个待输入点或终态 |
| 2 | `POST /api/trial/graph/step` | `TrialGraphStepRequest` | 推进一步 / 恢复 interrupt（发言、陈词、人工裁决） |
| 3 | `POST /api/trial/graph/stream` | start 或 step 形态（dict） | SSE 流式执行：`event: open/phase/event/turn/verdict/done/error` |
| 4 | `GET /api/trial/session/{session_id}` | — | 取会话快照（404 = 不存在） |
| 5 | `GET /api/trial/session/{session_id}/export.md` | — | 导出庭审记录 Markdown（text/plain） |
| 6 | `GET /api/trial/session/{session_id}/export.pdf` | — | 导出庭审记录 PDF（application/pdf，`%PDF-` 头） |

**请求形态**（`app/models/schemas.py`）：

```jsonc
// TrialGraphStartRequest
{
  "case_description": "……（1~8000 字）",
  "user_role": "plaintiff | defendant",
  "jurisdiction": "CN | JP | KR | SG",
  "language": "zh",
  "top_k": 5,
  "claims":     [{ "text": "主张内容", "relief": "诉求" }],
  "evidences":  [{ "title": "证据名称", "evidence_type": "书证", "description": "…（含日期）" }],
  "interrupt_on_limitation": false,   // 时效高风险时挂起人工确认
  "session_id": null                   // 可选：复用既有会话
}

// TrialGraphStepRequest（三选一驱动 interrupt 恢复）
{
  "session_id": "…",
  "statement": "辩论发言（debate 阶段）",
  "closing":   "总结陈词（closing 阶段）",
  "decision":  "approve | reject（human_confirm 人工裁决）"
}
```

**响应形态**（`TrialGraphResponse` 会话快照，start/step/get 三接口同构）：

```jsonc
{
  "session_id": "…",
  "phase": "create_case | fix_facts | … | adjudicate",
  "status": "refused | insufficient_evidence | awaiting_input | done",
  "pending": "下一步待用户输入的提示（awaiting_input 时）",
  "interrupted": false,               // true = 停在 interrupt 等待 step 恢复
  "trace": ["create_case(ok)", "…"],
  "facts": { … }, "complaint": { … }, "evidence_reviews": [ … ],
  "limitation": { … }, "debate_turns": [ … ], "closing_text": "…",
  "verdict": { … },                   // adjudicate 后填充
  "events": [ … ],                    // 滚动庭审记录
  "disclaimers": ["【仅法律推演…】"]
}
```

**校验口径**：start 缺 `case_description` → 422；step 语句为空/`resume` 值非法 → 400；session 不存在 → 404。
`graph/stream` 预校验同口径（错误以 `event: error` 帧返回），非 dict 的 `__interrupt__` chunk 自动跳过。

### 2.2 P2 轮次制（保留兼容，`/api/trial` 前缀同一）

| # | 方法 · 路径 | 请求/响应 | 说明 |
| --- | --- | --- | --- |
| 7 | `POST /api/trial/start` | `TrialStartRequest` → `TrialSession` | 旧版轮次制开庭（fact_set + 双视角摘要） |
| 8 | `POST /api/trial/turn` | `TrialTurnRequest` → `TrialSession` | 旧版逐轮发言（round-based） |

> P2 两条为 P3 状态机落地前的轮次制接口，测试覆盖于 `tests/test_p2.py`，暂保留兼容；
> 前端入口已全部切换至 P3（旧版 `TrialView.tsx` 已确认无引用后移除）。

## 3. 关键机制

### 3.1 双视角对抗（铁律 2）

- `file_complaint` 阶段对每项主张生成对方律师视角漏洞 `holes`，并输出 `opposition_summary`
  （固定前缀"【法律风险】"，要点带序号，只引用真实检索到的法条 ID）。
- `debate` 阶段 opponent 角色继续攻击、judge 角色归纳争点；全部发言进 `debate_turns`（role=user/opponent/judge）。

### 3.2 证据要件校验

`review_evidences`（规则引擎）对每份证据产出 `EvidenceReview`：

- **要件匹配**：按案由要件模板（合同/劳动/侵权/general，`_ELEMENTS`）与证据描述词面匹配 →
  `element_match: strong/partial/weak` + `target_elements`；
- **证明力**：`probative_strength: strong/medium/weak`（书证原件强、复印件/单方陈述降档）；
- **瑕疵识别**：`_evidence_defects`（复印件、无原件、单方制作、日期缺失等）→ `defects` 列表。

### 3.3 时效联动（铁律 3）

`_limitation_link` 串联证据日期 → `limitation_check`（默认 3 年普通时效，CN-MINFA-188）→ `LimitationRisk`：

- `risk_level`：`expired`（"已…届满"）/ `warning`（"仅剩|中断"）/ `safe` / `unknown`（无日期 → `checked=false`）；
- 裁决联动：expired → 相应主张"部分支持"并在 `risk_notes` 出"时效联动提示"；
- 跨法域对照按案由过滤（2026-11 修复）：`CompareService.compare(..., causes=[…])` 排除与当前案由
  无关的时效条目（如合同案件混入劳动仲裁时效条目），"通用"时效条目保留。

### 3.4 过期挂起（interrupt_on_limitation）

1. `evidence_review` 后检测：`interrupt_on_limitation=true` 且 `risk_level=expired` → 进入 `human_confirm`；
2. 图执行挂起（`interrupt()`），`TrialGraphResponse.interrupted=true`，`pending` 提示人工裁决；
3. `POST /graph/step` 传 `decision`：`approve` → 继续 debate；`reject` → 终止（status 不出 done，
   会话标记被驳回，不产出裁决书）；
4. 无挂起场景（默认）直接进入 debate。

### 3.5 模拟裁判

裁决规则（`build_verdict`，逐主张）：

| 情形 | 结论 |
| --- | --- |
| support=insufficient（未挂现行法条） | 驳回（理由=证据不足 + 对方抗辩成立） |
| 时效 expired | 部分支持（时效风险提示） |
| support=partial 或平均证明力 < medium | 部分支持（补强举证建议） |
| 其余（supported + 证明力强） | 支持 |

- **小结要件复述**（2026-11 引入）：overall 强制 `TRIAL_DISCLAIMER` 前置 + 计数小结 + 裁判要件复述段
  （复述所引法条关键要件与关键词，提升结论-依据一致性）；
- **NLI 校验**：对小结执行 `nli_check`（与主链路口径一致）；**不通过仍标注"证据不足"降级警示并进
  `risk_notes`，不得静默放行**（降级分支保留，不阻断输出）；
- 逐条 `TrialVerdictItem` 挂 `citation_ids / case_refs / cross_refs`（判例参考与跨法域对照按案由过滤后引用）。

## 4. 记录导出流程（Markdown / PDF）

代码落点：`backend/app/services/trial_export_service.py`。导出以会话快照 record 为唯一数据源，零外呼。

**Markdown（`to_markdown`，九节）**：

1. 案件信息（角色/法域/案情）
2. 事实固定（事实清单 + 时间线）
3. 诉状与主张（含双视角对抗：holes / opposition_summary）
4. 举证质证（证据 → 要件匹配/证明力/瑕疵）
5. 时效联动（key_date / deadline / risk_level / calc_items）
6. 法庭辩论（逐轮 user/opponent/judge）
7. 总结陈词
8. 模拟裁判（逐条结论 + 理由 + 引用；小结强制免责声明前置）
9. 法条引用清单（全量去重，含 statute_id / 出处链接）

**PDF（`to_pdf_bytes`）**：同一 MD 结构经 reportlab 重排；中文用内置 CID 字体 `STSong-Light`
（无需字体文件，CJK 直出）；标题层级（#/##/###）映射为字号阶梯；输出校验 `%PDF-` 头。

前端 `/mock-trial` 工作台裁决面板内一键导出（`trialExportLinks` → 两个 GET 直链）。

## 5. 回归与测试

- `tests/test_trial_graph.py`（11 例）：全链路裁决、双视角、挂条阈值、insufficient 短路、注入拒答、
  举证/时效、expired 挂起-reject 终止、approve 恢复、会话快照/恢复 404、MD/PDF 导出、SSE 流式；
- `tests/test_golden_trial.py` + `data/golden_set_trial.json`（10 例）：行为闸门 + 引用召回 ≥98% +
  幻觉 ≤3% + 时效准确率 ≥99%（支持 `checked:false` 期望）；
- `tests/test_verdict_nli.py`（2 例，2026-11 新增）：小结复述法条关键词后通过 NLI、降级必须标注证据不足；
- 全量回归矩阵与指标见 [regression-report.md](regression-report.md)；已知限制见 [known-issues.md](known-issues.md)。
