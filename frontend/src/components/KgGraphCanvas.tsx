"use client";

import { useEffect, useRef } from "react";
import type { KgQueryResponse } from "@/lib/api";

/** 从 CSS 变量取色（主题切换跟随全局变量，禁止硬编码颜色）。 */
function cssVar(name: string): string {
  if (typeof window === "undefined") return "#888";
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  // 变量是 "R G B" 三元组
  const parts = v.split(/\s+/).map(Number);
  if (parts.length === 3 && parts.every((n) => !isNaN(n))) {
    return `rgb(${parts[0]} ${parts[1]} ${parts[2]})`;
  }
  return v || "#888";
}

export function jurColorOf(statuteId: string): string {
  if (statuteId.startsWith("s:CN") || statuteId.startsWith("CN")) return cssVar("--c-jur-cn");
  if (statuteId.startsWith("s:JP") || statuteId.startsWith("JP")) return cssVar("--c-jur-jp");
  if (statuteId.startsWith("s:KR") || statuteId.startsWith("KR")) return cssVar("--c-jur-kr");
  if (statuteId.startsWith("s:SG") || statuteId.startsWith("SG")) return cssVar("--c-jur-sg");
  return cssVar("--c-accent");
}

interface CanvasProps {
  result: KgQueryResponse;
  /** 仅展示指定法域的条文节点（null=全部）；其他节点不受影响，不改动缓存数据 */
  jurFilter: string | null;
}

/**
 * G6 知识图谱画布（懒加载；Canvas2D 渲染，聊天页无任何 WebGL 负载）。
 * 数据来自 /api/kg/query 的多跳路径（kg_service.py 产出），只读消费。
 */
export default function KgGraphCanvas({ result, jurFilter }: CanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<{ destroy: () => void } | null>(null);

  useEffect(() => {
    let disposed = false;
    const el = containerRef.current;
    if (!el) return;

    async function render() {
      const el = containerRef.current;
      if (!el) return;
      // ---- 组装子图数据（纯派生，不改动 result 缓存）----
      const nodeMap = new Map<
        string,
        { id: string; name: string; type: string; jur: string | null }
      >();
      const edges: { source: string; target: string; relation: string }[] = [];

      const consider = (id: string, name: string, type: string) => {
        if (nodeMap.has(id)) return;
        const m = /^(?:s:)?(CN|JP|KR|SG)-/.exec(id);
        nodeMap.set(id, { id, name, type, jur: m ? m[1] : null });
      };
      if (result.matched_node) {
        consider(result.matched_node.id, result.matched_node.name, result.matched_node.node_type);
      }
      for (const p of result.paths) {
        const [a, b] = p.nodes;
        if (!a || !b) continue;
        consider(a.id, a.name, a.node_type);
        consider(b.id, b.name, b.node_type);
        edges.push({ source: a.id, target: b.id, relation: p.relations[0] ?? "" });
      }

      // 法域过滤：仅影响展示的条文节点（概念/判例节点始终保留）
      const visibleIds = new Set<string>();
      for (const n of nodeMap.values()) {
        const hide = jurFilter && n.jur && n.jur !== jurFilter && n.type === "statute";
        if (!hide) visibleIds.add(n.id);
      }
      const nodes = [...nodeMap.values()]
        .filter((n) => visibleIds.has(n.id))
        .map((n) => ({
          id: n.id,
          name: n.name.length > 14 ? n.name.slice(0, 13) + "…" : n.name,
          fullName: n.name,
          nodeType: n.type,
          jur: n.jur,
        }));
      const edges2 = edges.filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target));

      // ---- 懒加载 G6 ----
      let GraphCtor: new (cfg: unknown) => { render: () => void; destroy: () => void };
      try {
        const mod = await import("@antv/g6");
        GraphCtor = (mod.Graph ?? (mod as unknown as { default: { Graph: unknown } }).default.Graph) as never;
      } catch {
        el.innerHTML =
          '<p style="padding:12px;font-size:12px;opacity:.7">图谱画布组件加载失败（G6 不可用），请查看上方文字版结构化展开。</p>';
        return;
      }
      if (disposed) return;

      const lineColor = cssVar("--c-graph-line");
      const textColor = cssVar("--c-graph-text");
      const nodeFill = cssVar("--c-graph-node");
      const nodeStroke = cssVar("--c-graph-node-stroke");

      try {
        graphRef.current?.destroy();
        const graph = new GraphCtor({
          container: el,
          width: el.clientWidth || 640,
          height: 320,
          autoFit: "view",
          padding: 24,
          data: {
            nodes: nodes.map((n) => ({
              id: n.id,
              name: n.name,
              fullName: n.fullName,
              nodeType: n.nodeType,
              jur: n.jur,
            })),
            edges: edges2.map((e) => ({
              source: e.source,
              target: e.target,
              relation: e.relation,
            })),
          },
          layout: { type: "dagre", rankdir: "LR", nodesep: 16, ranksep: 56 },
          node: {
            style: {
              size: (d: { nodeType?: string }) => (d.nodeType === "statute" ? 30 : 38),
              fill: (d: { nodeType?: string; jur?: string | null }) =>
                d.nodeType === "statute" && d.jur
                  ? jurColorOf(`${d.jur}-`)
                  : nodeFill,
              stroke: (d: { nodeType?: string; jur?: string | null }) =>
                d.nodeType === "statute" && d.jur
                  ? jurColorOf(`${d.jur}-`)
                  : nodeStroke,
              lineWidth: 1.5,
              labelText: (d: { name?: string }) => d.name ?? "",
              labelFill: textColor,
              labelFontSize: 10,
              labelPlacement: "bottom",
              radius: 6,
            },
          },
          edge: {
            style: {
              stroke: lineColor,
              lineWidth: 1.2,
              endArrow: true,
              labelText: (d: { relation?: string }) => d.relation ?? "",
              labelFill: textColor,
              labelFontSize: 9,
              labelOpacity: 0.75,
            },
          },
          behaviors: ["drag-canvas", "zoom-canvas", "drag-element"],
        });
        graph.render();
        graphRef.current = graph;
      } catch {
        el.innerHTML =
          '<p style="padding:12px;font-size:12px;opacity:.7">图谱画布渲染失败，请查看上方文字版结构化展开。</p>';
      }
    }

    render();

    // 主题切换 → 重取 CSS 变量重绘
    const onTheme = () => render();
    window.addEventListener("lextheme", onTheme);
    return () => {
      disposed = true;
      window.removeEventListener("lextheme", onTheme);
      graphRef.current?.destroy();
      graphRef.current = null;
    };
  }, [result, jurFilter]);

  return (
    <div
      ref={containerRef}
      className="neu-inset mt-3 h-[320px] w-full overflow-hidden"
      role="img"
      aria-label={`知识图谱画布：${result.matched_node?.name ?? "子图"}，共 ${result.paths.length} 条关系路径`}
    />
  );
}
