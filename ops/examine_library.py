"""Examine Library — proactively retarget AWAY from a chosen (working) library.

Different problem from ``ops.datablock_reconnect`` (which only triggers on
BROKEN/missing placeholders): a library can resolve perfectly fine and still be
worth dropping — e.g. a shared "Asset_bundle.blend" that creates circular
references with another library, so the user wants everything it currently
provides re-sourced from the local file or from OTHER already-loaded libraries
first, falling back to picking a specific replacement only when nothing already
in memory matches.

Workflow: pick a library → list EVERY local datablock currently linked from it →
for each, look for an EXACT (or ``.NNN``-same-base) name match already in memory,
preferring a LOCAL datablock over one from a different library (no file I/O at
all for that path) → where nothing matches, the row offers Make Local or a
per-row manual override: pick ANY source .blend and ANY datablock within it (not
just an auto-suggested name — e.g. relinking a Cube to a Sphere from another
file is a deliberate, valid choice here, not a mistake to guess around).

A name match is only a guess that two datablocks are "the same thing, renamed" —
for Materials we can do better, because (unlike a missing image file) BOTH sides
of an in-memory suggestion still have their full node graph loaded. ``_material_
graph_match`` reuses the F3 fingerprinter (``core.fingerprint.fingerprint_
material``, resolution-agnostic) to compare the examined material against the
suggested replacement and tags the row "identical" or "differs" so the user can
tell a safe rename apart from a same-named-but-different look (Phase 2 — a
per-node diff for the "differs" case — is deferred).
"""

from __future__ import annotations

import os

import bpy

from ..core import reconnect as rc
from .datablock_inspect import _iter_all_blocks
from .pickers import FilePickerMixin, resolve_existing_file


def _iter_library_blocks(library):
    """Yield ``(bpy.data attribute, block)`` for every datablock the CURRENT file
    links from ``library`` — any type. Thin filter over the shared generic walk
    (Phase 2b, 2026-06-25 — this used to duplicate ``_iter_all_blocks``'s walk
    near-verbatim, same shape as ``ops.datablock_inspect._iter_missing_blocks``,
    just a different predicate)."""
    for attr, block in _iter_all_blocks():
        if block.library is library:
            yield attr, block


def _material_graph_match(context, original, candidate) -> str:
    """``"identical"``/``"differs"`` node-graph comparison between two Material
    datablocks (both must already be loaded — never used for an unloaded/missing
    side), or ``""`` if either isn't a Material or extraction fails."""
    if not (isinstance(original, bpy.types.Material) and isinstance(candidate, bpy.types.Material)):
        return ""
    from ..core.fingerprint import fingerprint_material
    from ..prefs import get_prefs
    from .extract import extract_material

    try:
        prefs = get_prefs(context)
        res_pattern = prefs.resolution_token_regex if prefs else None
        fp_a = fingerprint_material(extract_material(original, res_pattern))
        fp_b = fingerprint_material(extract_material(candidate, res_pattern))
    except Exception:
        return ""
    return "identical" if fp_a == fp_b else "differs"


def _in_memory_pools(attr: str, exclude_library) -> tuple[list[str], dict[str, str]]:
    """``(local names, {other-library name: library filepath})`` for ``attr``'s
    collection — the candidate pools "Examine Library" searches before falling
    back to a manual file pick."""
    coll = getattr(bpy.data, attr, None)
    if coll is None:
        return [], {}
    local_names: list[str] = []
    other_by_name: dict[str, str] = {}
    for b in coll:
        if b.library is None:
            local_names.append(b.name)
        elif b.library is not exclude_library:
            other_by_name.setdefault(b.name, b.library.filepath)
    return local_names, other_by_name


