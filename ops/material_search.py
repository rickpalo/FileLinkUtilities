"""docs/TODO.md #22 — Find Material Across Files: recursively search every
.blend under a chosen folder for a material name (wildcard or substring),
entirely offline via BAT (core.material_search / core.blendscan) — no
Blender launch, no library linking, matching this project's existing
folder-wide-scan house style (core/blendscan.py's F1 link map).
"""

from __future__ import annotations

import os

import bpy

from ..core.blendscan import iter_blend_files
from ..core.material_search import find_materials
from ..core.report import Finding, Report
from .progress import ModalProgressMixin


class FILELINK_OT_search_material(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "filelink.search_material"
    bl_label = "Find Material Across Files"
    bl_description = ("Recursively search every .blend under the chosen folder for a "
                      "material name (wildcard or substring), entirely offline")
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        return bool(scene.filelink_scan_dir and scene.filelink_material_search_pattern)

    def cancel_message(self):
        return "Find Material Across Files cancelled"

    def run_steps(self, context):
        import pathlib

        from ..core.blendscan import bat_available

        scene = context.scene
        root = bpy.path.abspath(scene.filelink_scan_dir)
        pattern = scene.filelink_material_search_pattern

        if not (root and os.path.isdir(root)):
            self.report({"ERROR"}, "Choose a valid folder above (Map a Folder's Project Folder)")
            return
        if not bat_available():
            self.report({"ERROR"}, "Blender Asset Tracer unavailable; reinstall the extension")
            return

        files = list(iter_blend_files(pathlib.Path(root)))
        total = len(files) or 1
        report = Report(title=f"Find Material: '{pattern}'", feature="matsearch")
        matched_files = 0
        total_hits = 0
        unreadable: list[str] = []

        for i, blend in enumerate(files, 1):
            path = str(blend)
            try:
                hits = find_materials(blend, pattern)
            except Exception as exc:
                unreadable.append(f"{path} — {type(exc).__name__}: {exc}")
                hits = None
            if hits:
                matched_files += 1
                total_hits += len(hits)
                report.add(Finding(
                    category="material_match",
                    message=f"{len(hits)} material(s) matching '{pattern}' in "
                            f"{os.path.basename(path)}",
                    severity="info",
                    items=hits,  # bare names -- not "Material/Name", nothing here is
                                 # selectable (the file isn't open), see module docstring
                    data={"path": path},
                ))
            if i % 5 == 0 or i == total:
                yield (i / total, f"Scanning {i}/{total} .blend file(s)…")

        tail = f"; {len(unreadable)} unreadable" if unreadable else ""
        report.add(Finding(
            category="overview",
            message=(f"{len(files)} file(s) scanned, {total_hits} material(s) matched in "
                     f"{matched_files} file(s){tail}"),
            severity="info",
            data={"files": len(files), "matched_files": matched_files, "hits": total_hits,
                  "unreadable": len(unreadable)},
        ))

        from .report_store import stash_report

        stash_report(context, report, "matsearch")
        context.window_manager.filelink_matsearch_skipped_text = "\n".join(unreadable)

        msg = f"{total_hits} material(s) matched in {matched_files}/{len(files)} file(s)"
        self.report({"WARNING"} if unreadable else {"INFO"}, msg + (f"{tail}." if tail else "."))
