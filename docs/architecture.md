# System Architecture

> [English](../README.md) | [简体中文](../README.zh-CN.md) | [日本語](../README.ja.md) | [한국어](../README.ko.md)

> EXCLUSLAWYER 系统架构详解。阅读前置：根目录 [README](../README.md)。
> 本文聚焦三件事：**双后端向量检索**、**法律知识图谱**、**官源数据管道与 PDF 清洗**（以新加坡 SGA 1979 为典型案例）。

---

## 1. 分层总览

```
Frontend (Next.js 14)
   │  REST + SSE
Gateway (FastAPI) ── 注入扫描 · untrusted_data 包裹 · BYOK 防泄露断言
   │
推理核心
   ├─ LangGraph 状态机（consult 咨询机 / trial 庭审机，interrupt/resume）
   ├─ RAG 核心（BGE-M3 嵌入 → 检索 → 重排 → 质量闸门 → NLI 校验）
   └─ 知识与计算（Neo4j 图谱 · 时效/赔偿计算器 · 多法域对比 · 导出）
   │
数据面（Milvus Lite / Milvus Standalone / NumPy · official_statutes.json · golden set）
```

设计原则与四大铁律一一对应：

| 铁律 | 架构落点 |
| --- | --- |
| ① 结论必挂现行法条原文 | RAG 检索结果是唯一引用来源；`_cite_by_id` 只从库里取真实存在的条文；检索不足 → `insufficient evidence` |
| ② 双视角对抗 | 事实漏洞 `_fact_holes` + 法律风险 `_legal_risks`（定向检索**命中才引用**）；庭审机的对方律师节点 |
| ③ 时效感知 | `status`/`effective_date`/`amended_history` 入库；`STATUS_WEIGHT` 加权；修订 diff 时间线 |
| ④ 多法域可比 | 数据模型 `jurisdiction/language` 字段全预留；Compare 服务按主题横向对照 |

---

## 2. 双后端向量检索

### 2.1 后端选择

| 后端 | 用途 | 实现 |
| --- | --- | --- |
| **Milvus Lite** | 默认开发/单机生产（`VECTOR_STORE=milvus_lite`） | 本地文件 `data/milvus_lite.db`，零外部依赖 |
| **Milvus Standalone** | 生产集群（`docker compose --profile full`） | etcd + MinIO + Milvus，`MILVUS_URI` 切换 |
| **NumpyVectorStore** | 测试/离线/CI（`VECTOR_STORE=numpy`） | 纯 numpy 点积检索，内存态，可选落盘 |

三者实现同一接口（`upsert / search / count / get`），检索层 `Retriever` 无感切换。
Golden Set 与全量 pytest 均跑 **HashingEmbedder(dim=128) + NumpyVectorStore** 组合——确定性、零网络、秒级回归；生产语义质量由 BGE-M3 组合保证。

### 2.2 嵌入与重排

- **Embedding：BGE-M3**（中/日/韩/英跨语言，覆盖四法域语料）。模型缓存于 HF_HOME（用户指定路径），支持 `HF_ENDPOINT` 镜像与 `HF_HUB_DISABLE_XET=1`。
- **Rerank：bge-reranker-v2-m3**。网络不可用（HF 502 等）时**自动退回向量相似度排序**并记录日志——重排是增强项不是可用性单点。
- 测试 conftest 全局 `settings.reranker="none"`，避免每个 Retriever 首检索都等 HF 超时（否则全量测试从 ~3.5s 拖到 ~257s）。

### 2.3 检索质量闸门（防幻觉第一道防线）

法条入库与检索共用一套**字符 2-gram 重叠率**闸门：

- 主闸门：查询与条文的字符 2-gram 重叠率 **≥ 0.08** 才允许召回；
- 语义豁免：嵌入相似度 **≥ 0.35** 可豁免主闸门（语义命中但字面差异大）；
- 两级豁免都过不了 → 该条不进引用清单 → 上层输出「证据不足」。

