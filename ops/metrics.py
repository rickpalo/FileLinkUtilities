"""Health-dashboard metrics + a per-file baseline for showing deltas as the
addon works through issues (v0.3.x, project_flow_redesign).

Baseline is "since you opened the file": the ``load_post`` handler clears
``wm.filelink_metrics_baseline`` on every file open, and each metric is
baselined lazily the first time it becomes *known* — instant metrics (size on
disk, linked libraries) on the first dashboard draw after a load, scan-derived
metrics (render RAM/VRAM, duplicate counts, missing/broken counts, orphans) the
first time their own scan produces a value worth surfacing. Later draws show
``baseline → now`` for anything that has moved.

This module reads ``bpy.data`` and window-manager scan results, so it is NOT
bpy-free and lives under ``ops/`` rather than ``core/``. Raw byte counts for
RAM/VRAM are stashed by their operators as decimal STRINGS (Blender's
``IntProperty`` is 32-bit and overflows past ~2 GB); everything here parses
them back with :func:`_as_int`.
"""

from __future__ import annotations

import json
import os

import bpy

from ..core.resource import human_bytes

BASELINE_PROP = "filelink_metrics_baseline"

# key -> (label, unit, reveal_nonzero)
#   unit:            "bytes" formats via human_bytes, "count" is a plain integer.
#   reveal_nonzero:  True  -> only surfaces once a scan finds a non-zero value
#                            (then keeps showing, e.g. "14 → 0 ✓", once baselined);
#                    False -> always shown (the instant metrics).
_SPEC: dict[str, tuple[str, str, bool]] = {
    "size_on_disk": ("Size on disk", "bytes", False),
    "linked_libs": ("Linked libs", "count", False),
    "render_ram": ("Render RAM", "bytes", False),
    "vram": ("VRAM", "bytes", False),
    "dup_materials": ("Dup materials", "count", True),
    "dup_meshes": ("Dup meshes", "count", True),
    "missing_tex": ("Missing tex", "count", True),
    "broken_libs": ("Broken libs", "count", True),
    "orphans": ("Orphans", "count", True),
}
ORDER = list(_SPEC)


def _as_int(wm, prop: str) -> int:
    try:
        return int(getattr(wm, prop, "") or 0)
    except (ValueError, TypeError):
        return 0


def size_on_disk() -> tuple[int, int]:
    """``(local_bytes, linked_bytes)`` on disk for THIS project's directly-
    referenced files. Local = the current ``.blend`` + its own (non-linked)
    external image files. Linked = every linked library ``.blend`` + external
    images owned by a library. Packed images already count inside the
    ``.blend``. Fast — one ``os.path.getsize`` (stat) per unique path, no BAT
    walk."""
    seen: set[str] = set()

    def size_of(path: str) -> int:
        try:
            resolved = os.path.normpath(bpy.path.abspath(path))
        except Exception:
            return 0
        if not resolved or resolved in seen:
            return 0
        seen.add(resolved)
        try:
            return os.path.getsize(resolved) if os.path.isfile(resolved) else 0
        except OSError:
            return 0

    local = linked = 0
    if bpy.data.filepath:
        local += size_of(bpy.data.filepath)
    for lib in bpy.data.libraries:
        if lib.filepath:
            linked += size_of(lib.filepath)
    for img in bpy.data.images:
        if img.packed_file is not None:
            continue
        if getattr(img, "source", "") in {"FILE", "SEQUENCE", "TILED"} and img.filepath:
            nbytes = size_of(img.filepath)
            if img.library is not None:
                linked += nbytes
            else:
                local += nbytes
    return local, linked


def library_stats() -> tuple[int, int, int]:
    """(total, missing, absolute) over ``bpy.data.libraries`` — same instant,
    no-scan health the old Current File Data line showed."""
    total = missing = absolute = 0
    for lib in bpy.data.libraries:
        fp = lib.filepath
        if not fp:
            continue
        total += 1
        if not fp.startswith("//"):
            absolute += 1
        try:
            if not os.path.isfile(bpy.path.abspath(fp)):
                missing += 1
        except Exception:
            missing += 1
    return total, missing, absolute


