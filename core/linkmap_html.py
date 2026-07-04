"""Render a folder link-map (F1) scan as a self-contained interactive HTML page.

The folder scan (:func:`core.blendscan.map_folder`) yields a
:class:`~core.blendscan.ScanResult`: a file->file :class:`~core.graph.DepGraph`
plus the per-file :class:`~core.blendscan.LinkRef` lists. This module turns that
into a graph the user can *see*: every ``.blend`` in the folder is a node, every
"A links a library from B" is a directed edge, and each node is classified so the
picture reads at a glance:

    root        a top-level file nothing else links (a scene)
    leaf        a pure asset library that links nothing
    intermediate    links things AND is linked
    external    exists but lives OUTSIDE the scanned folder (a shared library)
    missing     a linked target that is not on disk (a broken link)
    isolated    a .blend with no links either way

The output is ONE ``.html`` file with the graph data inlined as JSON and a small
vanilla-JS renderer: a force-directed layout with drag / pan / click-to-focus,
on-page zoom (+/−/Fit) buttons, Ctrl-gated wheel zoom (plain wheel pans), and a
**Hierarchical** toggle that lays the files out in dependency layers (depth comes
from :func:`assign_depths`, computed here so it's testable). No CDN, no external
assets — it opens offline in any browser. bpy-free and unit-tested; the operator
layer just writes the string to disk and opens it.

Datablock-level edge detail ("A links a Camera and an Object from B") is a
deliberate future extension — the edge already carries a ``count`` of link refs,
and :mod:`core.datablock_links` can supply the per-datablock breakdown later.
"""

from __future__ import annotations

import html
import json
import ntpath
import pathlib
from collections import Counter

# Node classification keys (also the CSS/legend keys in the page).
ROOT = "root"
LEAF = "leaf"
INTERMEDIATE = "intermediate"
EXTERNAL = "external"
MISSING = "missing"
ISOLATED = "isolated"

KIND_LABELS = {
    ROOT: "Root (top-level scene)",
    LEAF: "Asset / leaf (links nothing)",
    INTERMEDIATE: "Intermediate",
    EXTERNAL: "External (outside folder)",
    MISSING: "Missing (broken link)",
    ISOLATED: "Isolated (no links)",
}


def _name(path: str) -> str:
    return ntpath.basename(path) or path


def _key(path: str) -> str:
    """Case/separator-insensitive comparison key for a path string."""
    return str(path).replace("\\", "/").rstrip("/").lower()


def _existence(scan) -> dict[str, bool]:
    """Which graph nodes exist on disk, derived purely from the scan data (no disk
    access, so this stays unit-testable): a node exists if we scanned it (it was
    found by the folder walk, or found-but-unreadable) or any link that resolves to
    it reported ``exists``."""
    present: dict[str, bool] = {}
    for fkey in scan.refs:
        present[fkey] = True
    for fkey in scan.errors:  # readable-or-not, the file is on disk
        present[fkey] = True
    for refs in scan.refs.values():
        for ref in refs:
            target = ref.resolved_path or ref.stored_path
            if ref.exists:
                present[target] = True
            else:
                present.setdefault(target, False)
    return present


def classify_nodes(scan, root: pathlib.Path) -> dict[str, str]:
    """Map every graph node (a resolved .blend path) to one of the kind keys."""
    root_key = _key(str(pathlib.Path(root)))
    present = _existence(scan)
    targets = {e.target for e in scan.graph.edges}
    sources = {e.source for e in scan.graph.edges}

    def under_root(node: str) -> bool:
        nk = _key(node)
        return nk == root_key or nk.startswith(root_key + "/")

    kinds: dict[str, str] = {}
    for node in scan.graph.nodes:
        if not present.get(node, False):
            kinds[node] = MISSING
        elif not under_root(node):
            kinds[node] = EXTERNAL
        else:
            incoming = node in targets
            outgoing = node in sources
            if not incoming and not outgoing:
                kinds[node] = ISOLATED
            elif not incoming:
                kinds[node] = ROOT
            elif not outgoing:
                kinds[node] = LEAF
            else:
                kinds[node] = INTERMEDIATE
    return kinds


def aggregate_edges(scan) -> list[tuple[str, str, int]]:
    """Collapse the multigraph to unique (source, target, count) where ``count`` is
    how many library references A makes to B (usually 1; >1 means duplicate library
    blocks). Self-edges are dropped."""
    counts: Counter[tuple[str, str]] = Counter()
    for e in scan.graph.edges:
        if e.source != e.target:
            counts[(e.source, e.target)] += 1
    return [(s, t, n) for (s, t), n in counts.items()]


