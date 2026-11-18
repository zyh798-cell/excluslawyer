"""Build the animated brand assets from the original raster artwork.

Inputs
  docs/_cat_matted.png      alpha-matted cutout of the original artwork

Outputs
  assets/logo.svg           static vector master of the cat (no animation)
  docs/banner.svg           1200x320 animated banner
  docs/logo.svg             120x120 animated square mark
  docs/favicon.svg          monochrome silhouette (16 / 24 / 32)

The cat is never redesigned: every contour is traced from the source pixels.
Only the representation changes (raster -> editable vector) and the motion
(layered on top) is new.
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "_cat_matted.png")
ASSETS = os.path.join(ROOT, "assets")

# brand tokens
INK = "#0E1420"       # deep navy - fur
INK_2 = "#182234"     # deep navy tint - inner ear / shading
STEEL = "#5EA9C9"     # steel blue - secondary accent
AMBER = "#C8861A"     # amber - chest tuft, emphasis
PAPER = "#F2EEE6"     # warm paper - eyes, text
BG = "#0B0E14"        # banner ground


# ---------------------------------------------------------------- segmenting
def segment(rgb: np.ndarray, alpha: np.ndarray):
    r, g, b = rgb[..., 0].astype(int), rgb[..., 1].astype(int), rgb[..., 2].astype(int)
    lum = (r + g + b) / 3.0
    sil = alpha > 140

    chest = sil & ((r - b) > 26) & (r + g + b > 240)

    cream = sil & (r > 150) & (g > 140) & (b > 120) & ((r - b) < 70)

    grid_y, grid_x = np.indices(sil.shape)
    ys, xs = np.nonzero(sil)
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
    head = (grid_y < y0 + 0.46 * (y1 - y0)) & (grid_x < x0 + 0.55 * (x1 - x0))

    eyes = cream & head
    inner_ear = sil & head & (r >= b - 6) & (lum > 50) & (lum < 98) & ~cream

    # small warm blob on the muzzle = nose
    warm = sil & ((r - g) > 6) & ((r - b) > 36) & (r > 100) & (lum > 80) & (lum < 190)
    muzzle = (grid_y > y0 + 0.42 * (y1 - y0)) & (grid_y < y0 + 0.58 * (y1 - y0))
    nose = np.zeros_like(sil)
    lab, n = ndimage.label(warm & muzzle)
    for i in range(1, n + 1):
        comp = lab == i
        area = int(comp.sum())
        if 30 <= area <= 1500:
            nose |= comp

    return {"silhouette": sil, "chest": chest, "eyes": eyes, "ear": inner_ear, "nose": nose}


# ------------------------------------------------------------------ tracing
def trace(mask: np.ndarray):
    m = np.pad(mask, 1)
    up = np.roll(m, 1, axis=0)[1:-1, 1:-1]
    dn = np.roll(m, -1, axis=0)[1:-1, 1:-1]
    lf = np.roll(m, 1, axis=1)[1:-1, 1:-1]
    rt = np.roll(m, -1, axis=1)[1:-1, 1:-1]
    inside = m[1:-1, 1:-1]

    edges = defaultdict(list)
    ys, xs = np.nonzero(inside & ~up)
    for y, x in zip(ys.tolist(), xs.tolist()):
        edges[(x + 1, y + 1)].append((x + 2, y + 1))
    ys, xs = np.nonzero(inside & ~rt)
    for y, x in zip(ys.tolist(), xs.tolist()):
        edges[(x + 2, y + 1)].append((x + 2, y + 2))
    ys, xs = np.nonzero(inside & ~dn)
    for y, x in zip(ys.tolist(), xs.tolist()):
        edges[(x + 2, y + 2)].append((x + 1, y + 2))
    ys, xs = np.nonzero(inside & ~lf)
    for y, x in zip(ys.tolist(), xs.tolist()):
        edges[(x + 1, y + 2)].append((x + 1, y + 1))

    polys = []
    guard = 0
    while edges:
        guard += 1
        if guard > 200000:
            break
        start = next(iter(edges))
        poly, cur = [start], start
        while True:
            lst = edges.get(cur)
            if not lst:
                edges.pop(cur, None)
                break
            nxt = lst.pop()
            if not lst:
                del edges[cur]
            if nxt == start:
                break
            poly.append(nxt)
            cur = nxt
        if len(poly) > 8:
            polys.append(poly)
    return polys


# ----------------------------------------------------------------- smoothing
def rdp(pts, eps):
    n = len(pts)
    if n < 3:
        return list(pts)
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        p = np.asarray(pts[i:j + 1], dtype=float)
        a, b = p[0], p[-1]
        ab = b - a
        norm = math.hypot(*ab) or 1.0
        rel = p[1:-1] - a
        dist = np.abs(ab[0] * rel[:, 1] - ab[1] * rel[:, 0]) / norm
        k = int(np.argmax(dist))
        if dist[k] > eps:
            idx = i + 1 + k
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [pts[i] for i in range(n) if keep[i]]


def chaikin(pts, iters=2):
    for _ in range(iters):
        out = []
        n = len(pts)
        for i in range(n):
            p, q = pts[i], pts[(i + 1) % n]
            out.append((0.75 * p[0] + 0.25 * q[0], 0.75 * p[1] + 0.25 * q[1]))
            out.append((0.25 * p[0] + 0.75 * q[0], 0.25 * p[1] + 0.75 * q[1]))
        pts = out
    return pts


def contour(mask, eps, min_pts=30, smooth=1):
    out = []
    for p in trace(mask):
        if len(p) < min_pts:
            continue
        out.append(chaikin(rdp(p, eps), iters=smooth))
    out.sort(key=len, reverse=True)
    return out


def to_path(pts, tf, precision=1):
    norm = [tf(p) for p in pts]
    if norm[0] != norm[-1]:
        norm.append(norm[0])
    d = [f"M{norm[0][0]:.{precision}f} {norm[0][1]:.{precision}f}"]
    n = len(norm) - 1
    for i in range(n):
        p0, p1 = norm[(i - 1) % n], norm[i]
        p2, p3 = norm[(i + 1) % n], norm[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        d.append(
            f"C{c1[0]:.{precision}f} {c1[1]:.{precision}f} {c2[0]:.{precision}f} {c2[1]:.{precision}f} "
            f"{p2[0]:.{precision}f} {p2[1]:.{precision}f}"
        )
    d.append("Z")
    return "".join(d)


# ------------------------------------------------------------------ tail cut
def split_tail(sil: np.ndarray, x_gate: int = 420):
    """Isolate the tail band from the body using the row-run structure.

    The tail is the right-most structure of the drawing: every row run that
    starts right of the torso (x_gate) belongs to it. The tail re-joins the
    body around the hip, where the runs merge again.
    """
    band = np.zeros_like(sil)
    h, w = sil.shape
    for y in range(h):
        row = sil[y]
        if not row.any():
            continue
        d = np.diff(np.concatenate(([0], row.view(np.int8), [0])))
        starts = np.nonzero(d == 1)[0]
        ends = np.nonzero(d == -1)[0] - 1
        runs = [(s, e) for s, e in zip(starts, ends) if e - s >= 8]
        for s, e in runs:
            if s >= x_gate:
                band[y, s:e + 1] = True

    ys, xs = np.nonzero(band)
    if not len(ys):
        return band, sil, (0.0, 0.0)

    bottom = int(ys.max())
    neck_x = []
    for r in range(max(0, bottom - 12), bottom + 1):
        sel = (ys >= r) & (ys <= r)
        if sel.any():
            neck_x.append(float(xs[sel].mean()))
    pivot = (float(np.mean(neck_x)), float(bottom))
    return band, sil, pivot


def eye_pupils(eye_mask: np.ndarray, cream: np.ndarray, dark: np.ndarray):
    """The pupil is the dark slit framed by cream on both sides."""
    pupil = np.zeros_like(eye_mask)
    ys, xs = np.nonzero(eye_mask)
    if not len(ys):
        return pupil
    y0, y1 = int(ys.min()), int(ys.max())
    for y in range(y0, y1 + 1):
        row = np.nonzero(cream[y])[0]
        row = row[(row >= xs.min()) & (row <= xs.max())]
        if len(row) < 2:
            continue
        lo, hi = int(row.min()), int(row.max())
        if hi - lo < 10:
            continue
        mid = dark[y, lo:hi + 1]
        pupil[y, lo:hi + 1] = mid
    return pupil


def main():
    im = Image.open(SRC).convert("RGBA")
    rgb = np.array(im)[..., :3]
    alpha = np.array(im)[..., 3]
    layers = segment(rgb, alpha)

    sil = layers["silhouette"]
    f = 2
    h, w = sil.shape
    small = sil[: h // f * f, : w // f * f].reshape(h // f, f, w // f, f).any(axis=(1, 3))

    band, small_sil, pivot = split_tail(small)
    band_d = ndimage.binary_dilation(band, np.ones((5, 5), bool))
    stub = np.zeros_like(band)
    # keep a short overlap of the tail inside the body so the seam never opens
    ys, xs = np.nonzero(band)
    if len(ys):
        ymax = int(ys.max())
        for y in range(ymax, min(small.shape[0], ymax + 22)):
            stub[y, :] = small_sil[y, :] & (np.arange(small.shape[1]) >= pivot[0] - 12)

    body_mask = small_sil & ~band
    tail_mask = (band | stub) & small_sil

    def sc(mask):
        return mask[: mask.shape[0] // f * f, : mask.shape[1] // f * f].reshape(
            mask.shape[0] // f, f, mask.shape[1] // f, f
        ).any(axis=(1, 3))

    lum = rgb.astype(int).sum(axis=2) / 3.0
    dark_small = sc(sil & (lum < 78))
    cream_small = sc(layers["eyes"])

    shapes = {
        "body": contour(body_mask, 1.9, smooth=1),
        "tail": contour(tail_mask, 1.9, smooth=1),
        "chest": contour(sc(layers["chest"]), 1.1, smooth=1),
    }

    # eyes + pupils, paired per eye so each can blink on its own
    eye_small = cream_small
    eye_lab, eye_n = ndimage.label(eye_small)
    eye_pairs = []
    for i in range(1, eye_n + 1):
        comp = eye_lab == i
        if comp.sum() < 60:
            continue
        eye_pairs.append(
            (contour(comp, 0.8, smooth=1), contour(eye_pupils(comp, cream_small, dark_small), 0.7, min_pts=10, smooth=1))
        )

    ys, xs = np.nonzero(small_sil)
    bx0, by0 = int(xs.min()), int(ys.min())
    bx1, by1 = int(xs.max()) + 1, int(ys.max()) + 1
    bw, bh = bx1 - bx0, by1 - by0
    pad = 4.0
    inner = 100.0 - 2 * pad
    scale = min(inner / bw, inner / bh)
    off_x = pad + (inner - bw * scale) / 2.0
    off_y = pad + (inner - bh * scale) / 2.0

    def tf(p):
        return (off_x + (p[0] - bx0) * scale, off_y + (p[1] - by0) * scale)

    def paths(polys):
        return [to_path(p, tf) for p in polys]

    def tp(pivot_pt):
        return (round(pivot_pt[0] * scale + off_x - bx0 * scale, 2), round(pivot_pt[1] * scale + off_y - by0 * scale, 2))

    data = {
        "bbox": [bx0, by0, bx1, by1],
        "body": paths(shapes["body"]),
        "tail": paths(shapes["tail"]),
        "chest": paths(shapes["chest"]),
        "eyes": [[paths(e), paths(p)] for e, p in eye_pairs],
        "pivot": tp((pivot[0], pivot[1])),
        "pivot_raw": pivot,
    }
    with open(os.path.join(ROOT, "docs", "_vector_layers.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)

    for k in ("body", "tail", "chest"):
        print(f"{k}: {len(shapes[k])} contour(s) {[len(p) for p in shapes[k]]}")
    print("eyes:", [(len(e), len(p)) for e, p in eye_pairs])
    print("pivot(raw):", pivot, "-> normalised:", data["pivot"])

    # preview render
    canvas = Image.new("RGBA", (640, 640), (11, 14, 20, 255))
    dr = ImageDraw.Draw(canvas)

    def draw(polys, color):
        for poly in polys:
            pts = [tf(p) for p in poly]
            dr.polygon([(x / 100 * 640, y / 100 * 640) for x, y in pts], fill=color)

    draw(shapes["body"], (14, 20, 32, 255))
    draw(shapes["tail"], (14, 20, 32, 255))
    draw(shapes["chest"], (200, 134, 26, 255))
    for e, p in eye_pairs:
        draw(e, (242, 238, 230, 255))
        draw(p, (14, 20, 32, 255))
    canvas.save(os.path.join(ROOT, "docs", "_vector_debug.png"))
    print("preview written")

    # ------------------------------------------------------------- emitters
    def place(cx, cy, size):
        """Map the 0..100 cat box (via tf) onto a target placement."""
        k = size / 100.0
        px, py = tf(pivot)

        def T(p):
            nx, ny = tf(p)
            return (cx + (nx - 50.0) * k, cy + (ny - 50.0) * k)

        return T, (cx + (px - 50.0) * k, cy + (py - 50.0) * k)

    def d_of(polys, T):
        return " ".join(to_path(p, T) for p in polys)

    def cat_markup(T, Tpivot, motion=True):
        """The cat itself: body, swaying tail, breathing chest, blinking eyes."""
        def cls(name):
            return f' class="{name}"' if motion else ""

        out = []
        out.append(f'<g{cls("enter")}>')
        out.append(
            f'  <g{cls("tail")} style="transform-origin:{Tpivot[0]:.1f}px {Tpivot[1]:.1f}px">'
        )
        out.append(f'    <path d="{d_of(shapes["tail"], T)}" fill="{INK}"/>')
        out.append("  </g>")
        out.append(f'  <path d="{d_of(shapes["body"], T)}" fill="{INK}"/>')
        if shapes["chest"]:
            out.append(f'  <path id="chestmark" d="{d_of(shapes["chest"], T)}" fill="{AMBER}"/>')
            out.append(
                f'  <use href="#chestmark"{cls("glow")} opacity="0.4" filter="url(#soft)"/>'
            )
        for eye, pup in eye_pairs:
            out.append(f'  <g{cls("eye")}>')
            out.append(f'    <path d="{d_of(eye, T)}" fill="{PAPER}"/>')
            if pup:
                out.append(f'    <path d="{d_of(pup, T)}" fill="{INK}"/>')
            out.append("  </g>")
        out.append("</g>")
        return "\n".join(out)

    CSS = """
  .enter { animation: enter .4s cubic-bezier(.22,.68,.32,1) both; }
  .tail  { transform-box: view-box; animation: sway 3s ease-in-out infinite; }
  .eye   { transform-box: fill-box; transform-origin: center; animation: blink 3.8s ease-in-out infinite; }
  .glow  { animation: breathe 2.6s ease-in-out infinite; }
  .shimmer { animation: shimmer 7s ease-in-out infinite; }
  .rule  { animation: rulepulse 5s ease-in-out infinite; }
  .disc  { animation: discpulse 6s ease-in-out infinite; }
  @keyframes enter { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
  @keyframes sway { 0%,100% { transform: rotate(-4deg); } 50% { transform: rotate(4deg); } }
  @keyframes blink { 0%,90%,100% { transform: scaleY(1); } 93% { transform: scaleY(.08); } 96% { transform: scaleY(1); } }
  @keyframes breathe { 0%,100% { opacity: .30; } 50% { opacity: .80; } }
  @keyframes shimmer { 0%,100% { stop-color: #C8861A; } 50% { stop-color: #F2EEE6; } }
  @keyframes rulepulse { 0%,100% { opacity: .35; } 50% { opacity: .95; } }
  @keyframes discpulse { 0%,100% { opacity: .45; } 50% { opacity: .85; } }
  @media (prefers-reduced-motion: reduce) {
    .enter, .tail, .eye, .glow, .shimmer, .rule, .disc { animation: none !important; }
    .enter { opacity: 1; transform: none; }
    .glow { opacity: .45; }
  }
"""

    # ---------------------------------------------------------- static master
    T0, P0 = place(50.0, 50.0, 100.0)
    master = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" role="img" aria-label="EXCLUSLAWYER mark: a black cat with one upright ear and one folded ear, half-lidded eyes, an amber chest tuft and a curled tail.">
  <title>EXCLUSLAWYER mark</title>
  <defs>
    <filter id="soft" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="3"/>
    </filter>
  </defs>
  <path d="{d_of(shapes["body"], T0)}" fill="{INK}"/>
  <path d="{d_of(shapes["tail"], T0)}" fill="{INK}"/>
  <path d="{d_of(shapes["chest"], T0)}" fill="{AMBER}"/>
</svg>
"""
    os.makedirs(ASSETS, exist_ok=True)
    with open(os.path.join(ASSETS, "logo.svg"), "w", encoding="utf-8") as fh:
        fh.write(master)

    # ------------------------------------------------------------- square mark
    TS, PS = place(60.0, 60.0, 84.0)
    square = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120" role="img" aria-label="EXCLUSLAWYER mark: a black cat with one upright ear and one folded ear, half-lidded eyes, an amber chest tuft and a curled tail.">
  <title>EXCLUSLAWYER mark</title>
  <style>{CSS}</style>
  <defs>
    <radialGradient id="disc" cx="0.5" cy="0.40" r="0.64">
      <stop offset="0" stop-color="#FBF9F4"/>
      <stop offset="1" stop-color="#E4DED2"/>
    </radialGradient>
    <filter id="soft" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="2.4"/>
    </filter>
  </defs>
  <rect width="120" height="120" rx="18" fill="{INK}"/>
  <circle class="disc" cx="60" cy="60" r="52" fill="url(#disc)" stroke="{AMBER}" stroke-width="1.4" opacity="0.85"/>
  {cat_markup(TS, PS)}
</svg>
"""
    with open(os.path.join(ROOT, "docs", "logo.svg"), "w", encoding="utf-8") as fh:
        fh.write(square)

    # ------------------------------------------------------------ monochrome
    TFs, PSs = place(50.0, 50.0, 100.0)
    favicon = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="32" height="32" role="img" aria-label="EXCLUSLAWYER mark, monochrome silhouette.">
  <title>EXCLUSLAWYER</title>
  <style>
    .mark {{ fill: {INK}; }}
    @media (prefers-color-scheme: dark) {{ .mark {{ fill: {PAPER}; }} }}
  </style>
  <g class="mark">
    <path d="{d_of(shapes["body"], TFs)}"/>
    <path d="{d_of(shapes["tail"], TFs)}"/>
  </g>
</svg>
"""
    with open(os.path.join(ROOT, "docs", "favicon.svg"), "w", encoding="utf-8") as fh:
        fh.write(favicon)

    # ---------------------------------------------------------------- banner
    TB, PB = place(185.0, 168.0, 152.0)
    banner = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 320" width="1200" height="320" role="img" aria-label="EXCLUSLAWYER — open-source legal intelligence. A cat that reads before it speaks. The curled tail quietly echoes a citation bracket.">
  <title>EXCLUSLAWYER — open-source legal intelligence</title>
  <style>{CSS}</style>
  <defs>
    <linearGradient id="wm" gradientUnits="userSpaceOnUse" x1="330" y1="0" x2="1130" y2="0">
      <stop class="shimmer" offset="0" stop-color="{AMBER}"/>
      <stop offset="0.5" stop-color="{PAPER}"/>
      <stop offset="1" stop-color="{AMBER}"/>
    </linearGradient>
    <radialGradient id="halo" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="{STEEL}" stop-opacity="0.20"/>
      <stop offset="1" stop-color="{STEEL}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="disc" cx="0.5" cy="0.40" r="0.64">
      <stop offset="0" stop-color="#FBF9F4"/>
      <stop offset="1" stop-color="#E4DED2"/>
    </radialGradient>
    <linearGradient id="rule" gradientUnits="userSpaceOnUse" x1="330" y1="0" x2="1100" y2="0">
      <stop offset="0" stop-color="{AMBER}" stop-opacity="0"/>
      <stop offset="0.5" stop-color="{AMBER}"/>
      <stop offset="1" stop-color="{AMBER}" stop-opacity="0"/>
    </linearGradient>
    <filter id="soft" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="3.2"/>
    </filter>
  </defs>

  <rect width="1200" height="320" fill="{INK}"/>
  <ellipse class="disc" cx="330" cy="168" rx="420" ry="220" fill="url(#halo)"/>

  <g font-family="Inter, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="11" letter-spacing="4" fill="{STEEL}">
    <text x="64" y="26">EXCLUSLAWYER &#183; ANIMAL IDENTITY 01</text>
    <text x="1136" y="26" text-anchor="end">THE REVIEWER &#183; CN / JP / KR / SG</text>
  </g>
  <line x1="64" y1="36" x2="1136" y2="36" stroke="{STEEL}" stroke-opacity="0.28" stroke-width="1"/>

  <circle cx="185" cy="168" r="93" fill="url(#disc)" stroke="{AMBER}" stroke-width="1.4" stroke-opacity="0.9"/>
  <circle cx="185" cy="168" r="97" fill="none" stroke="{STEEL}" stroke-opacity="0.22" stroke-width="1"/>
  {cat_markup(TB, PB)}

  <text x="330" y="152" font-family="Inter, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="60" font-weight="700" letter-spacing="7" fill="url(#wm)">EXCLUSLAWYER</text>
  <text x="333" y="192" font-family="Inter, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="13" letter-spacing="6" fill="{AMBER}">OPEN-SOURCE LEGAL INTELLIGENCE</text>
  <line class="rule" x1="330" y1="212" x2="1100" y2="212" stroke="url(#rule)" stroke-width="1"/>
  <text x="330" y="238" font-family="Inter, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="15" letter-spacing="1.5" fill="{STEEL}">Intelligence &#183; Precision &#183; Open by design</text>
  <g font-family="Georgia, 'Times New Roman', serif" font-style="italic" font-size="16" fill="#C9C2B4">
    <text x="330" y="272">A cat that reads before it speaks.</text>
    <text x="330" y="296">The curled tail quietly echoes a citation bracket.</text>
  </g>
</svg>
"""
    with open(os.path.join(ROOT, "docs", "banner.svg"), "w", encoding="utf-8") as fh:
        fh.write(banner)

    for f in ("assets/logo.svg", "docs/logo.svg", "docs/favicon.svg", "docs/banner.svg"):
        p = os.path.join(ROOT, f)
        print(f"{f}: {os.path.getsize(p)} bytes")


if __name__ == "__main__":
    main()
