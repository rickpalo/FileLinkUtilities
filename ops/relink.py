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
from .datablock_inspect import _iter_all_blocks
from .pickers import FilePickerMixin

# Mirrors ops.datablock_inspect._LOOP_NODE_CAP's own "too heavy" guard — above
# this many linked datablocks, skip the direct/indirect check (assume direct)
# rather than let a giant file's user_map scan hang Find Broken Links.
_DIRECT_NODE_CAP = 60000


def _direct_libraries(libs: list) -> set:
    """Which of ``libs`` (real ``bpy.types.Library`` datablocks) are
    referenced by at least one LOCAL datablock, vs. only reachable
    transitively through another linked library (docs/TODO.md Group 1 item 5,
    2026-07-04 — the "ThePiazzaSanMarco.blend not in Libraries" confusion:
    `bpy.data.libraries` includes libraries your OWN linked libraries link,
    not just ones this file links directly). `bpy.data.user_map(subset=...)`
    restricts which IDs appear as dict KEYS but still scans the whole file to
    find their users, so passing just these libraries' own linked IDs as the
    subset is enough — cheaper than a full-file map, same technique
    `ops.datablock_inspect` already uses for its own loop detection."""
    lib_set = set(libs)
    linked_ids = [block for _attr, block in _iter_all_blocks() if block.library in lib_set]
    if len(linked_ids) > _DIRECT_NODE_CAP:
        return lib_set  # too expensive to check safely — don't mislabel, just skip
    try:
        umap = bpy.data.user_map(subset=linked_ids)
    except Exception:
        return lib_set  # never let a bpy quirk break the broken-links list

    direct: set = set()
    for block in linked_ids:
        if block.library in direct:
            continue
        if any(user.library is None for user in umap.get(block, ())):
            direct.add(block.library)
    return direct


def _gather_libs() -> list[LibDesc]:
    libs = list(bpy.data.libraries)
    direct = _direct_libraries(libs)
    out: list[LibDesc] = []
    for lib in libs:
        stored = lib.filepath
        if not stored:
            continue
        resolved = os.path.normpath(bpy.path.abspath(stored))
        out.append(LibDesc(name=lib.name, stored=stored, resolved=resolved,
                           exists=os.path.isfile(resolved), is_direct=lib in direct))
    return out


def _populate_broken_links(context) -> tuple[int, int]:
    """Refill ``filelink_broken_libs`` from the current file's missing libraries,
    each paired with an auto-found candidate where unambiguous. Returns
    (broken count, auto-matched count)."""
    wm = context.window_manager
    coll = wm.filelink_broken_libs
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
        # Pre-tick only confident auto-matches, and only DIRECT links: an indirect
        # library can't be bulk-relinked from here (its parent library owns the
        # path), so pre-ticking it would let Relink Selected try and fail on it
        # (user feedback 2026-07-15, item 5). Indirect rows go to Retarget instead.
        item.selected = bool(cand) and lib.is_direct
        # Reuses the generic per-row `tag` (unused elsewhere for this list) to
        # carry "direct"/"indirect" — see core.relink.LibDesc.is_direct.
        item.tag = "direct" if lib.is_direct else "indirect"
    wm.filelink_broken_index = 0
    # Prune the "retargeted → reconnecting" set to libraries STILL broken (user
    # feedback 2026-07-15 item 3): once a library is relinked/fully reconnected it
    # drops out of `missing`, so its greyed row is gone anyway — don't keep a stale
    # flag around that could re-grey a same-path library later.
    from .datablock_reconnect import _norm_lib_path
    still_broken = {_norm_lib_path(lib.stored) for lib in missing}
    prev = set(filter(None, wm.filelink_retargeted_libs.split("\n")))
    wm.filelink_retargeted_libs = "\n".join(sorted(prev & still_broken))
    return len(missing), len(candidates)