def cycle_edges(scan) -> set[tuple[str, str]]:
    """Directed (source, target) pairs that participate in a library cycle."""
    pairs: set[tuple[str, str]] = set()
    for cycle in scan.graph.find_cycles():
        for a, b in zip(cycle, cycle[1:]):
            pairs.add((a, b))
    return pairs


def assign_depths(node_ids, edges_agg) -> dict[str, int]:
    """Layer index per node for the hierarchical view, measured from the
    **root**: the top-level scene(s) that pull everything in sit at the top
    (0); a file sits one layer below anything that links it, so pure assets
    (linked by others, linking nothing themselves) sink to the bottom.
    Reverted 2026-07-04 (Group 9 #30, user's explicit re-confirm) back to
    this — its ORIGINAL direction — after a 2026-06-25 inversion to
    leaf-at-top; computed as the mirror of the leaf-based longest-outgoing-
    chain distance (same cycle-safe bounded relaxation as before, capped at
    one pass per node so a library **cycle** can't loop forever — cycle
    members still settle at a shared layer, flagged red regardless), just
    flipped top/bottom rather than a different algorithm."""
    ids = list(node_ids)
    idset = set(ids)
    succ: dict[str, list[str]] = {n: [] for n in ids}  # outgoing targets
    for s, t, *_ in edges_agg:
        if s in idset and t in idset and s != t:
            succ[s].append(t)
    depth_from_leaves = {n: 0 for n in ids}
    for _ in range(len(ids)):
        changed = False
        for n in ids:
            if succ[n]:
                d = max(depth_from_leaves[t] for t in succ[n]) + 1
                if d > depth_from_leaves[n]:
                    depth_from_leaves[n] = d
                    changed = True
        if not changed:
            break
    max_depth = max(depth_from_leaves.values(), default=0)
    return {n: max_depth - d for n, d in depth_from_leaves.items()}


def build_graph_data(scan, root: pathlib.Path, title: str | None = None) -> dict:
    """The JSON-serializable graph the page renders."""
    kinds = classify_nodes(scan, root)
    edges_agg = aggregate_edges(scan)
    in_cycle = cycle_edges(scan)
    depths = assign_depths(scan.graph.nodes, edges_agg)

    nodes = [
        {"id": node, "label": _name(node), "kind": kinds.get(node, INTERMEDIATE),
         "depth": depths.get(node, 0)}
        for node in sorted(scan.graph.nodes, key=_key)
    ]
    edges = [
        {"source": s, "target": t, "count": n, "cycle": (s, t) in in_cycle}
        for (s, t, n) in edges_agg
    ]

    counts = Counter(kinds.values())
    summary = {
        "files": len(scan.graph.nodes),
        "links": len(edges),
        "roots": counts.get(ROOT, 0),
        "leaves": counts.get(LEAF, 0),
        "external": counts.get(EXTERNAL, 0),
        "missing": counts.get(MISSING, 0),
        "isolated": counts.get(ISOLATED, 0),
        "cycles": len(scan.graph.find_cycles()),
        "unreadable": len(scan.errors),
    }
    return {
        "title": title or f"Link map: {root}",
        "root": str(root),
        "nodes": nodes,
        "edges": edges,
        "summary": summary,
    }


def build_link_map_html(scan, root: pathlib.Path, title: str | None = None) -> str:
    """Return a complete, self-contained interactive HTML document for the scan."""
    data = build_graph_data(scan, root, title)
    payload = json.dumps(data).replace("</", "<\\/")  # safe to inline in <script>
    return _PAGE.replace("__TITLE__", html.escape(data["title"])).replace(
        "__DATA__", payload
    )


