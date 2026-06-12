"""F5 - Resource Analyzer: estimate what is using System Memory / Video Memory /
Disk, broken down by datablock type (each datablock counted once).

Read-only. Estimates are labeled as such in the UI; the Profile Render button
(separate, M7 step 4) captures real engine peak memory.
"""

import os

import bpy

from ..core.resource import (
    human_bytes,
    image_estimate,
    mesh_estimate,
    peak_process_ram_bytes,
)
from ..core.resource_tree import build_resource_tree
from ..core.tree import nodes_to_json, top_level_keys

RESOURCE_PROP = "assetdoctor_resource_tree"
RESOURCE_EXPANDED = "assetdoctor_resource_expanded"


def _image_disk(img) -> int:
    if img.packed_file is not None:
        return int(getattr(img.packed_file, "size", 0) or 0)
    path = bpy.path.abspath(img.filepath) if img.filepath else ""
    try:
        return os.path.getsize(path) if path and os.path.isfile(path) else 0
    except OSError:
        return 0


def _gather(context):
    items = []
    for img in bpy.data.images:
        w, h = (img.size[0], img.size[1]) if len(img.size) >= 2 else (0, 0)
        est = image_estimate({"width": w, "height": h, "depth": img.depth})
        items.append({
            "type": "Image", "name": img.name,
            "ram": est["ram"], "vram": est["vram"], "disk": _image_disk(img),
            "users": img.users,
        })
    for me in bpy.data.meshes:
        est = mesh_estimate({
            "verts": len(me.vertices), "edges": len(me.edges),
            "loops": len(me.loops), "polys": len(me.polygons),
        })
        items.append({
            "type": "Mesh", "name": me.name,
            "ram": est["ram"], "vram": est["vram"], "disk": 0, "users": me.users,
        })
    return items


class ASSETDOCTOR_OT_analyze_resources(bpy.types.Operator):
    bl_idname = "assetdoctor.analyze_resources"
    bl_label = "Analyze Resource Usage"
    bl_description = (
        "Estimate System Memory / Video Memory and disk use by datablock type "
        "(estimates; see the Resource panel)"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ..log import get_logger

        log = get_logger()
        nodes, totals = build_resource_tree(_gather(context))

        wm = context.window_manager
        setattr(wm, RESOURCE_PROP, nodes_to_json(nodes))
        setattr(wm, RESOURCE_EXPANDED, "\n".join(top_level_keys(nodes)))

        msg = (f"Estimated totals — RAM {human_bytes(totals['ram'])}, "
               f"VRAM {human_bytes(totals['vram'])}, disk {human_bytes(totals['disk'])}")
        log.info("F5 %s", msg)
        self.report({"INFO"}, msg + " (estimates; see Resource panel)")
        return {"FINISHED"}


class ASSETDOCTOR_OT_profile_render(bpy.types.Operator):
    bl_idname = "assetdoctor.profile_render"
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
        context.window_manager.assetdoctor_profiled_ram = text
        log.info("F5 profile render: peak process RAM = %s", text)
        self.report({"INFO"}, f"Render done — real peak RAM: {text} (whole process)")
        return {"FINISHED"}