**时效权重**（检索排序加权）：

| 状态 | 权重 |
| --- | --- |
| `effective`（现行） | 1.0 |
| `amended`（已修订） | 0.85 |
| `unknown`（时效不明） | 0.7 |
| `repealed`（已废止） | 0.3 |

废止/旧版条文**不删除、降权 + 标注**——保留历史沿革（铁律 ③ 的「修订降权 + 历史」）。

### 2.4 挂条阈值（庭审/意见书统一口径）

| top 得分 | 判定 | 处理 |
| --- | --- | --- |
| ≥ 0.35 | `supported` | 挂引用 |
| ≥ 0.25 | `partial` | 挂引用（证据力打折） |
| < 0.25 | `insufficient` | **不挂引用**，标注「检索相似度过低」 |

宁缺毋滥：`insufficient` 主张的 `citations` 恒为空数组，裁判阶段直接驳回，杜绝「弱命中硬凑依据」。

---

## 3. 法律知识图谱（Neo4j）

### 3.1 双 schema

- **大陆法系子图**：`Concept`（构成要件）—`ELEMENT_OF`→ `Concept`、`Statute` —`REGULATES`→ `Concept`、`Concept` —`REQUIRES`→ `Concept`，支撑构成要件多跳问答。
- **SG 判例子图**：`Precedent` —`ESTABLISHES`→ `SG-PRIN-*`（注意义务 / 保密义务 / 单方错误 / 电子合同成立 / 算法合同责任），普通法规则经判例锚定。

### 3.2 跨法域类比

`ANALOGOUS_TO` 边连接四法域对应规则，例如：

```
CN-MINFA-577 ↔ JP-415 ↔ KR-390      （违约责任）
CN-MINFA-584 ↔ JP-416 ↔ KR-393      （损失赔偿范围）
CN-MINFA-1165 ↔ JP-709 ↔ KR-750     （过错侵权）
CN-MINFA-563 ↔ JP-541 ↔ KR-543      （合同法定解除）
CN-MINFA-188 ↔ JP-166 ↔ KR-162      （诉讼时效）
```

### 3.3 生产/快照双态

- **Neo4j 真库**：`docker compose --profile full` 拉起，`KG_NEO4J_URI=bolt://localhost:7687`，`tests/test_kg_neo4j.py` 专项验证（需 Docker）。
- **快照回退**：`data/kg/kg_snapshot.json`（55 节点 / 64 边，nodes + edges(src/dst/relation)）。无图库环境自动降级到快照查询，问答链路不中断。

查询接口 `/api/kg/query` 返回 `related_cases`（判例）、`statute_ids`（挂条）与关系路径；模拟法庭的裁判卡片直接消费这两项。

---

## 4. 官源数据管道

**四法域官源**（禁商业库：北大法宝 / Westlaw / LexisNexis 一律不接）：

| 法域 | 源 | 接口要点（实测破译） |
| --- | --- | --- |
| 中国 | flk.npc.gov.cn | `/law-search/search/list` + `download/pc?bbbs=&format=docx`；`sxx`：1=废止 / 2=旧版 / 3=现行 |
| 日本 | e-Gov 法令検索 | `lawdata/{LawId}` XML；附則 = `SupplProvision` 节点 |
| 韩国 | law.go.kr | 正文为 **POST** `lsInfoR.do`（`efYd` 必须取表单 `frm_efYd`）；憲法真名 `대한민국헌법` |
| 新加坡 | sso.agc.gov.sg | AWS WAF 间歇拦截：4xx/202 **不做底层重试**，等冷却后**增量补齐** |

**合并入库**：`scripts/fetch_statutes.py --jur --ingest`
- 空 `--jur` = 不联网，只重建合并 + 灌库（退出码 2 是「抓取成功 0/0」门禁误报，产出正常）。
- 最终 `data/official/official_statutes.json`：**7,054 条**唯一 ID —— CN 2,338 / JP 2,610（含 134 附則）/ KR 1,856 / SG 250（CONS 107 + CRTPA 9 + EmA 71 + SGA 63）。
- 向量灌库 upsert 按 `id` 覆盖，重复入库幂等。