# The page: data inlined as JSON, rendered by a small dependency-free
# force-directed canvas graph. Kept as one string so the operator can write it
# verbatim. No braces are Python-formatted here (we use .replace), so the JS/CSS
# braces are literal.
_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AssetDoctor — __TITLE__</title>
<style>
  :root { color-scheme: dark; }
  html, body { margin: 0; height: 100%; overflow: hidden;
    font: 13px/1.4 system-ui, "Segoe UI", sans-serif; background: #1b1d23; color: #e6e6e6; }
  #c { display: block; width: 100vw; height: 100vh; cursor: grab; }
  #c.grabbing { cursor: grabbing; }
  .panel { position: fixed; background: rgba(30,33,40,.92); border: 1px solid #3a3f4b;
    border-radius: 8px; padding: 10px 12px; backdrop-filter: blur(4px); }
  #head { top: 12px; left: 12px; max-width: 46vw; }
  #head h1 { margin: 0 0 4px; font-size: 14px; font-weight: 600; }
  #head .sub { color: #9aa3b2; font-size: 12px; word-break: break-all; }
  #head .stats { margin-top: 6px; font-size: 12px; }
  #head .stats b { color: #fff; }
  #legend { bottom: 12px; left: 12px; }
  #legend div { display: flex; align-items: center; gap: 7px; margin: 3px 0; }
  #legend .dot { width: 12px; height: 12px; border-radius: 50%; }
  #info { top: 12px; right: 12px; width: 320px; max-height: 80vh; overflow: auto; display: none; }
  #info h2 { margin: 0 0 6px; font-size: 13px; word-break: break-all; }
  #info .path { color: #9aa3b2; font-size: 11px; word-break: break-all; margin-bottom: 8px; }
  #info h3 { margin: 8px 0 3px; font-size: 11px; text-transform: uppercase;
    letter-spacing: .04em; color: #8b93a4; }
  #info ul { margin: 0; padding-left: 16px; }
  #info li { cursor: pointer; word-break: break-all; }
  #info li:hover { color: #fff; text-decoration: underline; }
  #info .none { color: #6b7280; font-style: italic; }
  #info .close { float: right; cursor: pointer; color: #9aa3b2; }
  #search { position: fixed; top: 12px; left: 50%; transform: translateX(-50%); }
  #search input { background: #11131a; border: 1px solid #3a3f4b; color: #e6e6e6;
    border-radius: 6px; padding: 6px 10px; width: 240px; font-size: 13px; }
  .hint { color: #6b7280; font-size: 11px; margin-top: 6px; }
  #tooltip { position: fixed; pointer-events: none; background: #11131a; border: 1px solid #3a3f4b;
    border-radius: 5px; padding: 3px 7px; font-size: 11px; display: none; max-width: 50vw;
    word-break: break-all; z-index: 10; }
  #controls { bottom: 12px; right: 12px; display: flex; gap: 6px; padding: 6px; }
  #controls button { background: #11131a; border: 1px solid #3a3f4b; color: #e6e6e6;
    border-radius: 6px; padding: 6px 11px; font-size: 13px; cursor: pointer; min-width: 34px; }
  #controls button:hover { background: #1b2030; }
  #controls button.active { background: #2a3550; border-color: #5b9cff; color: #fff; }
</style>
</head>
<body>
<canvas id="c"></canvas>
<div id="head" class="panel">
  <h1 id="title"></h1>
  <div class="sub" id="root"></div>
  <div class="stats" id="stats"></div>
  <div class="hint">Drag a node to move it · scroll to pan, Ctrl+scroll to zoom · drag background to pan · click a file to focus</div>
</div>
<div id="search" class="panel"><input id="q" type="search" placeholder="Find a file…" autocomplete="off"></div>
<div id="legend" class="panel"></div>
<div id="info" class="panel">
  <span class="close" id="infoClose">✕</span>
  <h2 id="iName"></h2>
  <div class="path" id="iPath"></div>
  <h3>Links to (this file → libraries)</h3>
  <ul id="iOut"></ul>
  <h3>Linked by (files that use this)</h3>
  <ul id="iIn"></ul>
</div>
<div id="tooltip"></div>
<div id="controls" class="panel">
  <button id="zin" title="Zoom in">+</button>
  <button id="zout" title="Zoom out">−</button>
  <button id="zfit" title="Fit graph to view">Fit</button>
  <button id="tree" title="Toggle hierarchical (layered) layout">Hierarchical</button>
</div>
<script>
const DATA = __DATA__;
const COLORS = {
  root: "#5b9cff", leaf: "#46c79a", intermediate: "#c8b04a",
  external: "#9b7fd4", missing: "#e0594b", isolated: "#7a8190"
};
const KIND_LABELS = {
  root: "Root (top-level scene)", leaf: "Asset / leaf (links nothing)",
  intermediate: "Intermediate (links & linked)", external: "External (outside folder)",
  missing: "Missing (broken link)", isolated: "Isolated (no links)"
};