def _refresh_broken_links(context) -> tuple[int, int]:
    """Repopulate the broken-link list AND stash the persistent report, so a scan
    always leaves a visible result — including a "No broken library links found"
    status when the file is clean (user rule, 2026-06-22). Returns (broken, auto-matched)."""
    from .report_store import stash_report

    broken, found = _populate_broken_links(context)
    coll = context.window_manager.filelink_broken_libs
    rows = [(item.name, item.stored, item.target) for item in coll]
    report = relink.build_broken_links_report(
        rows, blend_name=bpy.path.basename(bpy.data.filepath) or "current file")
    stash_report(context, report, "f7links")
    return broken, found


class FILELINK_OT_scan_broken_links(bpy.types.Operator):
    bl_idname = "filelink.scan_broken_links"
    bl_label = "Find Broken Library Links"
    bl_description = ("List this file's broken/missing library links so you can relink "
                      "them individually (with an auto-found match where possible)")
    bl_options = {"REGISTER"}

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the file first")
            return {"CANCELLED"}
        broken, found = _refresh_broken_links(context)
        if context.area:
            context.area.tag_redraw()
        if not broken:
            self.report({"INFO"}, "No broken library links found — see the Broken Library Links report")
        else:
            self.report({"INFO"}, f"{broken} broken link(s); {found} with an auto-found match")
        return {"FINISHED"}


class FILELINK_OT_relink_pick_file(FilePickerMixin, bpy.types.Operator):
    bl_idname = "filelink.relink_pick_file"
    bl_label = "Pick Library File"
    bl_description = "Choose the .blend file to relink this broken library to"
    bl_options = {"REGISTER", "INTERNAL"}

    index: bpy.props.IntProperty()  # type: ignore[valid-type]
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]
    filter_glob: bpy.props.StringProperty(default="*.blend", options={"HIDDEN"})  # type: ignore[valid-type]

    def execute(self, context):
        coll = context.window_manager.filelink_broken_libs
        if 0 <= self.index < len(coll):
            item = coll[self.index]
            target = os.path.normpath(bpy.path.abspath(self.filepath))
            item.target = target
            item.has_candidate = os.path.isfile(target)
            item.selected = True
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class FILELINK_OT_relink_selected(bpy.types.Operator):
    bl_idname = "filelink.relink_selected"
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

        coll = context.window_manager.filelink_broken_libs
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

        # Refresh the list + report so the now-fixed links drop off (and the report
        # flips to "No broken links found" once they're all resolved).
        _refresh_broken_links(context)
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Relinked {relinked} librar{'y' if relinked == 1 else 'ies'}. "
                              f"Save to persist.{tail}")
        return {"FINISHED"}


def _populate_dup_lib_members(context, plan: relink.LibFixPlan) -> None:
    """Refill ``filelink_dup_lib_members`` from ``plan.duplicates`` (item 6,
    2026-06-25): one row per stored-path FORM in each duplicate-library group
    (``group`` = the resolved-target key), pre-selecting the first member of
    each group as the default "keep this path" choice — mirrors every other
    list in this addon defaulting to a sensible first pick rather than none."""
    coll = context.window_manager.filelink_dup_lib_members
    coll.clear()
    for group_key, members in plan.duplicates.items():
        for i, (name, stored) in enumerate(members):
            item = coll.add()
            item.name = name
            item.stored = stored
            item.group = group_key
            item.selected = (i == 0)


def _populate_abs_path_members(context, groups: list[relink.AbsolutePathGroup]) -> None:
    """Refill ``filelink_abs_path_members`` from ``plan_absolute_paths``
    (item 7, 2026-06-25): one row per absolute library, grouped (``group``)
    by drive. Same-drive members default pre-ticked (the same safe,
    idempotent relative-path conversion Normalize already silently performs)
    and carry their precomputed relative path in ``target``; cross-drive
    members get an EMPTY ``target`` — there is no relative path between
    drives — so the UI can tell them apart and show them read-only."""
    coll = context.window_manager.filelink_abs_path_members
    coll.clear()
    for group in groups:
        for member in group.members:
            item = coll.add()
            item.name = member.name
            item.stored = member.stored
            item.group = group.drive
            item.target = member.new
            item.selected = bool(member.new)