def _populate_examine_rows(context, library) -> int:
    """Refill ``filelink_examine_rows`` from every datablock ``library``
    currently provides. Returns the row count."""
    wm = context.window_manager
    coll = wm.filelink_examine_rows
    coll.clear()
    for attr, block in _iter_library_blocks(library):
        local_names, other_by_name = _in_memory_pools(attr, library)
        row = coll.add()
        row.name = block.name
        row.kind = type(block).__name__
        row.collection = attr

        # EXACT/numbered only — a wrong fuzzy guess here would silently repoint a
        # WORKING link at an unrelated datablock, so only an unambiguous match
        # auto-applies; anything else needs the user's explicit Make Local or pick.
        sug = rc.suggest_reconnect(block.name, local_names, allow_fuzzy=False)
        candidate = None
        if sug.target:
            row.suggested_kind = "local"
            row.suggested_name = sug.target
            candidate = getattr(bpy.data, attr).get(sug.target)
            if candidate is not None and candidate.library is not None:
                candidate = None  # name collision with a linked block — not our local pool
        else:
            sug2 = rc.suggest_reconnect(block.name, list(other_by_name), allow_fuzzy=False)
            if sug2.target:
                row.suggested_kind = "library"
                row.suggested_name = sug2.target
                row.suggested_library = other_by_name[sug2.target]
                candidate = next((b for b in getattr(bpy.data, attr)
                                  if b.name == sug2.target and b.library is not None
                                  and b.library.filepath == row.suggested_library), None)
            else:
                row.suggested_kind = "none"
        row.use_suggested = row.suggested_kind != "none"
        row.selected = row.use_suggested
        if candidate is not None:
            row.graph_match = _material_graph_match(context, block, candidate)
    wm.filelink_examine_index = 0
    wm.filelink_examine_library = library.name if library else ""
    wm.filelink_examine_scanned = True
    return len(coll)


def rebuild_examine_picker_rows(wm) -> None:
    """Rebuild ``wm.filelink_examine_picker_rows`` (Group 12 Phase 3, item
    4) from the current ``filelink_examine_rows`` + expand state.

    The simplest of the four Phase 3 sections: unlike Missing Textures/
    Duplicate Textures/Reconnect, NOTHING in a group's header text depends on
    per-row state here (no "N matched"/mismatch/confidence counts — just a
    bare member count), and no field changes which GROUP a row belongs to
    (grouping is by ``kind``, fixed at scan time). So only membership-
    changing ops (Examine / Apply Selected) need to call this — every other
    per-row edit (``selected``/``make_local``/``target``/a fresh
    ``source_blend`` from Pick a Specific Item or Search a Folder) is drawn
    live by ``FILELINK_UL_examine_picker`` straight off the real row, no
    rebuild needed."""
    from ..core import picker as picker_mod
    from .report_store import get_expanded

    coll = wm.filelink_examine_rows
    if not len(coll):
        wm.filelink_examine_picker_rows.clear()
        return

    expanded = get_expanded(wm, "filelink_examine_expanded")
    groups: dict[str, list[int]] = {}
    for i, item in enumerate(coll):
        groups.setdefault(item.kind, []).append(i)

    specs = [
        picker_mod.GroupSpec(
            key=kind,
            label=f"{kind}  ({len(groups[kind])})",
            icon="LIBRARY_DATA_DIRECT",
            members=[picker_mod.MemberRef(ref_index=i) for i in groups[kind]],
        )
        for kind in sorted(groups, key=str.lower)
    ]
    picker_rows = picker_mod.flatten_group_member_rows(
        specs, expanded, ref_prop="filelink_examine_rows")

    picker_coll = wm.filelink_examine_picker_rows
    picker_coll.clear()
    for pr in picker_rows:
        item = picker_coll.add()
        item.kind = pr.kind
        item.key = pr.key
        item.group_key = pr.group_key
        item.ref_prop = pr.ref_prop
        item.ref_index = pr.ref_index
        item.indent = pr.indent
        item.label = pr.label
        item.icon = pr.icon
        item.has_action = pr.has_action
        item.alert = pr.alert
        item.is_expanded = pr.is_expanded


