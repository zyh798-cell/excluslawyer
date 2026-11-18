"""Cross-language README consistency checker for EXCLUSLAWYER."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["README.md", "README.zh-CN.md", "README.ja.md", "README.ko.md"]

REQUIRED_SECTIONS = 14

# numbers that must appear identically in every language
SHARED_TOKENS = [
    "7,054", "2,338", "2,610", "1,856", "250", "113", "4 skipped", "49 / 49",
    "0 %", "0.08", "0.35", "2.0 s", "1.9 s", "v0.1.0", "AGPL-3.0", "CC BY-NC 4.0",
    "55", "64", "1.00", "120", "16 / 24 / 32",
]

DOC_LINKS = [
    "docs/architecture.md", "docs/scenario-entry.md", "docs/plain-explain.md",
    "docs/mock-court.md", "docs/mock-trial.md", "docs/eval.md",
    "docs/regression-report.md", "docs/known-issues.md",
    "docs/banner.svg", "docs/logo.svg", "docs/favicon.svg", "assets/logo.svg",
    "LICENSE",
]

EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U0001F1E6-\U0001F1FF]"
)


def headings(text):
    return [h.strip() for h in re.findall(r"^#{1,3}\s+(.+)$", text, re.M)]


def check_corruption(text, name):
    issues = []
    if "\ufffd" in text:
        for i, line in enumerate(text.split("\n"), 1):
            if "\ufffd" in line:
                issues.append(f"{name}:{i} replacement char")
    # latin word glued between CJK chars
    for i, line in enumerate(text.split("\n"), 1):
        for m in re.finditer(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af][A-Za-z]{2,}[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", line):
            ctx = line[max(0, m.start() - 25):m.end() + 25]
            latin = re.search(r"[A-Za-z]+", m.group())
            latin = latin.group() if latin else ""
            if latin in ("schema", "localStorage", "untrusted_data", "interrupt", "resume",
                             "prefers", "reduce", "SQLite", "Milvus", "Lite", "Standalone", "NumPy",
                             "Neo4j", "Redis", "MinIO", "Celery", "Docker", "Compose", "Playwright",
                             "Chromium", "Lighthouse", "pytest", "vitest", "reportlab", "pypdf",
                             "pymilvus", "FlagEmbedding", "Tailwind", "TypeScript", "React",
                             "FastAPI", "Pydantic", "LangGraph", "AntV", "lucide", "Next", "Node",
                             "Python", "REST", "SSE", "NLI", "OCR", "PDF", "API", "NPM", "MD", "BYOK",
                             "BYOK", "API", "SSE", "REST", "PDF", "MD", "BGE", "M3", "reranker", "FlagEmbedding", "pymilvus", "numpy", "reportlab", "pypdf", "LangGraph", "checkpoint", "sqlite", "Lighthouse", "Playwright", "Chromium", "Tailwind", "TypeScript", "React", "FastAPI", "Pydantic", "Neo4j", "Redis", "MinIO", "Celery", "Docker", "Compose", "Next", "Node", "Python", "NLI", "OCR", "BYOK", "RAG", "UI", "GitHub", "LLM", "NP"):
                continue
            issues.append(f"{name}:{i} mixed-script {m.group()!r} :: {ctx}")
    return issues


def main():
    problems = []
    contents = {}
    for f in FILES:
        p = os.path.join(ROOT, f)
        if not os.path.exists(p):
            problems.append(f"MISSING FILE {f}")
            continue
        text = open(p, encoding="utf-8").read()
        contents[f] = text

        problems += check_corruption(text, f)

        h2 = re.findall(r"^##\s+(.+)$", text, re.M)
        if len(h2) < REQUIRED_SECTIONS:
            problems.append(f"{f}: only {len(h2)} level-2 sections (expect >= {REQUIRED_SECTIONS})")

        # badge / number parity
        for tok in SHARED_TOKENS:
            if tok not in text:
                problems.append(f"{f}: missing shared token {tok!r}")

        # link targets must exist
        for link in re.findall(r"\]\(([^)]+)\)", text):
            if link.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target = os.path.join(ROOT, link.split("#")[0])
            if not os.path.exists(target):
                problems.append(f"{f}: dead link -> {link}")

        # internal anchors must resolve
        anchors = set()
        for h in headings(text):
            slug = re.sub(r"[^\w\s-]", "", h.lower()).strip().replace(" ", "-")
            slug = re.sub(r"-+", "-", slug).replace("--", "-")
            anchors.add(slug)
            anchors.add(re.sub(r"-", "", slug))
        for a in re.findall(r"\]\(#([^)]+)\)", text):
            if a not in anchors and a.replace("-", "") not in {x.replace("-", "") for x in anchors}:
                problems.append(f"{f}: unresolved anchor #{a}")

        # emoji ban
        for m in EMOJI.finditer(text):
            problems.append(f"{f}: emoji {m.group()!r} near {text[max(0,m.start()-30):m.start()+30]!r}")

        # svg reference
        if 'src="docs/banner.svg"' not in text:
            problems.append(f"{f}: banner not referenced via <img>")

    # badge URLs identical across languages
    for f, text in contents.items():
        bad = re.findall(r'img\.shields\.io/badge/([^"]+)', text)
        if bad:
            print(f"{f}: {len(bad)} badges")

    # parity of badge set
    badge_sets = {f: set(re.findall(r'img\.shields\.io/badge/([^"]+)', t)) for f, t in contents.items()}
    base = badge_sets[FILES[0]]
    for f, s in badge_sets.items():
        if s != base:
            problems.append(f"{f}: badge set differs from master ({len(s)} vs {len(base)})")

    # table row parity (rough): count rows starting with '|'
    for f, t in contents.items():
        rows = len([l for l in t.split("\n") if l.strip().startswith("|")])
        print(f"{f}: {len(t.splitlines())} lines, {rows} table rows, "
              f"{len(re.findall(r'^##\s', t, re.M))} H2")

    print()
    if problems:
        print(f"PROBLEMS ({len(problems)}):")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
