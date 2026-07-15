"""F5 - Resource Analyzer: estimate what is using System Memory / Video Memory /
Disk, broken down by datablock type (each datablock counted once).

Read-only. Estimates are labeled as such in the UI; the Profile Render button
(separate, M7 step 4) captures real engine peak memory.
"""

import json
import os

import bpy

from ..core.resource import (
    human_bytes,
    image_estimate,
    mesh_estimate,
    peak_process_ram_bytes,
)
from ..core.resource_tree import SORT_KEYS, build_resource_tree
from ..core.tree import nodes_to_json, top_level_keys
from .progress import ModalProgressMixin

RESOURCE_PROP = "filelink_resource_tree"
RESOURCE_EXPANDED = "filelink_resource_expanded"
RESOURCE_TOTALS = "filelink_resource_totals"
RESOURCE_ITEMS = "filelink_resource_items_json"

_EST_CHUNK = 64  # datablocks estimated between progress yields


def _image_disk(img) -> int:
    if img.packed_file is not None:
        return int(getattr(img.packed_file, "size", 0) or 0)
    path = bpy.path.abspath(img.filepath) if img.filepath else ""
    try:
        return os.path.getsize(path) if path and os.path.isfile(path) else 0
    except OSError:
        return 0


def _gather_steps(context):
    """Estimate RAM/VRAM/disk for every image + mesh, yielding ``(fraction,
    status)`` every ``_EST_CHUNK``. Returns the ``items`` list.

    Skips datablocks flagged risky by :func:`extract.datablock_risk_reason` —
    reading ``img.size`` / ``len(me.vertices)`` on data that's missing, an
    override, or linked from a missing library is the same uncatchable native
    crash the fingerprint scans guard against (PSM_Stage v0.3.9: this was the
    ONE geometry-reading path in Analyze All that still didn't, so the run
    crashed here on the final step). A skipped block just isn't counted — the
    estimate is a footprint reading, not a correctness check."""
    from .extract import datablock_risk_reason

    images = list(bpy.data.images)
    meshes = list(bpy.data.meshes)
    total = (len(images) + len(meshes)) or 1

    items = []
    done = 0
    for img in images:
        if not datablock_risk_reason(img):
            w, h = (img.size[0], img.size[1]) if len(img.size) >= 2 else (0, 0)
            est = image_estimate({"width": w, "height": h, "depth": img.depth})
            items.append({
                "type": "Image", "name": img.name,
                "ram": est["ram"], "vram": est["vram"], "disk": _image_disk(img),
                "users": img.users,
            })
        done += 1
        if done % _EST_CHUNK == 0:
            yield (0.85 * done / total, f"Estimating resources {done}/{total}…")
    for me in meshes:
        if not datablock_risk_reason(me):
            est = mesh_estimate({
                "verts": len(me.vertices), "edges": len(me.edges),
                "loops": len(me.loops), "polys": len(me.polygons),
            })
            items.append({
                "type": "Mesh", "name": me.name,
                "ram": est["ram"], "vram": est["vram"], "disk": 0, "users": me.users,
            })
        done += 1
        if done % _EST_CHUNK == 0:
            yield (0.85 * done / total, f"Estimating resources {done}/{total}…")
    return items


def _gather(context):
    """Synchronous gather (drains :func:`_gather_steps`). Kept for tests/scripting."""
    gen = _gather_steps(context)
    try:
        while True:
            next(gen)
    except StopIteration as done:
        return done.value


