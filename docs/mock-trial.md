# Mock Trial — LangGraph 庭审状态机

> [English](../README.md) | [简体中文](../README.zh-CN.md) | [日本語](../README.ja.md) | [한국어](../README.ko.md)

> 模拟法庭是 EXCLUSLAWYER 的对抗推理中枢：把「主张 → 挂条 → 质证 → 辩论 → 裁判」
> 建模为显式状态机，每个环节可中断、可恢复、可导出、可回归。
> 前端入口：`/mock-trial`（六分区工作台，SSE 流式渲染）。

---

## 1. 状态机总览

```
START
  │
  ▼
create_case ──── 注入命中 ──────────────▶ end_refused（拒答短路）
  │ ok
  ▼
fix_facts            事实固定 + 法官争议焦点归纳
  │
  ▼
file_complaint ── 全部主张无据 ────────▶ end_insufficient（证据不足短路）
  │ 至少一项 grounded
  ▼
evidence_review      举证质证 + 时效联动（铁律 ③）
  │
  ├─(时效 expired 且 interrupt_on_limitation)─▶ human_confirm ──reject─▶ end_insufficient
  │                                                   │ approve
  ▼                                                   ▼
debate ◀────────────── 轮次 < N 循环 ───────────────┘
  │  （每轮 interrupt 等待发言 → 对方反驳 → 法官评析）
  │  轮次 = N（默认 3）
  ▼
closing              interrupt 等待总结陈词 + 法官立场小结
  │
  ▼
adjudicate           模拟裁判（强制免责 + 逐条溯源）
  │
  ▼
 END(status=done)
```

阶段字面量（`TrialPhase`）：`create_case / fix_facts / file_complaint / evidence_review / debate / closing / adjudicate`。
用户视角的四幕：**争点锁定 → 举证质证 → 双视角辩论 → 裁判输出**。

---

## 2. 各节点职责

### 2.1 create_case —— 立案与注入检测

对案情、主张、证据全部文本跑 `scan_untrusted`，**任一命中即拒答短路**（`status=refused`），
不进检索、不进诉状。trace 记录 `create_case(refused)`。

### 2.2 fix_facts —— 争点锁定

- `structure_facts`：叙事 → 结构化事实（confirmed / to_verify / assumption / claim 四类 + 时间线）。
- `_detect_topic` 识别案由（劳动 / 合同 / 侵权），法官节点输出**争议焦点归纳**（案由焦点 + 「诉讼/仲裁时效」必列），
  后续辩论、裁判均围绕焦点展开。

### 2.3 file_complaint —— 提交诉状（铁律 ①②）

逐项主张 `retriever.retrieve` 挂条，三级阈值判定支撑度：

| top 得分 | support | 处理 |
| --- | --- | --- |
| ≥ 0.35 | `supported` | 挂 citations + 法律风险 |
| ≥ 0.25 | `partial` | 挂 citations（证据力打折） |
| < 0.25 / 0 命中 | `insufficient` | **citations 恒为空**，标注证据不足 |

同时生成**对方律师视角**（铁律 ②）：
- `_fact_holes`：事实漏洞（待核实/假设事实、诉求缺确认事实支撑、按案由弱点、程序时效管辖抗辩）；
- `_legal_risks`：按案由**定向检索**（「诉讼时效期间」「违约金过分高于造成的损失」…），
  **命中才引用真实条文**，格式 `【法律风险】对方可援引 [ID] 标题条号：原文…`，不命中不编造；
- `opposition_summary`：对方律师总述（序号连续不重复）。

全程无任何 grounded 主张 → `status=insufficient_evidence` 短路，**不出具裁判**。

### 2.4 evidence_review —— 举证质证 + 时效联动

**证据校验**（每份证据三个维度）：