---

## 5. PDF 防断行与污染清洗 —— SGA 1979 案例

新加坡 SGA 1979（Sale of Goods Act 1979）的官方 PDF 是本项目数据管道里最脏的输入，其清洗方案具有普适参考价值。

### 5.1 两种条文式样混排

```
长条式（破折号）：  57.—(1)  Where the seller ...
短条式（行首空格）：  60.  In the case of ...
```

早期正则只匹配破折号式，**漏掉 21 个条号**（6/7/16/18/22–28/33/34/36/40/42/44/54/58–60）；且正文 56 条被末尾「修订对照表」中的同号文本污染——`keep-longer` 去重反而选中对照表的 4,672 字符版本。

### 5.2 清洗流水线（`sg_sso.split_pdf_text`）

1. **行首锚点切条**：`PDF_LINE_RE` 同时识别两种式样，只认**行首**编号——正文内嵌的 `Rule 1.—`（带 `(a)  Rule` 前缀）天然排除。
2. **编号回落切区段**：目录 / SCHEDULE / COMPARATIVE TABLE / LEGISLATIVE HISTORY 各自成段。
3. **正文区定位**：切完后**跨度最大**的区段即正文（排除目录、附表、对照表、沿革）。
4. **末条裁剪**：尾部遇 `THE SCHEDULE` / `COMPARATIVE TABLE` / `LEGISLATIVE HISTORY` 标题行即截断。
5. **完整性校验**：条号 1–63 连续无缺（含 s22 `[Not applicable]`、s40/s58 `[Omitted]` 短条、s63 Short title）。

典型修复结果：s5/s15/s17/s21/s32/s35 各自独立不再吞并；s18 完整保留 Rules 1–5 全文（3,520 字符）；s56 修正为真条文（212 字符）而非对照表残片。

### 5.3 留档与离线重解析

原始 PDF 存档 `data/official/_raw/SGA1979.pdf`（同名 `.txt` 为 layout 文本），解析器升级后可**离线重跑**而不必再次硬闯 WAF。

---

## 6. 安全架构（BYOK）

```
浏览器 localStorage（excluslawyer.byok）
   │  直连 LLM 服务商 /chat/completions
   │
   ├── POST /api/retrieve   （拿法条上下文）
   └── POST /api/verify     （NLI 校验）
后端全程不接触 API Key
```

- **fail-closed 守卫**：任何发往后端的载荷经 `assertNoSecretsToBackend` 断言，含 Key 即抛错阻断（不是静默放行）；报错信息经 `redactSecrets` 打码。
- **注入防护**：用户内容一律 `<untrusted_data>` 包裹与 system prompt 物理隔离；越狱模板分类器（`忽略以上指令` / `DAN mode` / `you are now` …）拦截即拒答。
- **降级诚实**：无 Key = 演示模式（只回摘录原文，不生成自由文本）；无 ML 依赖 = 哈希向量（检索降质但不编造）。所有降级路径都通向「证据不足」而非幻觉。

---

## 7. 配置速查

| 环境变量 | 取值 | 说明 |
| --- | --- | --- |
| `EMBEDDER` | `bge_m3` / `hash` | 生产 / 测试降级 |
| `VECTOR_STORE` | `milvus_lite` / `milvus` / `numpy` | 三后端切换 |
| `MILVUS_URI` | 路径或 URI | Lite 为本地文件 |
| `NEO4J_URI` / `KG_NEO4J_URI` | `bolt://…` | 图谱真库（缺省走快照） |
| `AUTO_INGEST` | `true` / `false` | 启动时种子法条自动入库 |
| `HF_HOME` / `HF_ENDPOINT` | 路径 / 镜像 | 模型缓存与镜像加速 |
