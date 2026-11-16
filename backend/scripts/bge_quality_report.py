"""BGE-M3 实模型质量验证：hash vs bge_m3 双模式对比。

产出 data/bge_comparison_report.md：
1. 同一套 Golden Set 100 条在两种 embedding 下的四大指标对比
2. 跨语言检索小样（中/日/韩/英查询 → 中文法条）——BGE-M3 的核心卖点验证

用法（backend/ 目录下）：
    python scripts/bge_quality_report.py
模型缓存设到 D 盘（HF_HOME="D:/项目/法律咨询顾问/hf-cache" HF_ENDPOINT=https://hf-mirror.com python scripts/bge_quality_report.py）
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.eval.golden_runner import format_report, load_cases, run_regression  # noqa: E402
from app.rag.embedder import BGEM3Embedder, HashingEmbedder  # noqa: E402
from app.rag.retriever import Retriever  # noqa: E402
from app.rag.vector_store import NumpyVectorStore  # noqa: E402
from app.services.ask_service import AskService  # noqa: E402
from scripts.ingest_cn import ingest_seed  # noqa: E402

# 跨语言小样：查询 → 期望召回的法条（文档库为中文法条原文）
CROSS_LINGUAL = [
    ("zh", "违约赔偿额怎么计算？", "CN-MINFA-584"),
    ("ja", "契約に違反した場合の損害賠償額はどのように計算されますか", "CN-MINFA-584"),
    ("ko", "계약 위반 시 손해배상액은 어떻게 산정됩니까", "CN-MINFA-584"),
    ("en", "How is the amount of damages calculated for breach of contract?", "CN-MINFA-584"),
    ("ja", "労働契約書に署名しない場合、使用者は二倍の賃金を支払うべきですか", "CN-LDF-82"),
    ("en", "What is the limitation period for civil claims?", "CN-MINFA-188"),
]


def build(embedder):
    store = NumpyVectorStore(path=None)
    ingest_seed(embedder, store)
    return AskService(Retriever(embedder, store)), Retriever(embedder, store), store


def cross_lingual_check(retriever) -> list[tuple[str, str, str, list[str], bool]]:
    rows = []
    for lang, q, expected in CROSS_LINGUAL:
        cites = retriever.retrieve(q, top_k=3)
        got = [c.statute_id for c in cites]
        rows.append((lang, q, expected, got, expected in got))
    return rows


def main() -> int:
    golden = BASE_DIR / "data" / "golden_set.json"
    cases = load_cases(golden)

    sections: list[str] = ["# BGE-M3 实模型质量对比报告", ""]
    summaries = {}

    for name, emb in [("hash（词面哈希·兜底）", HashingEmbedder(dim=256)), ("bge_m3（语义·实模型）", BGEM3Embedder())]:
        print(f"=== 运行模式：{name} ===")
        svc, retriever, store = build(emb)
        valid_ids = set(store.payloads)
        report = run_regression(svc, cases, valid_ids)
        summaries[name] = report
        sections += [f"## 模式：{name}", ""]
        sections += format_report(report, mode=name).splitlines()[2:]  # 去掉重复标题
        sections.append("")
        if "bge" in name:
            sections += ["## 跨语言检索小样（查询语言 → 中文法条）", ""]
            sections.append("| 语言 | 查询 | 期望 | 实际召回 top-3 | 判定 |")
            sections.append("| --- | --- | --- | --- | --- |")
            for lang, q, expected, got, ok in cross_lingual_check(retriever):
                sections.append(f"| {lang} | {q[:28]} | {expected} | {', '.join(got)} | {'✅' if ok else '❌'} |")
            sections.append("")

    # 汇总对比
    h = summaries["hash（词面哈希·兜底）"].metrics
    b = summaries["bge_m3（语义·实模型）"].metrics
    summary = [
        "## 双模式对比速览",
        "",
        "| 指标 | hash 兜底 | bge_m3 实模型 |",
        "| --- | --- | --- |",
        f"| 法条引用准确率 | {h['citation_recall']:.2%} | {b['citation_recall']:.2%} |",
        f"| 结论-依据一致性 | {h['consistency']:.2%} | {b['consistency']:.2%} |",
        f"| 幻觉率 | {h['hallucination_rate']:.2%} | {b['hallucination_rate']:.2%} |",
        f"| 时效正确率 | {h['timeliness_accuracy']:.2%} | {b['timeliness_accuracy']:.2%} |",
    ]
    sections = sections[:2] + summary + [""] + sections[2:]

    out = BASE_DIR / "data" / "bge_comparison_report.md"
    out.write_text("\n".join(sections), encoding="utf-8")
    print("\n".join(summary))
    print(f"\n报告已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