| 维度 | 方法 |
| --- | --- |
| 要件匹配 | 案由要件模板 `_ELEMENTS` + 字符 2-gram 重叠（≥2 要件=strong / 1=partial / 0=weak） |
| 证明力 | 类型基准矩阵：鉴定意见/书证=strong，物证/电子数据=medium，证人证言/当事人陈述=weak；带瑕疵降一级 |
| 证据瑕疵 | 复印件截图、电子数据未固定、无来源说明、模糊时间（「去年/最近」）、灭失风险 |

**时效联动**（铁律 ③）：
1. `_parse_date` 三级正则取最早日期（`YYYY年M月D日` → `YYYY年M月` → `YYYY年`）；
2. `limitation_check`（普通 3 年时效，民法典第一百八十八条）输出起算日 / 届满日 / 结论；
3. 风险分级：`expired`（已届满）/ `warning`（≤180 天或含中断提示）/ `safe` / `unknown`（无时间要素）；
4. 挂载 CN-MINFA-188（`_cite_by_id` 只取真实存在），检索兜底用「诉讼时效期间」查询。

### 2.5 debate —— 双视角辩论（interrupt 驱动）

每轮执行一次，天然承载用户交互：

```
interrupt({phase:"debate", round, prompt})  ── 等待发言
        │ resume(statement)
        ▼
用户 TrialTurn ──▶ 对方律师反驳 ──▶（未满 N 轮）法官评析
```

对方反驳双路径：
- **LLM 路径**（`LLMConfig.from_settings().available`）：系统词「只围绕证据、时效、因果关系、
  可预见性、过错相抵、程序抗辩；引用法条只能用给定清单 [CIT-id]，绝不编造」；
- **规则路径**（无 LLM 兜底）：合并 claim holes/risks + 证据瑕疵 + 时效抗辩，**引用仅限已挂载法条**。

### 2.6 human_confirm —— 时效风险人工确认

仅在 `interrupt_on_limitation=True` 且时效 `expired` 时挂起：
`approve` 继续审理 / `reject` 终止推演（`status=insufficient_evidence`）。

### 2.7 closing → adjudicate —— 裁判输出

**强制前置免责**（`TRIAL_DISCLAIMER`）：

> 【仅法律推演，不具备法律效力，不可用于真实诉讼，请咨询执业律师】

`verdict.overall` 以该句**开头**，`disclaimer` 字段独立携带，UI 卡片红色置顶——三层冗余防漏渲。

**逐条裁决规则**：

| 条件 | 裁决 |
| --- | --- |
| `support=insufficient` | 驳回（理由挂「证据不足」+ 对方抗辩成立） |
| 时效 `expired` | 部分支持（时效抗辩理由） |
| `support=partial` 或平均证明力 < 1.0 | 部分支持（举证补强） |
| 其余 | 支持 |

每条理由后附 `[ID] 标题条号：原文…`（**法条溯源**）+ KG 判例参考 + Compare 跨法域对照引用。
NLI 校验（`nli_check`）对小结做词面蕴含检查，**不阻断输出**，`degraded` 如实标注。

---

## 3. Checkpointer 状态持久化

中断恢复是庭审交互的地基，双层持久化：

| 层 | 载体 | 职责 |
| --- | --- | --- |
| LangGraph checkpoint | `SqliteSaver`（`data/trial_checkpoints.sqlite`） | 跨进程/重启的 interrupt/resume |
| 会话快照 | `data/trial_sessions/{id}.json`（原子写 tmp+replace） | UI 刷新恢复、导出、审计 |

- **序列化**：`JsonPlusSerializer(allowed_msgpack_modules=[("app.models.schemas", T), …])`
  注册 17 个 pydantic 类型（TrialClaim/TrialComplaint/EvidenceReview/LimitationRisk/TrialTurn/TrialVerdict…），
  消除 msgpack「unregistered type」告警（未来版本将封禁未注册类型）。
