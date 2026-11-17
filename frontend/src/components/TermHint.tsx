"use client";

import { useState } from "react";
import { BookOpen } from "lucide-react";
import { TERM_MATCH_WORDS, TERM_LOOKUP, type LawTerm } from "@/lib/terms";

/**
 * 术语即时释义：专业术语首次出现时渲染为可点击词，点击后在原位下方展开
 * 通俗释义 + 类比卡片（内联展开式，不用重组件库；窄屏无绝对定位溢出问题）。
 *
 * 红线：释义只解释概念，不提供结论或行动建议。
 */
export default function TermHint({ term }: { term: LawTerm }) {
  const [open, setOpen] = useState(false);
  const panelId = `term-panel-${term.term}`;

  return (
    <span className="inline">
      <button
        type="button"
        className="inline-flex items-baseline gap-0.5 border-b border-dashed border-accent/60 text-accent-soft"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={`查看术语释义：${term.term}`}
        title={term.term}
      >
        {term.term}
        <BookOpen size={12} aria-hidden className="self-center" />
      </button>
      {open && (
        <span
          id={panelId}
          className="mt-1 block rounded-xl border border-line bg-surface-raised p-3 text-sm shadow-lg"
          role="note"
        >
          <span className="block text-xs leading-6 text-fg-muted">
            <span className="font-semibold text-fg">{term.term}：</span>
            {term.plain}
          </span>
          <span className="mt-1.5 block text-xs leading-6 text-fg-subtle">
            <span className="font-medium text-fg-muted">类比：</span>
            {term.analogy}
          </span>
        </span>
      )}
    </span>
  );
}

/** 术语匹配词表（长词优先，避免「仲裁」吃掉「仲裁前置」）。 */
const TERM_MATCH_ORDER = TERM_MATCH_WORDS;

/**
 * 把一段白话文本按术语表切分渲染：命中术语 → TermHint，其余原样。
 */
export function renderTextWithTerms(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let buf = "";
  let i = 0;
  const pushBuf = () => {
    if (buf) {
      nodes.push(buf);
      buf = "";
    }
  };
  outer: while (i < text.length) {
    for (const w of TERM_MATCH_ORDER) {
      if (text.startsWith(w, i)) {
        pushBuf();
        nodes.push(<TermHint key={`${i}-${w}`} term={TERM_LOOKUP.get(w)!} />);
        i += w.length;
        continue outer;
      }
    }
    buf += text[i];
    i += 1;
  }
  pushBuf();
  return nodes;
}