class FILELINK_OT_examine_library(bpy.types.Operator):
    bl_idname = "filelink.examine_library"
    bl_label = "Examine Library"
    bl_description = (
        "List every data-block the current file links from the chosen library, "
        "and suggest an existing LOCAL or OTHER-LIBRARY datablock already in "
        "memory to re-source it from instead (exact-name only — no guessing). "
        "Nothing is changed yet"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        name = context.window_manager.filelink_examine_library_pick
        library = bpy.data.libraries.get(name) if name else None
        if library is None:
            self.report({"ERROR"}, "Pick a library to examine")
            return {"CANCELLED"}
        n = _populate_examine_rows(context, library)
        rebuild_examine_picker_rows(context.window_manager)
        if context.area:
            context.area.tag_redraw()
        if n:
            suggested = sum(1 for row in context.window_manager.filelink_examine_rows
                            if row.suggested_kind != "none")
            self.report({"INFO"}, f"{n} data-block(s) from {library.name}; "
                        f"{suggested} have an in-memory match already")
        else:
            self.report({"INFO"}, f"✓ Nothing currently links from {library.name}")
        return {"FINISHED"}


def _peek_names(path: str, attr: str) -> list[str] | None:
    """Peek ``attr``'s names in ``path`` without loading anything (``link=True``,
    ``data_to`` never assigned). ``None`` on read failure, distinct from an
    empty list (file read fine, just has none of this type) — callers decide
    whether/how to report each case."""
    try:
        with bpy.data.libraries.load(path, link=True) as (data_from, _data_to):
            return list(getattr(data_from, attr, []))
    except Exception:
        return None


class FILELINK_OT_examine_pick_source(FilePickerMixin, bpy.types.Operator):
    bl_idname = "filelink.examine_pick_source"
    bl_label = "Pick a Specific Item"
    bl_description = (
        "Choose a .blend AND a specific datablock within it for THIS row — not "
        "limited to a name match (e.g. relink a Cube to a Sphere from another "
        "file on purpose). Overrides any in-memory suggestion for this row"
    )
    bl_options = {"REGISTER", "INTERNAL"}

    index: bpy.props.IntProperty()  # type: ignore[valid-type]
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]
    filter_glob: bpy.props.StringProperty(default="*.blend", options={"HIDDEN"})  # type: ignore[valid-type]

    def execute(self, context):
        coll = context.window_manager.filelink_examine_rows
        if not (0 <= self.index < len(coll)):
            return {"CANCELLED"}
        row = coll[self.index]
        path = resolve_existing_file(self.filepath)
        if not path:
            self.report({"ERROR"}, "Choose a .blend file")
            return {"CANCELLED"}
        names = _peek_names(path, row.collection)
        if names is None:
            self.report({"ERROR"}, f"Could not read {os.path.basename(path)}")
            return {"CANCELLED"}

        row.source_blend = path
        row.candidates = "\n".join(rc.ranked_candidates(row.name, names))
        row.use_suggested = False
        row.make_local = False
        row.selected = bool(names)
        if context.area:
            context.area.tag_redraw()
        if not names:
            self.report({"WARNING"}, f"{os.path.basename(path)} has no {row.kind} datablocks")
        return {"FINISHED"}


class FILELINK_OT_examine_search_folder(FilePickerMixin, bpy.types.Operator):
    """Folder-wide convenience layer over Pick a Specific Item (docs/TODO.md
    #20, 2026-06-27): walk every .blend under a chosen folder and peek each
    for a name match, instead of requiring the user to already know which
    file holds a replacement. Skips any file matching an ALREADY-LOADED
    library's resolved path — re-peeking a library this session has just
    really linked from is a documented, uncatchable native crash risk (see
    ops.datablock_reconnect._populate_missing_blocks's docstring); such a
    file is also pointless to search anyway, since its names are already in
    the in-memory pools _populate_examine_rows checked first."""

    bl_idname = "filelink.examine_search_folder"
    bl_label = "Search a Folder"
    bl_description = (
        "Walk every .blend in a chosen folder looking for a name match for this "
        "row, instead of already knowing which file to pick. Skips files "
        "already linked into this session"
    )
    bl_options = {"REGISTER", "INTERNAL"}

    index: bpy.props.IntProperty()  # type: ignore[valid-type]
    directory: bpy.props.StringProperty(subtype="DIR_PATH")  # type: ignore[valid-type]
    filter_folder: bpy.props.BoolProperty(default=True, options={"HIDDEN"})  # type: ignore[valid-type]

    def execute(self, context):
        import pathlib

        from ..core.blendscan import iter_blend_files
        from ..core.reconnect import find_best_file_match

        coll = context.window_manager.filelink_examine_rows
        if not (0 <= self.index < len(coll)):
            return {"CANCELLED"}
        row = coll[self.index]
        if not (self.directory and os.path.isdir(self.directory)):
            self.report({"ERROR"}, "Choose a folder")
            return {"CANCELLED"}

        already_loaded = {
            os.path.normpath(bpy.path.abspath(lib.filepath))
            for lib in bpy.data.libraries if lib.filepath
        }
        names_by_file: dict[str, list[str]] = {}
        unreadable = 0
        for blend in iter_blend_files(pathlib.Path(self.directory)):
            path = os.path.normpath(str(blend))
            if path in already_loaded:
                continue
            names = _peek_names(path, row.collection)
            if names is None:
                unreadable += 1
            elif names:
                names_by_file[path] = names

        best_file, suggestion = find_best_file_match(row.name, names_by_file)
        if not best_file:
            tail = f"; {unreadable} unreadable" if unreadable else ""
            self.report({"WARNING"}, f"No {row.kind} matching '{row.name}' found in "
                        f"{len(names_by_file)} file(s) searched{tail}")
            return {"CANCELLED"}

        row.source_blend = best_file
        row.candidates = "\n".join(rc.ranked_candidates(row.name, names_by_file[best_file]))
        row.use_suggested = False
        row.make_local = False
        row.selected = True
        if context.area:
            context.area.tag_redraw()
        self.report({"INFO"}, f"Found '{suggestion.target}' ({suggestion.confidence}) in "
                    f"{os.path.basename(best_file)} — searched {len(names_by_file)} file(s)")
        return {"FINISHED"}


