# Evaluation — Golden Set 与回归测试矩阵

> [English](../README.md) | [简体中文](../README.zh-CN.md) | [日本語](../README.ja.md) | [한국어](../README.ko.md)

> 评测是 EXCLUSLAWYER 的质量门禁：换 prompt、换模型、换 embedding，跑一遍 Golden Set，
> 四大指标任一不达标即失败。本文记录评测标准、**0% 幻觉率的验证方法**与全量回归矩阵。

---

## 1. Golden Set（100 条）

### 1.1 用例构成

`backend/data/golden_set.json`，100 条典型问答对，按行为分四层：

| 层 | 条数 | 行为断言 |
| --- | --- | --- |
| 应引法条 | 66 | 期望法条必须被召回 + 必含/禁含关键词 |
| 证据不足 | 15 | 明示「证据不足」且 **零引用** |
| 拒答 | 10 | 拒绝输出并引导执业律师 |
| 注入拦截 | 9 | 越狱模板拦截，`detail` 标注命中规则 |

Schema：

```json
{
  "id": "G-001",
  "category": "contract",
  "question": "……",
  "expect": {
    "behavior": "answer | insufficient | refusal | injection",
    "statute_ids": ["CN-MINFA-577"],
    "must_contain": ["违约责任"],
    "must_not_contain": ["编造"]
  }
}
```

### 1.2 四大指标与门槛

| 指标 | 定义 | 门槛 | 当前值 |
| --- | --- | --- | --- |
| 法条引用准确率 citation_recall | 期望法条被召回的比例 | ≥ 98% | **100%** |
| 结论-依据一致性 consistency | NLI 校验非 degraded 的比例 | ≥ 90% | **100%** |
| 幻觉率 hallucination_rate | 引用了库里不存在的法条/案例 | ≤ 3% | **0%** |
| 时效正确率 timeliness_accuracy | 引用法条时效标注与知识库一致 | ≥ 99% | **100%** |

**100 / 100 全部通过。** 门禁落在 `tests/test_golden.py`，CI 跑 pytest 即回归。

### 1.3 运行方式

```bash
cd backend
python -m pytest tests/test_golden.py -q          # 门禁（断言 len==100 + 四指标）
python scripts/golden_regression.py               # 报告：data/golden_report.md
```

`app/eval/golden_runner.py` 为回归引擎：逐条跑 `AskService.ask`，产出 `RegressionReport`
（指标 + 失败清单），`format_report` 渲染 Markdown。

---

## 2. 0% 幻觉率的验证方法

幻觉的工程定义：**引用了知识库中不存在的法条 ID 或案例**。验证分四道防线：

### 2.1 静态全集对照（Golden 层）

```
valid_ids = {s.id for s in load_statutes("data/cn_statutes_sample.json")}   # 17 条种子
# 或官源全集：official_statutes.json 7,054 条
for sid in resp.citations:
    assert sid in valid_ids        # 不存在 → 计入 hallucination
```

指标口径：`hallucination_rate = 幻觉引用数 / 引用总数`。当前 0/全部引用。

### 2.2 挂条阈值「宁缺毋滥」（管线层）

检索相似度 < 0.25 的主张**不挂任何引用**（citations 恒为空数组），上层输出「证据不足」。
弱命中不允许硬凑依据——幻觉在出口前就被结构性消灭。

### 2.3 `_cite_by_id` 单向取数（实现层）

意见书/庭审/裁判的引用全部经 `_cite_by_id(retriever, statute_id)` 从库中读取
（`store.get` + `payload_to_dict`），**不接受模型生成的条文文本**。
LLM 路径的系统词强制 `[CIT-id]` 格式且「只能使用给定清单」，输出侧再校验 ID 存在性。

### 2.4 行为闸门（语义层）

| 行为 | 通过条件 |
| --- | --- |
| `insufficient` | status=insufficient_evidence + 零引用 + 明示「证据不足」 |
| `refusal` / `injection` | 未放行；拦截文案标注命中规则 |
| `grounded` | 期望法条全部召回 + must_contain 命中 + must_not_contain 未出现 |