- **中断/恢复协议**：
  - 挂起：`interrupt(value)` → 响应 `interrupted=true, status=awaiting_input, pending=prompt`；
  - 恢复：`Command(resume=statement | closing | decision)`，`"__interrupt__" in result` 判定是否继续挂起；
  - 每个会话 `thread_id` = session_id，快照含 `snapshot.next` 信息。
- **无 checkpointer 兜底**：路由层现场编译 MemorySaver 版（测试/无 lifespan 场景）。

---

## 4. TrialExportSchema 导出规范

### 4.1 会话快照 Schema（`TrialGraphResponse`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` | str | 会话 ID（`^[A-Za-z0-9_-]{1,64}$`，防路径穿越） |
| `phase` | str | 当前阶段（挂起时取 interrupt 的 phase） |
| `status` | enum | `refused / insufficient_evidence / awaiting_input / done` |
| `pending` | str | 待用户输入提示 |
| `trace` | str[] | 全链路节点轨迹（`debate(round=2)` 等） |
| `facts` | FactSet | 结构化事实 + 时间线 |
| `complaint` | TrialComplaint | 主张（含 support/holes/risks/citations）+ 对方律师视角 |
| `evidence_reviews` | EvidenceReview[] | 要件匹配 / 证明力 / 瑕疵 |
| `limitation` | LimitationRisk | 时效联动结果（risk_level / key_date / deadline / citations） |
| `debate_turns` | TrialTurn[] | 辩论记录（user / opponent / judge，追加式） |
| `closing_text` | str | 总结陈词 |
| `verdict` | TrialVerdict | 裁判（disclaimer 前置） |
| `events` | TrialEvent[] | 滚动庭审记录（phase/kind/role/title/content/citation_ids） |
| `disclaimers` | str[] | 固定含 TRIAL_DISCLAIMER |

### 4.2 Markdown 导出（`GET /api/trial/session/{id}/export.md`）

九节结构：案件信息 → 案情 → 事实固定 → 诉状与主张（含双视角）→ 举证质证 → 时效联动 →
法庭辩论 → 总结陈词 → 模拟裁判 → **法条引用清单表**（含 `source_url` 链接）。
文末再次附 TRIAL_DISCLAIMER。`Content-Disposition: attachment`。

### 4.3 PDF 导出（`GET /api/trial/session/{id}/export.pdf`）

reportlab `SimpleDocTemplate`（A4）+ `UnicodeCIDFont("STSong-Light")`（中文无需字体文件）。
Markdown 同源逐行渲染：`#`→标题、`>`→引注色引用、`|`→表格行、`-`→列表。

---

## 5. SSE 流式协议（`POST /api/trial/graph/stream`）

POST + `text/event-stream`（EventSource 不支持 POST，前端 fetch 流解析）。
请求体同 start/step；**预校验**在流前返回 4xx（不进流）。

| 事件 | 载荷 | 时机 |
| --- | --- | --- |
| `open` | `{session_id}` | 连接建立 |
| `phase` | `{node, trace[]}` | 每节点完成 |
| `event` | TrialEvent | 庭审记录逐条 |
| `turn` | TrialTurn | 辩论发言逐条 |
| `verdict` | TrialVerdict | 裁判产出 |
| `done` | TrialGraphResponse | 终态/挂起，完整快照（随后落盘） |
| `error` | `{error}` | 流内错误 |

## 6. API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/trial/graph/start` | 开庭（至辩论挂起或终态短路） |
| POST | `/api/trial/graph/step` | 推进（statement / closing / decision 三选一） |
| POST | `/api/trial/graph/stream` | 同上，SSE 流式 |
| GET | `/api/trial/session/{id}` | 会话快照（刷新/重启恢复） |
| GET | `/api/trial/session/{id}/export.md` | Markdown 全记录 |
| GET | `/api/trial/session/{id}/export.pdf` | PDF 全记录 |
| POST | `/api/trial/start` · `/api/trial/turn` | 旧轮次制（兼容保留） |