class FILELINK_OT_analyze_resources(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "filelink.analyze_resources"
    bl_label = "Analyze Resource Usage"
    bl_description = (
        "Estimate System Memory / Video Memory and disk use by datablock type "
        "(estimates; see the Resource panel)"
    )
    bl_options = {"REGISTER"}

    def cancel_message(self):
        return "Resource analysis cancelled"

    def run_steps(self, context):
        from ..log import get_logger

        log = get_logger()
        items = yield from _gather_steps(context)

        yield (0.9, "Building resource tree…")
        wm = context.window_manager
        setattr(wm, RESOURCE_ITEMS, json.dumps(items))
        nodes, totals = build_resource_tree(items, sort_by=wm.filelink_resource_sort)
        setattr(wm, RESOURCE_PROP, nodes_to_json(nodes))
        setattr(wm, RESOURCE_EXPANDED, "\n".join(top_level_keys(nodes)))
        from .report_store import rebuild_resource_rows
        rebuild_resource_rows(wm)

        msg = (f"Estimated totals — RAM {human_bytes(totals['ram'])}, "
               f"VRAM {human_bytes(totals['vram'])}, disk {human_bytes(totals['disk'])}")
        # Persisted (not just the transient operator-report popup) so the
        # Analyze button can show the same line inline after the popup fades
        # (negative-output principle — a result must stay visible).
        setattr(wm, RESOURCE_TOTALS, msg)
        # Raw bytes for the Health dashboard (decimal strings — IntProperty is
        # 32-bit and overflows past ~2 GB). VRAM is the only VRAM figure we
        # have (Blender doesn't expose real VRAM), so the dashboard reads it here.
        wm.filelink_resource_ram_b = str(totals["ram"])
        wm.filelink_resource_vram_b = str(totals["vram"])
        log.info("F5 %s", msg)
        self.report({"INFO"}, msg + " (estimates; see Resource panel)")


class FILELINK_OT_resource_sort_by(bpy.types.Operator):
    """Re-sort the Resource Usage type groups by a column header click
    (docs/TODO.md #15, 2026-06-27). Cheap: re-groups the already-gathered
    ``items`` cached by the last scan — never re-walks bpy.data."""

    bl_idname = "filelink.resource_sort_by"
    bl_label = "Sort Resource Usage"
    bl_description = "Re-sort the type groups by this column (RAM/VRAM/disk)"
    bl_options = {"INTERNAL"}

    metric: bpy.props.EnumProperty(
        items=[(k.upper(), k.upper(), "") for k in SORT_KEYS], default="RAM")  # type: ignore[valid-type]

    def execute(self, context):
        wm = context.window_manager
        raw = getattr(wm, RESOURCE_ITEMS, "")
        if not raw:
            return {"CANCELLED"}
        wm.filelink_resource_sort = self.metric.lower()
        items = json.loads(raw)
        nodes, _totals = build_resource_tree(items, sort_by=wm.filelink_resource_sort)
        setattr(wm, RESOURCE_PROP, nodes_to_json(nodes))
        setattr(wm, RESOURCE_EXPANDED, "\n".join(top_level_keys(nodes)))
        from .report_store import rebuild_resource_rows
        rebuild_resource_rows(wm)
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class FILELINK_OT_profile_render(bpy.types.Operator):
    bl_idname = "filelink.profile_render"
    bl_label = "Profile Render (real RAM)"
    bl_description = (
        "Render the current frame and report Blender's REAL peak system RAM "
        "(whole process), to complement the estimates. Slow on heavy scenes. "
        "Note: real VRAM is not exposed by Blender's Python API"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ..log import get_logger

        log = get_logger()
        if context.scene.camera is None:
            self.report({"ERROR"}, "Scene has no camera to render from")
            return {"CANCELLED"}
        try:
            bpy.ops.render.render(write_still=False)
        except RuntimeError as exc:
            self.report({"ERROR"}, f"Render failed: {exc}")
            return {"CANCELLED"}

        peak = peak_process_ram_bytes()
        text = human_bytes(peak) if peak else "unavailable"
        context.window_manager.filelink_profiled_ram = text
        # Raw bytes for the Health dashboard's Render RAM delta (decimal string).
        context.window_manager.filelink_profiled_ram_b = str(peak) if peak else ""
        log.info("F5 profile render: peak process RAM = %s", text)
        self.report({"INFO"}, f"Render done — real peak RAM: {text} (whole process)")
        return {"FINISHED"}