### 2.5 模拟法庭 Golden（10 条独立集）

`data/golden_set_trial.json` + `app/eval/trial_golden_runner.py`（与主集**互不污染**，
主集 `len(cases)==100` 断言不受影响）：

| 校验项 | 方法 |
| --- | --- |
| 幻觉 | complaint/limitation 的全部 citation_ids ⊆ valid_ids |
| 法条引用准确 | 期望 statute_ids ⊆ 主张 citations（如二倍工资→CN-LDF-82） |
| 时效联动 | 2015 旧案→`expired`+CN-MINFA-188；无日期→`checked=false`；2024 案→checked+CN-MINFA-188 |
| 行为 | grounded / insufficient（库外案由如南极捕鲸配额）/ refusal（注入） |

门禁：`tests/test_golden_trial.py`（behavior 100% + recall ≥98% + 幻觉 ≤3% + 时效 ≥99%）。

---

## 3. 全量回归测试矩阵

### 3.1 后端（pytest）

```
cd backend && python -m pytest tests/ -q
→ 113 passed · 4 skipped（skip = Neo4j Docker 专项，环境未起图库时跳过）
```

| 测试文件 | 覆盖 |
| --- | --- |
| `test_api.py` | /api/ask /retrieve /verify /feedback 接口契约 |
| `test_facts.py` | 事实结构化四类 + 时间线排序 |
| `test_opinion.py` | 五段式意见书 + 对抗六段 + 风险透明 |
| `test_pipeline.py` | 数据管道 + **SG PDF 切分**（TOC/正文/Schedule/对照表/沿革边界、行内 Rule 并入、空置条） |
| `test_retriever.py` | 双后端检索 + 2-gram 质量闸门 + 时效权重 |
| `test_graph.py` | LangGraph 咨询状态机（中断恢复/注入/证据不足/NLI 降级） |
| `test_trial_graph.py` | **庭审状态机 13 项**：全流程/双视角/溯源/证据+时效/过期挂起/快照恢复/导出/SSE/400·404 |
| `test_golden.py` | 主 Golden 门禁（100 条 + 四指标） |
| `test_golden_trial.py` | 庭审 Golden 门禁（10 条 + 四指标） |
| `test_kg.py` / `test_kg_neo4j.py` | 图谱快照查询 / Neo4j 真库（Docker，可 skip） |
| `test_p1.py` / `test_p2.py` | 合同类案时效 / 模拟法庭·图谱·计算器·对比 |

### 3.2 前端（vitest）

```
cd frontend && npm test
→ 16 / 16 passed
```

| 测试文件 | 覆盖 |
| --- | --- |
| `consult-graph.test.tsx` | 对话问答 + 状态机咨询面板 |
| `kg-canvas.test.tsx` | KG 图谱面板画布 |
| `panels.test.tsx` | 溯源/事实/意见面板 |
| `theme-toast-byok.test.tsx` | 主题切换 / Toast / BYOK 密钥守卫 |

### 3.3 构建与性能

| 项 | 结果 |
| --- | --- |
| `npm run build` | exit 0 · 0 warnings · `/mock-trial` 首载 100 kB |
| Lighthouse（/mock-trial） | 性能 100 · LCP 1.9 s（门 <2.5 s）· CLS 0（门 <0.1）· TBT 0 ms |

### 3.4 一键回归清单

```bash
cd backend  && python -m pytest tests/ -q          # 113 passed · 4 skipped
cd frontend && npm test && npm run build           # 16/16 + build clean
```

---

## 4. 反馈闭环（Golden Set 持续进化）

1. 前端每条回答下「有用 / 有误 / 引用过时」→ `data/feedback.jsonl`；
2. `python scripts/import_feedback.py` 将「有误/引用过时」样本并入 `data/golden_feedback.json`
   （`needs_review=true`，**不污染已标注指标**）；
3. 人工标注后转正进主 Golden Set，下一轮回归自动覆盖。

> 原则：**指标是门槛不是装饰**。任何 prompt / 模型 / embedding 变更，Golden Set 不过不准合入。