def _refresh_libfix(context):
    """Plan normalizations + duplicate-block detection (no mutation) and stash
    the f7fix report + the duplicate-library/absolute-path checkbox lists.
    Called again after Normalize/Merge/Make Relative so all three reflect
    the new state."""
    from .report_store import stash_report

    blend_dir = os.path.dirname(bpy.data.filepath)
    libs = _gather_libs()
    plan = relink.plan_library_fixes(libs, blend_dir)
    report = relink.build_libfix_report(plan, relinks=None,
                                        blend_name=bpy.path.basename(bpy.data.filepath))
    stash_report(context, report, "f7fix")
    _populate_dup_lib_members(context, plan)
    _populate_abs_path_members(context, relink.plan_absolute_paths(libs, blend_dir))
    return plan, blend_dir


class FILELINK_OT_normalize_library_paths(bpy.types.Operator):
    bl_idname = "filelink.normalize_library_paths"
    bl_label = "Normalize Library Paths"
    bl_options = {"REGISTER"}

    apply: bpy.props.BoolProperty(default=False)  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        if properties.apply:
            return ("Normalize this file's library paths (absolute→relative, fix "
                    "backslashes) where safe. Does NOT relink — broken links are "
                    "handled by Find Broken Library Links. Takes a backup first")
        return ("Report which library paths would be normalized and which libraries "
                "are duplicated (no changes, no relinking)")

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the file first")
            return {"CANCELLED"}

        plan, blend_dir = _refresh_libfix(context)

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
        _refresh_libfix(context)
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Normalized {normalized} library path(s). Save to persist.{tail}")
        return {"FINISHED"}


class FILELINK_OT_dup_lib_select(bpy.types.Operator):
    """Tick exactly one stored-path form per duplicate-library group (radio
    behaviour via checkboxes — Blender has no native radio-checkbox), item 6."""

    bl_idname = "filelink.dup_lib_select"
    bl_label = "Use This Path"
    bl_options = {"INTERNAL"}

    index: bpy.props.IntProperty()  # type: ignore[valid-type]

    def execute(self, context):
        coll = context.window_manager.filelink_dup_lib_members
        if not (0 <= self.index < len(coll)):
            return {"CANCELLED"}
        group = coll[self.index].group
        for i, item in enumerate(coll):
            if item.group == group:
                item.selected = (i == self.index)
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


def _merge_library(victim, canonical) -> int:
    """Remap every datablock ``victim`` currently provides onto the
    identically-named datablock from ``canonical`` — the SAME real file,
    reached via a different stored path, so every name should already match.
    Links the name in from ``canonical``'s own file first if ``bpy.data``
    doesn't already hold it (mirrors ``ops.examine_library``'s mechanics
    exactly — this IS that same "re-source everything a library provides"
    operation, just auto-targeted at the other half of a duplicate pair
    instead of a user-picked replacement). Never force-removes ``victim`` —
    once nothing references it, Blender drops it on its own. Returns the
    remap count."""
    from .examine_library import _iter_library_blocks

    by_attr: dict[str, list] = {}
    for attr, block in _iter_library_blocks(victim):
        by_attr.setdefault(attr, []).append(block)
    if not by_attr:
        return 0

    to_link: dict[str, set[str]] = {}
    for attr, blocks in by_attr.items():
        coll = getattr(bpy.data, attr, None)
        have = {b.name for b in coll if b.library is canonical} if coll else set()
        wanted = {b.name for b in blocks} - have
        if wanted:
            to_link[attr] = wanted
    if to_link:
        try:
            with bpy.data.libraries.load(canonical.filepath, link=True) as (data_from, data_to):
                for attr, names in to_link.items():
                    setattr(data_to, attr,
                           [n for n in getattr(data_from, attr, []) if n in names])
        except Exception:
            pass  # best-effort — any name not found there just won't remap below

    remapped = 0
    for attr, blocks in by_attr.items():
        coll = getattr(bpy.data, attr)
        for block in blocks:
            target = next((b for b in coll if b.name == block.name and b.library is canonical), None)
            if target is None or target is block:
                continue
            block.user_remap(target)
            remapped += 1
    return remapped


