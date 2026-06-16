"""F7 Phase 3a — fix the current file's library paths (report-first + backup).

Normalises absolute → ``//``-relative and backslashes → forward slashes for the
current file's linked libraries (safe, reversible), and reports duplicate library
blocks. Small N (a handful of libraries), so this is a plain operator, not modal.
"""

from __future__ import annotations

import os

import bpy

from ..core import relink
from ..core.relink import LibDesc


def _gather_libs() -> list[LibDesc]:
    libs: list[LibDesc] = []
    for lib in bpy.data.libraries:
        stored = lib.filepath
        if not stored:
            continue
        resolved = os.path.normpath(bpy.path.abspath(stored))
        libs.append(LibDesc(name=lib.name, stored=stored, resolved=resolved,
                            exists=os.path.isfile(resolved)))
    return libs


class ASSETDOCTOR_OT_fix_library_paths(bpy.types.Operator):
    bl_idname = "assetdoctor.fix_library_paths"
    bl_label = "Fix Library Paths"
    bl_options = {"REGISTER"}

    apply: bpy.props.BoolProperty(default=False)  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        if properties.apply:
            return ("Normalize this file's library paths (absolute→relative, fix "
                    "backslashes) where safe. Takes a backup first")
        return ("Report which library paths would be normalized and which libraries "
                "are duplicated (no changes)")

    def _analyze_and_stash(self, context):
        """Gather libraries, plan fixes, build + stash the f7fix report. Called for
        the report, and again AFTER applying so the report reflects the new state."""
        from .report_store import stash_report

        blend_dir = os.path.dirname(bpy.data.filepath)
        libs = _gather_libs()
        plan = relink.plan_library_fixes(libs, blend_dir)
        # Search the folders of resolvable libraries (+ this file's folder) for the
        # missing ones by filename — the safe, unambiguous relinks.
        search_dirs = [blend_dir] + [os.path.dirname(lib.resolved)
                                     for lib in libs if lib.exists]
        relinks = relink.find_relink_candidates([lib for lib in libs if not lib.exists],
                                                search_dirs)
        report = relink.build_libfix_report(plan, relinks, bpy.path.basename(bpy.data.filepath))
        stash_report(context, report, "f7fix")
        return plan, relinks, blend_dir

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the file first")
            return {"CANCELLED"}

        plan, relinks, blend_dir = self._analyze_and_stash(context)

        msg = (f"{len(relinks)} relinkable, {len(plan.renames)} to normalize, "
               f"{len(plan.duplicates)} duplicate block(s)")
        if not self.apply or (not plan.renames and not relinks):
            self.report({"INFO"}, msg + (" (report only)" if not self.apply else ""))
            return {"FINISHED"}

        from .safety import auto_backup

        backup = auto_backup(context)
        relinked = 0
        for name, target in relinks.items():
            lib = bpy.data.libraries.get(name)
            if lib is None:
                continue
            lib.filepath = relink.to_relative(target, blend_dir) or target
            try:
                lib.reload()  # actually load the now-found data
                relinked += 1
            except Exception as exc:
                self.report({"WARNING"}, f"Relinked path for {name} but reload failed: {exc}")
        normalized = 0
        for name, _old, new in plan.renames:
            lib = bpy.data.libraries.get(name)
            if lib is not None:
                lib.filepath = new
                normalized += 1
        # Re-analyze so the report reflects the now-fixed state (clean → "all clean").
        self._analyze_and_stash(context)
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Relinked {relinked}, normalized {normalized} library "
                              f"path(s). Save to persist.{tail}")
        return {"FINISHED"}