def current(wm) -> dict[str, int]:
    """``metric_key -> value`` for every metric currently *known*. A key absent
    from the dict means "not scanned/knowable yet" — the dashboard neither
    draws nor baselines it. ``linked_libs`` carries its missing/absolute detail
    in the sibling keys ``libs_missing`` / ``libs_absolute`` (not their own
    dashboard rows)."""
    from .report_store import data_prop

    local, linked = size_on_disk()
    cur: dict[str, int] = {"size_on_disk": local + linked,
                           "size_local": local, "size_linked": linked}
    total, missing, absolute = library_stats()
    cur["linked_libs"] = total
    cur["libs_missing"] = missing
    cur["libs_absolute"] = absolute

    if getattr(wm, "filelink_profiled_ram_b", ""):
        cur["render_ram"] = _as_int(wm, "filelink_profiled_ram_b")
    if getattr(wm, "filelink_resource_vram_b", ""):
        cur["vram"] = _as_int(wm, "filelink_resource_vram_b")
    if wm.filelink_mat_scanned:
        cur["dup_materials"] = wm.filelink_mat_removable
    if wm.filelink_geo_scanned:
        cur["dup_meshes"] = wm.filelink_geo_removable
    if wm.filelink_tex_scanned:
        cur["missing_tex"] = len(wm.filelink_broken_imgs)
    if getattr(wm, data_prop("f7links"), ""):
        cur["broken_libs"] = len(wm.filelink_broken_libs)
    if getattr(wm, data_prop("f4"), ""):
        cur["orphans"] = len(wm.filelink_orphan_rows)
    return cur


def sync_baseline(wm, cur: dict[str, int]) -> dict[str, int]:
    """Merge any newly-eligible metric into the stored baseline and return the
    baseline dict. A metric is baselined the first time it is known; a
    ``reveal_nonzero`` metric waits until that first value is actually non-zero
    (so its baseline captures e.g. the "14" duplicates, not a premature 0).
    Writes the WM prop back only when something new was added — steady-state
    draws don't write. (Writing a WM prop from ``draw()`` is the same pattern
    the inline-report/pickers already use here; it's a data prop, no depsgraph
    touch.)"""
    try:
        base: dict[str, int] = json.loads(getattr(wm, BASELINE_PROP, "") or "{}")
    except (ValueError, TypeError):
        base = {}
    changed = False
    for key, value in cur.items():
        if key in base or key not in _SPEC:
            continue
        if _SPEC[key][2] and not value:  # reveal_nonzero: wait for a non-zero
            continue
        base[key] = value
        changed = True
    if changed:
        setattr(wm, BASELINE_PROP, json.dumps(base))
    return base


def display_rows(cur: dict[str, int], base: dict[str, int]
                 ) -> list[tuple[str, str, str, int | None, int | None]]:
    """The dashboard's display rows in fixed order: ``(key, label, unit,
    baseline, current)`` — pure (no I/O), given already-computed ``cur``/
    ``base`` dicts, so the panel can gather metrics ONCE per draw and still read
    ``cur`` for the size/library detail lines. ``baseline`` is None when
    unchanged-from-known or never baselined; ``current`` is None when the metric
    is no longer known. A ``reveal_nonzero`` metric with neither a baseline nor
    a non-zero current is omitted entirely."""
    out: list[tuple[str, str, str, int | None, int | None]] = []
    for key in ORDER:
        label, unit, reveal_nonzero = _SPEC[key]
        cur_val = cur.get(key)
        base_val = base.get(key)
        if reveal_nonzero and base_val is None and not cur_val:
            continue
        out.append((key, label, unit, base_val, cur_val))
    return out


def rows(wm) -> list[tuple[str, str, str, int | None, int | None]]:
    """Convenience: gather + baseline + display in one call (used by tests and
    any caller that doesn't need ``cur`` separately)."""
    cur = current(wm)
    base = sync_baseline(wm, cur)
    return display_rows(cur, base)


def status(key: str, base: int | None, cur: int | None, *, missing: int = 0) -> str:
    """"good" | "attention" | "neutral" — drives the row's colored status dot
    (and red text on "attention"). An issue/duplicate metric reads attention
    while non-zero and good once cleared to 0; a footprint metric reads good
    once it has dropped below its baseline; ``linked_libs`` is attention while
    any library is missing. Everything else is neutral (no dot)."""
    if key == "linked_libs":
        return "attention" if missing else "neutral"
    if cur is None:
        return "neutral"
    if _SPEC.get(key, ("", "", False))[2]:  # reveal_nonzero -> it's an issue count
        return "good" if cur == 0 else "attention"
    if base is not None and cur < base:  # footprint dropped since baseline
        return "good"
    return "neutral"


def fmt(unit: str, value: int) -> str:
    return human_bytes(value) if unit == "bytes" else str(value)


def delta_str(unit: str, base: int, cur: int) -> str:
    """Signed change, e.g. ``-1.7 GB`` or ``-14`` (uses a real minus sign). A
    reduction (cur < base) is the win, so it reads negative."""
    diff = cur - base
    sign = "+" if diff > 0 else "−"
    magnitude = human_bytes(abs(diff)) if unit == "bytes" else str(abs(diff))
    return f"{sign}{magnitude}"
