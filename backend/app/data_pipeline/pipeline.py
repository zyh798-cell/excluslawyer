# -*- coding: utf-8 -*-
"""抓取编排：核心法律清单 → fetch → normalize → validate → JSON + 报告。"""
from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

from app.models.schemas import Statute

from .base import FetchSession
from .cn_flk import CnFlkSource
from .jp_egov import JpEgovSource
from .kr_law import KrLawSource
from .normalizer import normalize, validate
from .sg_sso import SgSsoSource

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "official"

# 核心法律清单（官方名称必须与源站完全一致）
CORE_LAWS: dict[str, list[str]] = {
    "CN": [
        "中华人民共和国民法典",
        "中华人民共和国劳动合同法",
        "中华人民共和国劳动法",
        "中华人民共和国刑法",
        "中华人民共和国消费者权益保护法",
        "中华人民共和国民事诉讼法",
    ],
    "JP": [
        "日本国憲法",
        "民法",
        "労働基準法",
        "会社法",
    ],
    "KR": [
        "대한민국헌법",
        "민법",
        "근로기준법",
        "형법",
    ],
    "SG": [
        "Constitution of the Republic of Singapore",
        "Contracts (Rights of Third Parties) Act 2001",
        "Employment Act 1968",
        "Sale of Goods Act 1979",
    ],
}

SG_ACT_CODES = {
    "Constitution of the Republic of Singapore": "CONS1963",
    "Contracts (Rights of Third Parties) Act 2001": "CRTPA2001",
    "Employment Act 1968": "EmA1968",
    "Sale of Goods Act 1979": "SGA1979",
}


def run(
    jurisdictions: list[str] | None = None,
    sleep_s: float = 1.5,
    out_dir: Path | None = None,
) -> dict:
    out_dir = out_dir or DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ses = FetchSession(sleep_s=sleep_s)
    srcs = {
        "CN": CnFlkSource(ses),
        "JP": JpEgovSource(ses),
        "KR": KrLawSource(ses),
        "SG": SgSsoSource(ses),
    }
    jurisdictions = list(CORE_LAWS) if jurisdictions is None else jurisdictions

    all_statutes: list[Statute] = []
    law_reports: list[dict] = []

    for jur in jurisdictions:
        src = srcs[jur]
        for title in CORE_LAWS[jur]:
            t0 = time.time()
            try:
                if jur == "SG":
                    raw = src.fetch_law(SG_ACT_CODES[title], title_hint=title)
                else:
                    raw = src.fetch_law(title)
                stats = normalize(raw)
                all_statutes.extend(stats)
                # 单法 JSON（详细留存）
                law_file = out_dir / f"{jur}_{raw.source_id or title}.json"
                law_file.write_text(
                    json.dumps(
                        {
                            "law": {
                                "title": raw.title,
                                "source": raw.source,
                                "source_id": raw.source_id,
                                "jurisdiction": raw.jurisdiction,
                                "language": raw.language,
                                "promulgation_date": raw.promulgation_date,
                                "effective_date": raw.effective_date,
                                "status": raw.status,
                                "amended_history": raw.amended_history,
                                "source_url": raw.source_url,
                                "article_count": len(raw.articles),
                            },
                            "statutes": [s.model_dump() for s in stats],
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                law_reports.append({
                    "jur": jur, "title": title, "ok": True,
                    "articles": len(raw.articles),
                    "status": raw.status,
                    "promulgation": raw.promulgation_date,
                    "effective": raw.effective_date,
                    "history_items": len(raw.amended_history),
                    "seconds": round(time.time() - t0, 1),
                    "file": law_file.name,
                })
                print(f"[OK] {jur} {title}: {len(raw.articles)} 条 ({law_reports[-1]['seconds']}s)")
            except Exception as e:
                traceback.print_exc()
                law_reports.append({
                    "jur": jur, "title": title, "ok": False, "error": str(e)[:200],
                })
                print(f"[FAIL] {jur} {title}: {e}")

    quality = validate(all_statutes)
    # 合并文件 = 磁盘全部单法 JSON 扫描（跨次运行保底，不被单次失败覆盖）
    merged_map: dict[str, Statute] = {}
    for f in sorted(out_dir.glob("*.json")):
        if f.name in ("official_statutes.json", "pipeline_report.json"):
            continue
        try:
            blob = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for item in blob.get("statutes", []):
            s = Statute(**item)
            if s.id not in merged_map or len(s.text) > len(merged_map[s.id].text):
                merged_map[s.id] = s
    merged_statutes = list(merged_map.values())
    quality = validate(merged_statutes)
    merged = out_dir / "official_statutes.json"
    merged.write_text(
        json.dumps([s.model_dump() for s in merged_statutes], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = {"laws": law_reports, "quality": quality}
    (out_dir / "pipeline_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_md_report(out_dir / "PIPELINE_REPORT.md", report)
    print(f"\n合计 {quality['total']} 条 → {merged}")
    return report


def _write_md_report(path: Path, report: dict) -> None:
    q = report["quality"]
    lines = [
        "# 官方法规源数据管道报告",
        "",
        f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 抓取清单",
        "",
        "| 法域 | 法律 | 结果 | 条文数 | 公布日 | 施行日 | 状态 | 沿革条目 | 耗时 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in report["laws"]:
        if r.get("ok"):
            lines.append(
                f"| {r['jur']} | {r['title']} | ✅ | {r['articles']} | {r.get('promulgation') or '-'} | "
                f"{r.get('effective') or '-'} | {r['status']} | {r['history_items']} | {r['seconds']}s |"
            )
        else:
            lines.append(f"| {r['jur']} | {r['title']} | ❌ {r.get('error','')[:60]} | - | - | - | - | - | - |")
    lines += [
        "",
        "## 数据质量校验",
        "",
        f"- 总条文数：{q['total']}",
        f"- 平均条文长度：{q['avg_text_len']} 字",
        f"- 重复 ID：{q['duplicate_ids'] or '无'}",
        f"- 过短条文（<8字）：{q['too_short'] or '无'}",
        f"- 无日期且无沿革：{q['no_date_no_history'] or '无'}",
        f"- 非法状态值：{q['bad_status'] or '无'}",
        "",
        "### 各法条数",
        "",
    ]
    for law, n in q["laws"].items():
        lines.append(f"- {law}: {n} 条")
    lines += ["", "### 条号连续性（缺号）", ""]
    if q["numbering_gaps"]:
        for law, gaps in q["numbering_gaps"].items():
            lines.append(f"- {law}: {gaps}")
    else:
        lines.append("无缺号 🎉")
    lines += [
        "",
        "## 数据源",
        "",
        "- CN 国家法律法规数据库 flk.npc.gov.cn（POST /law-search/search/list + download/pc 官方 docx）",
        "- JP e-Gov 法令 API laws.e-gov.go.jp/api/1/lawdata（現行法令全文 XML）",
        "- KR 국가법령정보센터 law.go.kr（법령别名页 + POST lsInfoR.do 正文）",
        "- SG Singapore Statutes Online sso.agc.gov.sg（Act 页 + WholeDoc，AWS WAF 重试）",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
