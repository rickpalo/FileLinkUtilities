"""F7 — recursive single-file dependency scan (modal, offline via BAT).

Reads a chosen ``.blend`` (default = the current file) and walks its library
links breadth-first, recursing into each resolved ``.blend`` that exists, then
classifies every link (missing / absolute / mixed-slash / duplicate-ref /
inconsistent-path / drive-remap / circular) and stashes the F7 report.

Offline: it reads the dependency ``.blend`` files via Blender Asset Tracer — it
does NOT open them in Blender — so it is safe to run while other work is loaded.
Heavy files take tens of seconds each to read; progress + status update between
files and the run can be paused (see ops.progress.ModalProgressMixin)."""

from __future__ import annotations

import pathlib

import bpy

from ..core import blendscan, depscan
from .progress import ModalProgressMixin
from .report_store import stash_tree


class FILELINK_OT_scan_dependencies(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "filelink.scan_dependencies"
    bl_label = "Scan Dependencies"
    bl_description = (
        "Recursively map this file's library links (and the files they link, "
        "breadth-first), flagging missing/absolute/inconsistent paths, duplicate "
        "library references and circular links. Reads dependencies offline (does "
        "not open them); can be paused"
    )

    # Each step is a whole-file BAT read (slow), so repaint after EVERY step
    # instead of batching — otherwise the "now reading X" status only appears
    # after the blocking read and the user just sees "Starting…" for a minute.
    _PROGRESS_BUDGET = 0.0

    # Always scans the CURRENT file (avoids the confusion of scanning file B from
    # inside file A); the recursive walk follows its links outward anyway.
    def _start_file(self) -> str:
        return bpy.data.filepath

    def invoke(self, context, event):
        if not blendscan.bat_available():
            self.report({"ERROR"}, "Blender Asset Tracer unavailable — cannot scan offline")
            return {"CANCELLED"}
        start = self._start_file()
        if not start or not pathlib.Path(start).is_file():
            self.report({"ERROR"}, "Save the file first — the scan reads it from disk")
            return {"CANCELLED"}
        return super().invoke(context, event)

    def run_steps(self, context):
        start = self._start_file()
        result = depscan.new_dep_scan()
        # scan_recursive_steps is breadth-first; its status is "[depth] name", so
        # the level is already visible in the progress text as the walk descends.
        yield from depscan.scan_recursive_steps(
            result, [pathlib.Path(start)], scan_file=blendscan.scan_file
        )
        nodes = depscan.build_dependency_tree(result)
        stash_tree(context, nodes, "f7")
        n = len(result.graph.nodes)
        errors = next((x for x in nodes if x.key == "f7:errors"), None)
        issues = errors.detail if errors else "0"
        yield 1.0, f"Done: {n} files, {issues} issue(s)"
        self.report({"INFO"}, f"Dependency scan: {n} files, {issues} issue(s)")