const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");
let DPR = window.devicePixelRatio || 1;

// ---- model ----
const nodes = DATA.nodes.map(n => ({...n, x: 0, y: 0, vx: 0, vy: 0, deg: 0}));
const byId = new Map(nodes.map(n => [n.id, n]));
const edges = DATA.edges.filter(e => byId.has(e.source) && byId.has(e.target))
  .map(e => ({...e, s: byId.get(e.source), t: byId.get(e.target)}));
edges.forEach(e => { e.s.deg++; e.t.deg++; });

// Seed positions on a circle so the layout opens out instead of exploding.
const N = nodes.length || 1;
nodes.forEach((n, i) => {
  const a = (i / N) * Math.PI * 2;
  const r = 30 + 14 * Math.sqrt(N);
  n.x = Math.cos(a) * r + (Math.random() - 0.5) * 20;
  n.y = Math.sin(a) * r + (Math.random() - 0.5) * 20;
});

// ---- camera ----
let scale = 1, ox = 0, oy = 0;
function resize() {
  DPR = window.devicePixelRatio || 1;
  canvas.width = innerWidth * DPR; canvas.height = innerHeight * DPR;
  canvas.style.width = innerWidth + "px"; canvas.style.height = innerHeight + "px";
}
window.addEventListener("resize", resize); resize();
ox = innerWidth / 2; oy = innerHeight / 2;
const toScreen = p => ({ x: p.x * scale + ox, y: p.y * scale + oy });
const radius = n => 5 + Math.min(7, n.deg);

// ---- physics (simple force-directed; O(n^2), fine for typical project sizes) ----
let energy = 1;
function step() {
  const REP = 7000, SPRING = 0.02, LEN = 130, GRAV = 0.012, DAMP = 0.85;
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i];
    if (a.pin) continue;
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j];
      let dx = a.x - b.x, dy = a.y - b.y;
      let d2 = dx*dx + dy*dy || 0.01;
      const f = REP / d2;
      const d = Math.sqrt(d2);
      const fx = (dx / d) * f, fy = (dy / d) * f;
      a.vx += fx; a.vy += fy;
      if (!b.pin) { b.vx -= fx; b.vy -= fy; }
    }
  }
  for (const e of edges) {
    let dx = e.t.x - e.s.x, dy = e.t.y - e.s.y;
    const d = Math.sqrt(dx*dx + dy*dy) || 0.01;
    const f = (d - LEN) * SPRING;
    const fx = (dx / d) * f, fy = (dy / d) * f;
    if (!e.s.pin) { e.s.vx += fx; e.s.vy += fy; }
    if (!e.t.pin) { e.t.vx -= fx; e.t.vy -= fy; }
  }
  let moved = 0;
  for (const n of nodes) {
    if (n.pin) { n.vx = n.vy = 0; continue; }
    n.vx -= n.x * GRAV; n.vy -= n.y * GRAV;
    n.vx *= DAMP; n.vy *= DAMP;
    n.x += n.vx; n.y += n.vy;
    moved += Math.abs(n.vx) + Math.abs(n.vy);
  }
  energy = moved / N;
}

// ---- selection / search ----
let selected = null, query = "";
function neighborsOf(n) {
  const out = [], inc = [];
  for (const e of edges) {
    if (e.s === n) out.push(e.t);
    if (e.t === n) inc.push(e.s);
  }
  return { out, inc };
}
function highlightSet(n) {
  const set = new Set([n]);
  for (const e of edges) {
    if (e.s === n) set.add(e.t);
    if (e.t === n) set.add(e.s);
  }
  return set;
}

