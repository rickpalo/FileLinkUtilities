"""F7 Phase 3 — fix the current file's library links (report-first + backup).

Two **independent** jobs (kept separate by user request, 2026-06-21):

1. **Relink broken/missing libraries** — per-link and targetable. "Find Broken
   Links" lists each missing library with an auto-found same-name candidate (if
   any); the user ticks the ones to fix (or picks a file manually) and relinks
   only those. Lets you fix one broken material-library link without touching the
   rest of the file.
2. **Normalize library paths** — absolute → ``//``-relative + backslash → forward
   slash on the libraries that already resolve, and report duplicate library
   blocks. Pure path hygiene; it never relinks.

Small N (a handful of libraries), so these are plain operators, not modal.
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


def _populate_broken_links(context) -> tuple[int, int]:
    """Refill ``assetdoctor_broken_libs`` from the current file's missing libraries,
    each paired with an auto-found candidate where unambiguous. Returns
    (broken count, auto-matched count)."""
    wm = context.window_manager
    coll = wm.assetdoctor_broken_libs
    coll.clear()
    libs = _gather_libs()
    missing = [lib for lib in libs if not lib.exists]
    blend_dir = os.path.dirname(bpy.data.filepath)
    # Search the folders of resolvable libraries (+ this file's folder) by filename.
    search_dirs = [blend_dir] + [os.path.dirname(lib.resolved)
                                 for lib in libs if lib.exists]
    candidates = relink.find_relink_candidates(missing, search_dirs)
    for lib in missing:
        item = coll.add()
        item.name = lib.name
        item.stored = lib.stored
        cand = candidates.get(lib.name, "")
        item.target = cand
        item.has_candidate = bool(cand)
        item.selected = bool(cand)  # pre-tick only the confident auto-matches
    wm.assetdoctor_broken_index = 0
    return len(missing), len(candidates)


class ASSETDOCTOR_OT_scan_broken_links(bpy.types.Operator):
    bl_idname = "assetdoctor.scan_broken_links"
    bl_label = "Find Broken Links"
    bl_description = ("List this file's broken/missing library links so you can relink "
                      "them individually (with an auto-found match where possible)")
    bl_options = {"REGISTER"}

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the file first")
            return {"CANCELLED"}
        broken, found = _populate_broken_links(context)
        if context.area:
            context.area.tag_redraw()
        if not broken:
            self.report({"INFO"}, "No broken library links")
        else:
            self.report({"INFO"}, f"{broken} broken link(s); {found} with an auto-found match")
        return {"FINISHED"}


class ASSETDOCTOR_OT_relink_pick_file(bpy.types.Operator):
    bl_idname = "assetdoctor.relink_pick_file"
    bl_label = "Pick Library File"
    bl_description = "Choose the .blend file to relink this broken library to"
    bl_options = {"REGISTER", "INTERNAL"}

    index: bpy.props.IntProperty()  # type: ignore[valid-type]
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]
    filter_glob: bpy.props.StringProperty(default="*.blend", options={"HIDDEN"})  # type: ignore[valid-type]

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        coll = context.window_manager.assetdoctor_broken_libs
        if 0 <= self.index < len(coll):
            item = coll[self.index]
            target = os.path.normpath(bpy.path.abspath(self.filepath))
            item.target = target
            item.has_candidate = os.path.isfile(target)
            item.selected = True
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ASSETDOCTOR_OT_relink_selected(bpy.types.Operator):
    bl_idname = "assetdoctor.relink_selected"
    bl_label = "Relink Selected"
    bl_options = {"REGISTER"}

    @classmethod
    def description(cls, context, properties):
        return ("Repoint each ticked broken library to its target file (and reload it). "
                "Takes a backup first")

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the file first")
            return {"CANCELLED"}

        coll = context.window_manager.assetdoctor_broken_libs
        chosen = [item for item in coll if item.selected and item.target]
        if not chosen:
            self.report({"WARNING"}, "Tick at least one link that has a target file")
            return {"CANCELLED"}

        # Validate every target exists before mutating anything.
        targets = {item.name: os.path.normpath(bpy.path.abspath(item.target)) for item in chosen}
        absent = [name for name, t in targets.items() if not os.path.isfile(t)]
        if absent:
            self.report({"ERROR"}, f"Target file not found for: {', '.join(absent)}")
            return {"CANCELLED"}

        from .safety import auto_backup

        backup = auto_backup(context)
        blend_dir = os.path.dirname(bpy.data.filepath)
        relinked = 0
        for item in chosen:
            lib = bpy.data.libraries.get(item.name)
            if lib is None:
                continue
            lib.filepath = relink.relink_stored_path(targets[item.name], blend_dir)
            try:
                lib.reload()  # actually load the now-found data
                relinked += 1
            except Exception as exc:
                self.report({"WARNING"}, f"Relinked {item.name} but reload failed: {exc}")

        # Refresh the list so the now-fixed links drop off.
        _populate_broken_links(context)
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Relinked {relinked} librar{'y' if relinked == 1 else 'ies'}. "
                              f"Save to persist.{tail}")
        return {"FINISHED"}


class ASSETDOCTOR_OT_normalize_library_paths(bpy.types.Operator):
    bl_idname = "assetdoctor.normalize_library_paths"
    bl_label = "Normalize Library Paths"
    bl_options = {"REGISTER"}

    apply: bpy.props.BoolProperty(default=False)  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        if properties.apply:
            return ("Normalize this file's library paths (absolute→relative, fix "
                    "backslashes) where safe. Does NOT relink — broken links are "
                    "handled by Find Broken Links. Takes a backup first")
        return ("Report which library paths would be normalized and which libraries "
                "are duplicated (no changes, no relinking)")

    def _analyze_and_stash(self, context):
        """Plan normalizations + duplicate-block detection (no relinking) and stash
        the f7fix report. Called again after applying so the report reflects the
        new state."""
        from .report_store import stash_report

        blend_dir = os.path.dirname(bpy.data.filepath)
        plan = relink.plan_library_fixes(_gather_libs(), blend_dir)
        report = relink.build_libfix_report(plan, relinks=None,
                                            blend_name=bpy.path.basename(bpy.data.filepath))
        stash_report(context, report, "f7fix")
        return plan, blend_dir

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the file first")
            return {"CANCELLED"}

        plan, blend_dir = self._analyze_and_stash(context)

        msg = f"{len(plan.renames)} to normalize, {len(plan.duplicates)} duplicate block(s)"
        if not self.apply or not plan.renames:
            self.report({"INFO"}, msg + (" (report only)" if not self.apply else ""))
            return {"FINISHED"}

        from .safety import auto_backup

        backup = auto_backup(context)
        normalized = 0
        for name, _old, new in plan.renames:
            lib = bpy.data.libraries.get(name)
            if lib is not None:
                lib.filepath = new
                normalized += 1
        # Re-analyze so the report reflects the now-fixed state (clean → "all clean").
        self._analyze_and_stash(context)
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Normalized {normalized} library path(s). Save to persist.{tail}")
        return {"FINISHED"}
