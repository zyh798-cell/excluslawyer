# -*- coding: utf-8 -*-
"""就地重写官方数据 JSON 中的法条 ID（修正双重前缀 bug 后用）。"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.models.schemas import Statute  # noqa: E402
from app.data_pipeline.normalizer import article_key, slug_tag  # noqa: E402

DATA_DIR = BASE_DIR / "data" / "official"


def main() -> None:
    fixed = 0
    for f in sorted(DATA_DIR.glob("*.json")):
        if f.name in ("official_statutes.json", "pipeline_report.json"):
            continue
        blob = json.loads(f.read_text(encoding="utf-8"))
        law_title = blob.get("law", {}).get("title", "")
        jur = blob.get("law", {}).get("jurisdiction", "CN")
        tag = slug_tag(law_title)
        changed = False
        for s in blob.get("statutes", []):
            new_id = f"{jur}-{tag}-{article_key(s['article_no'])}"
            if s["id"] != new_id:
                s["id"] = new_id
                changed = True
                fixed += 1
        if changed:
            f.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
            print("fixed", f.name)
    print(f"total fixed: {fixed}")
    # 重建合并文件
    from app.data_pipeline.pipeline import run
    run(jurisdictions=[])


if __name__ == "__main__":
    main()