// ---- draw ----
function draw() {
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  ctx.clearRect(0, 0, innerWidth, innerHeight);
  const hi = selected ? highlightSet(selected) : null;
  const qmatch = n => query && n.label.toLowerCase().includes(query);

  // edges
  for (const e of edges) {
    const a = toScreen(e.s), b = toScreen(e.t);
    const active = !hi || hi.has(e.s) && hi.has(e.t);
    ctx.strokeStyle = e.cycle ? (active ? "#e0594b" : "rgba(224,89,75,.18)")
                              : (active ? "rgba(150,160,180,.55)" : "rgba(150,160,180,.08)");
    ctx.lineWidth = (e.count > 1 ? 2.2 : 1.1) * (e.cycle ? 1.4 : 1);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    // arrowhead near target
    const ang = Math.atan2(b.y - a.y, b.x - a.x);
    const tr = radius(e.t) + 2;
    const hx = b.x - Math.cos(ang) * tr, hy = b.y - Math.sin(ang) * tr;
    const ah = 7;
    ctx.fillStyle = ctx.strokeStyle;
    ctx.beginPath();
    ctx.moveTo(hx, hy);
    ctx.lineTo(hx - Math.cos(ang - 0.4) * ah, hy - Math.sin(ang - 0.4) * ah);
    ctx.lineTo(hx - Math.cos(ang + 0.4) * ah, hy - Math.sin(ang + 0.4) * ah);
    ctx.closePath(); ctx.fill();
  }
  // nodes
  for (const n of nodes) {
    const p = toScreen(n), r = radius(n);
    const dim = hi && !hi.has(n);
    ctx.globalAlpha = dim ? 0.18 : 1;
    ctx.fillStyle = COLORS[n.kind] || "#888";
    ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fill();
    if (n === selected || qmatch(n)) {
      ctx.lineWidth = 2.5; ctx.strokeStyle = "#fff";
      ctx.beginPath(); ctx.arc(p.x, p.y, r + 3, 0, Math.PI * 2); ctx.stroke();
    }
    if (scale > 0.5 || n === selected || qmatch(n) || (hi && hi.has(n))) {
      ctx.fillStyle = dim ? "#6b7280" : "#e6e6e6";
      ctx.font = "12px system-ui";
      ctx.fillText(n.label, p.x + r + 3, p.y + 4);
    }
    ctx.globalAlpha = 1;
  }
}

function frame() {
  if (!treeMode && energy > 0.05 && !dragNode) { for (let k = 0; k < 2; k++) step(); }
  draw();
  requestAnimationFrame(frame);
}

// ---- interaction ----
let dragNode = null, panning = false, lastX = 0, lastY = 0, downX = 0, downY = 0, moved = false;
function nodeAt(sx, sy) {
  for (let i = nodes.length - 1; i >= 0; i--) {
    const n = nodes[i], p = toScreen(n);
    const r = radius(n) + 4;
    if ((sx - p.x) ** 2 + (sy - p.y) ** 2 <= r * r) return n;
  }
  return null;
}
canvas.addEventListener("mousedown", ev => {
  downX = lastX = ev.clientX; downY = lastY = ev.clientY; moved = false;
  const n = nodeAt(ev.clientX, ev.clientY);
  if (n) { dragNode = n; n.pin = true; } else { panning = true; canvas.classList.add("grabbing"); }
});
window.addEventListener("mousemove", ev => {
  const dx = ev.clientX - lastX, dy = ev.clientY - lastY;
  lastX = ev.clientX; lastY = ev.clientY;
  if (Math.abs(ev.clientX - downX) + Math.abs(ev.clientY - downY) > 4) moved = true;
  if (dragNode) { dragNode.x += dx / scale; dragNode.y += dy / scale; energy = 1; }
  else if (panning) { ox += dx; oy += dy; }
  else {
    const n = nodeAt(ev.clientX, ev.clientY);
    const tip = document.getElementById("tooltip");
    if (n) { tip.style.display = "block"; tip.textContent = n.id;
      tip.style.left = (ev.clientX + 12) + "px"; tip.style.top = (ev.clientY + 12) + "px"; }
    else tip.style.display = "none";
  }
});
window.addEventListener("mouseup", ev => {
  if (dragNode) { dragNode.pin = treeMode; if (!moved) select(dragNode); dragNode = null; }
  else if (panning && !moved) { select(null); }
  panning = false; canvas.classList.remove("grabbing");
});
function zoomAt(cx, cy, factor) {
  ox = cx - (cx - ox) * factor; oy = cy - (cy - oy) * factor; scale *= factor;
}
canvas.addEventListener("wheel", ev => {
  ev.preventDefault();
  if (ev.ctrlKey || ev.metaKey) {
    // Ctrl/⌘ + wheel = zoom, softened so it isn't grabby; centered on the cursor.
    zoomAt(ev.clientX, ev.clientY, ev.deltaY < 0 ? 1.08 : 1 / 1.08);
  } else {
    // Plain wheel pans, so scrolling near the graph doesn't yank the zoom.
    ox -= ev.deltaX; oy -= ev.deltaY;
  }
}, { passive: false });