class FILELINK_OT_merge_duplicate_libraries(bpy.types.Operator):
    """"Use Selected Paths" (item 6): merge every duplicate-library group that
    has a ticked member, keeping that member's path and remapping everything
    the OTHER member(s) provide onto it."""

    bl_idname = "filelink.merge_duplicate_libraries"
    bl_label = "Use Selected Paths"
    bl_options = {"REGISTER"}

    # "" (the default, one button per group in the UI) = just that group;
    # never actually set to "all" anywhere yet, but kept generic like every
    # other "Selected" operator in this codebase in case a bulk button is
    # added later.
    group: bpy.props.StringProperty()  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        return ("Keep the ticked library's path; remap everything the OTHER "
                "duplicate(s) in its group provide onto it, so Blender can drop "
                "the redundant library once nothing references it. Takes a backup first")

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the file first")
            return {"CANCELLED"}

        coll = context.window_manager.filelink_dup_lib_members
        groups: dict[str, list] = {}
        for item in coll:
            if self.group and item.group != self.group:
                continue
            groups.setdefault(item.group, []).append(item)

        targets = []
        for group_key, items in groups.items():
            canonical = next((i for i in items if i.selected), None)
            if canonical is None:
                continue
            targets.append((canonical, [i for i in items if i.name != canonical.name]))
        if not targets:
            self.report({"WARNING"}, "Tick which path to keep for at least one group")
            return {"CANCELLED"}

        from .safety import auto_backup

        backup = auto_backup(context)
        remapped = merged_groups = 0
        for canonical_item, victims in targets:
            canonical_lib = bpy.data.libraries.get(canonical_item.name)
            if canonical_lib is None:
                continue
            for victim_item in victims:
                victim_lib = bpy.data.libraries.get(victim_item.name)
                if victim_lib is None or victim_lib is canonical_lib:
                    continue
                remapped += _merge_library(victim_lib, canonical_lib)
            merged_groups += 1

        # The now-unused victim librar(y/ies) are still present until purged —
        # do that now so the re-scan below honestly shows the group resolved
        # (mirrors Reconnect's do_linked_ids=True purge for the same reason).
        bpy.data.orphans_purge(do_local_ids=False, do_linked_ids=True, do_recursive=True)

        try:
            context.view_layer.update()
        except Exception:
            pass

        _refresh_libfix(context)
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Merged {merged_groups} duplicate group(s), "
                    f"{remapped} data-block(s) remapped.{tail} Save to persist.")
        return {"FINISHED"}


class FILELINK_OT_make_selected_relative(bpy.types.Operator):
    """"Make Selected Relative" (item 7): convert every ticked same-drive
    absolute library to its precomputed ``//``-relative path. Cross-drive
    libraries have no checkbox to begin with — there is no relative path
    between Windows drives."""

    bl_idname = "filelink.make_selected_relative"
    bl_label = "Make Selected Relative"
    bl_description = ("Convert every ticked same-drive absolute library path to a "
                      "//-relative one. Takes a backup first")
    bl_options = {"REGISTER"}

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the file first")
            return {"CANCELLED"}

        coll = context.window_manager.filelink_abs_path_members
        chosen = [item for item in coll if item.selected and item.target]
        if not chosen:
            self.report({"WARNING"}, "Tick at least one same-drive library")
            return {"CANCELLED"}

        from .safety import auto_backup

        backup = auto_backup(context)
        made = 0
        for item in chosen:
            lib = bpy.data.libraries.get(item.name)
            if lib is not None:
                lib.filepath = item.target
                made += 1

        _refresh_libfix(context)
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Made {made} library path(s) relative. Save to persist.{tail}")
        return {"FINISHED"}
