"""Batch 3 — reverse-dependency ("safe to delete?") operator.

Offline (BAT) modal scan of the Project Folder, then report who links TO the
chosen file. Reuses the F1 folder-scan plumbing (``core.blendscan``) for the walk
and ``core.reversedep`` for the pure inversion + report. Read-only — it only reads
.blend files from disk, never opens or mutates them.
"""

from __future__ import annotations

import pathlib

import bpy

from .progress import ModalProgressMixin
from .report_store import stash_report


class ASSETDOCTOR_OT_check_dependents(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "assetdoctor.check_dependents"
    bl_label = "Check What Links This File"
    bl_description = (
        "Before deleting a .blend, scan the Project Folder (offline) and list every "
        "file that links TO it — directly or through a chain — so you know what "
        "would break. The inverse of the top-down dependency scan. Read-only"
    )

    def cancel_message(self) -> str:
        return "Reverse-dependency check cancelled"

    def run_steps(self, context):
        from ..core import blendscan, reversedep

        scene = context.scene
        root_str = bpy.path.abspath(scene.assetdoctor_scan_dir or "")
        target_str = bpy.path.abspath(scene.assetdoctor_dep_target or "")

        root = pathlib.Path(root_str) if root_str else None
        if root is None or not root.is_dir():
            self.report({"ERROR"}, "Pick the Project Folder to scan first")
            return
        if not target_str:
            self.report({"ERROR"}, "Pick the file you want to check")
            return
        if not blendscan.bat_available():
            self.report({"ERROR"}, "Blender Asset Tracer unavailable; reinstall the extension")
            return

        target = str(pathlib.Path(target_str).resolve())
        files = list(blendscan.iter_blend_files(root))
        if not files:
            self.report({"INFO"}, "No .blend files found in that folder")
            return

        result = blendscan.new_scan_result()
        total = len(files)
        for i, f in enumerate(files):
            blendscan.scan_into(result, f)  # handles per-file read errors internally
            yield (0.92 * (i + 1) / total, f"Scanning {f.name}… {i + 1}/{total}")

        yield (0.96, "Inverting the link graph…")
        pairs = [(e.source, e.target) for e in result.graph.edges]
        direct, indirect, canon = reversedep.dependents(pairs, result.graph.nodes, target)
        label = pathlib.Path(target).name
        report = reversedep.build_reverse_dep_report(
            target, direct, indirect, found=canon is not None,
            scanned=total, file_label=label)
        stash_report(context, report, "f7rev")

        wm = context.window_manager
        if canon is None:
            wm.assetdoctor_dep_verdict = "not_scanned"
            wm.assetdoctor_dep_verdict_text = (
                f"{label} wasn't found in the scanned folder")
        elif direct or indirect:
            wm.assetdoctor_dep_verdict = "unsafe"
            tail = f", {len(indirect)} more transitively" if indirect else ""
            wm.assetdoctor_dep_verdict_text = (
                f"⚠ Do Not Delete — {len(direct)} file(s) link {label} directly{tail}")
        else:
            wm.assetdoctor_dep_verdict = "safe"
            wm.assetdoctor_dep_verdict_text = "No Links Detected — Safe to Delete"

        yield (1.0, "Done")
        if canon is None:
            self.report({"WARNING"}, f"{label} wasn't in the scanned folder — "
                        "check the Project Folder")
        elif direct or indirect:
            self.report({"WARNING"}, f"{len(direct)} direct + {len(indirect)} indirect "
                        f"dependent(s) link {label} — NOT safe to delete")
        else:
            self.report({"INFO"}, f"✓ Nothing links {label} — safe to delete")