// ---- zoom / fit / hierarchical-layout controls ----
function fitView() {
  if (!nodes.length) return;
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  for (const n of nodes) {
    minx = Math.min(minx, n.x); miny = Math.min(miny, n.y);
    maxx = Math.max(maxx, n.x); maxy = Math.max(maxy, n.y);
  }
  const w = (maxx - minx) || 1, h = (maxy - miny) || 1, margin = 90;
  scale = Math.min((innerWidth - margin) / w, (innerHeight - margin) / h, 2.5);
  if (!isFinite(scale) || scale <= 0) scale = 1;
  ox = innerWidth / 2 - ((minx + maxx) / 2) * scale;
  oy = innerHeight / 2 - ((miny + maxy) / 2) * scale;
}
let treeMode = false;
function applyTree() {
  // Lay nodes out in rows by dependency depth (roots at the top), spread left→right.
  const layers = new Map();
  for (const n of nodes) {
    const d = n.depth || 0;
    if (!layers.has(d)) layers.set(d, []);
    layers.get(d).push(n);
  }
  const vgap = 150, hgap = 130;
  for (const [d, layer] of layers) {
    layer.sort((a, b) => a.label.localeCompare(b.label));
    const span = (layer.length - 1) * hgap;
    layer.forEach((n, i) => { n.x = i * hgap - span / 2; n.y = d * vgap; n.vx = n.vy = 0; });
  }
}
function setTree(on) {
  treeMode = on;
  document.getElementById("tree").classList.toggle("active", on);
  if (on) { applyTree(); for (const n of nodes) n.pin = true; fitView(); }
  else { for (const n of nodes) n.pin = false; energy = 1; }
}
document.getElementById("zin").onclick = () => zoomAt(innerWidth / 2, innerHeight / 2, 1.2);
document.getElementById("zout").onclick = () => zoomAt(innerWidth / 2, innerHeight / 2, 1 / 1.2);
document.getElementById("zfit").onclick = () => fitView();
document.getElementById("tree").onclick = () => setTree(!treeMode);

// ---- info panel ----
function select(n) {
  selected = n;
  const info = document.getElementById("info");
  if (!n) { info.style.display = "none"; return; }
  info.style.display = "block";
  document.getElementById("iName").textContent = n.label;
  document.getElementById("iName").style.color = COLORS[n.kind];
  document.getElementById("iPath").textContent = n.id + "  ·  " + (KIND_LABELS[n.kind] || n.kind);
  const { out, inc } = neighborsOf(n);
  fillList("iOut", out); fillList("iIn", inc);
}
function fillList(id, arr) {
  const ul = document.getElementById(id); ul.innerHTML = "";
  if (!arr.length) { const li = document.createElement("li");
    li.className = "none"; li.textContent = "(none)"; ul.appendChild(li); return; }
  for (const m of arr) {
    const li = document.createElement("li");
    li.textContent = m.label; li.style.color = COLORS[m.kind];
    li.onclick = () => { select(m); centerOn(m); };
    ul.appendChild(li);
  }
}
function centerOn(n) { ox = innerWidth / 2 - n.x * scale; oy = innerHeight / 2 - n.y * scale; }
document.getElementById("infoClose").onclick = () => select(null);
document.getElementById("q").addEventListener("input", e => {
  query = e.target.value.trim().toLowerCase();
  const hit = query && nodes.find(n => n.label.toLowerCase().includes(query));
  if (hit) centerOn(hit);
});

// ---- chrome ----
document.getElementById("title").textContent = DATA.title;
document.getElementById("root").textContent = DATA.root;
const s = DATA.summary;
document.getElementById("stats").innerHTML =
  "<b>" + s.files + "</b> files · <b>" + s.links + "</b> links · " +
  s.roots + " root · " + s.leaves + " asset · " + s.external + " external · " +
  "<span style='color:#e0594b'>" + s.missing + " missing</span>" +
  (s.cycles ? " · <span style='color:#e0594b'>" + s.cycles + " cycle(s)</span>" : "") +
  (s.unreadable ? " · " + s.unreadable + " unreadable" : "");
const legend = document.getElementById("legend");
for (const k of ["root", "leaf", "intermediate", "external", "missing", "isolated"]) {
  const row = document.createElement("div");
  row.innerHTML = "<span class='dot' style='background:" + COLORS[k] + "'></span>" + KIND_LABELS[k];
  legend.appendChild(row);
}

frame();
</script>
</body>
</html>
"""