class FILELINK_OT_examine_apply_selected(bpy.types.Operator):
    bl_idname = "filelink.examine_apply_selected"
    bl_label = "Apply Selected"
    bl_description = (
        "For each ticked row: Make Local if checked, else remap onto the accepted "
        "in-memory suggestion or the manually picked item. The old (Asset_bundle) "
        "copy is NOT deleted — Blender drops it from the file on its own once "
        "nothing references it anymore. Takes a backup first"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        wm = context.window_manager
        library = bpy.data.libraries.get(wm.filelink_examine_library)
        coll = wm.filelink_examine_rows
        chosen = [row for row in coll if row.selected]
        if not chosen:
            self.report({"WARNING"}, "Tick at least one data-block")
            return {"CANCELLED"}

        from .safety import auto_backup

        backup = auto_backup(context)

        # Rows needing a fresh per-row file link, grouped by source so a file
        # already picked for several rows is only opened once.
        by_source: dict[str, list] = {}
        for row in chosen:
            if not row.make_local and not row.use_suggested and row.source_blend and row.target:
                by_source.setdefault(row.source_blend, []).append(row)

        loaded: dict[tuple[str, str, str], object] = {}
        for source, rows in by_source.items():
            wanted_by_attr: dict[str, set[str]] = {}
            for row in rows:
                wanted_by_attr.setdefault(row.collection, set()).add(row.target)
            try:
                with bpy.data.libraries.load(source, link=True) as (data_from, data_to):
                    for attr, names in wanted_by_attr.items():
                        setattr(data_to, attr,
                               [n for n in getattr(data_from, attr, []) if n in names])
            except Exception as exc:
                self.report({"WARNING"}, f"{os.path.basename(source)}: {exc}")
                continue
            for attr in wanted_by_attr:
                for idblock in getattr(data_to, attr, None) or []:
                    if idblock is not None:
                        loaded[(source, attr, idblock.name)] = idblock

        localized = remapped = 0
        for row in chosen:
            target_coll = getattr(bpy.data, row.collection, None)
            block = target_coll.get(row.name) if target_coll is not None else None
            if block is None or block.library is not library:
                continue  # already changed (or gone) since the scan

            if row.make_local:
                block.make_local()
                localized += 1
                continue

            target = None
            if row.use_suggested:
                if row.suggested_kind == "local":
                    cand = target_coll.get(row.suggested_name)
                    target = cand if (cand is not None and cand.library is None) else None
                elif row.suggested_kind == "library":
                    target = next((b for b in target_coll
                                   if b.name == row.suggested_name and b.library is not None
                                   and b.library.filepath == row.suggested_library), None)
            elif row.source_blend and row.target:
                target = loaded.get((row.source_blend, row.collection, row.target))

            if target is None or target is block:
                continue
            block.user_remap(target)
            remapped += 1

        try:
            context.view_layer.update()
        except Exception:
            pass

        wm.filelink_examine_rows.clear()
        wm.filelink_examine_scanned = False
        rebuild_examine_picker_rows(wm)
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Made {localized} local, remapped {remapped}.{tail} "
                    "Save to persist. Re-run Examine Library to see any remaining.")
        return {"FINISHED"}


