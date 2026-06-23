"""Batch C — datablock RECONNECT: point a missing (placeholder) data-block at a
real datablock in a chosen source .blend, then merge its users onto it.

A missing DATA-BLOCK (``core.missingdata``) differs from a missing LIBRARY LINK
(``ops.relink``): the library itself may resolve fine, but a specific Object/
Material/etc. it should hold no longer exists there under that name (renamed or
removed at the source — e.g. the user upgraded ``…People.blend`` to a 5.1 version
but old links still want the original names). Per missing-block GROUP (grouped by
the broken/old library, the natural unit since they usually share one fix), the
user picks a source .blend — often an upgraded copy of the same library, but it can
be anything — and we PEEK its matching collection (``bpy.data.libraries.load``,
``link=True``, never assigning ``data_to`` so nothing actually loads yet) to list
candidate names and auto-suggest the closest one (``core.reconnect``). On Apply:
backup, then for each ticked row LINK the chosen datablock in, ``user_remap`` the
placeholder's users onto it, and remove the now-unused placeholder.
"""

from __future__ import annotations

import os

import bpy

from ..core import missingdata, reconnect as rc
from .datablock_inspect import _iter_missing_blocks


def _populate_missing_blocks(context) -> list[missingdata.MissingBlock]:
    """Refill ``assetdoctor_missing_blocks`` from the current file's placeholder
    (``is_missing``) data-blocks. A library group that already had a source .blend
    picked keeps it across a re-scan (and its suggestions are recomputed) — so
    re-running the scan after a partial Reconnect doesn't make you re-pick the
    source for whatever's still left in that group."""
    wm = context.window_manager
    coll = wm.assetdoctor_missing_blocks
    old_sources = {item.library: item.source_blend for item in coll if item.source_blend}

    blocks = list(_iter_missing_blocks())
    coll.clear()
    for b in blocks:
        item = coll.add()
        item.name = b.name
        item.kind = b.kind
        item.collection = b.collection
        item.library = b.library
        item.source_blend = old_sources.get(b.library, "")
    wm.assetdoctor_missing_index = 0
    wm.assetdoctor_missing_scanned = True

    remaining_libs = {item.library for item in coll}
    for library in old_sources:
        if library in remaining_libs:
            _enumerate_group(context, library)
    return blocks


def _enumerate_group(context, library: str) -> str:
    """Open the group's chosen source .blend ONCE and peek (never load) the names
    available in each collection its rows need; fill ``candidates``/``confidence``/
    ``selected`` per row. Returns an error message, or ``""`` on success (including
    the no-op case where the group has no rows or no source picked yet)."""
    wm = context.window_manager
    coll = wm.assetdoctor_missing_blocks
    rows = [item for item in coll if item.library == library]
    if not rows:
        return ""
    source = rows[0].source_blend
    if not source or not os.path.isfile(source):
        return ""

    attrs = sorted({row.collection for row in rows if row.collection})
    names_by_attr: dict[str, list[str]] = {}
    try:
        with bpy.data.libraries.load(source, link=True) as (data_from, _data_to):
            for attr in attrs:
                names_by_attr[attr] = list(getattr(data_from, attr, []))
    except Exception as exc:
        return f"Could not read {os.path.basename(source)}: {exc}"

    for row in rows:
        names = names_by_attr.get(row.collection, [])
        row.candidates = "\n".join(rc.ranked_candidates(row.name, names))
        suggestion = rc.suggest_reconnect(row.name, names)
        row.confidence = suggestion.confidence
        row.selected = suggestion.confidence != "none"
    return ""


class ASSETDOCTOR_OT_scan_reconnect_targets(bpy.types.Operator):
    bl_idname = "assetdoctor.scan_reconnect_targets"
    bl_label = "Find Reconnectable Data-blocks"
    bl_description = (
        "List this file's missing (placeholder) data-blocks, grouped by their "
        "broken/renamed source library, so you can point each group at a source "
        ".blend and reconnect them to the closest-matching real datablock. "
        "Nothing is changed yet"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        blocks = _populate_missing_blocks(context)
        if context.area:
            context.area.tag_redraw()
        if blocks:
            libs = len({b.library for b in blocks})
            self.report({"INFO"}, f"{len(blocks)} missing data-block(s) from "
                        f"{libs} librar{'y' if libs == 1 else 'ies'} — pick a source "
                        "per group to suggest reconnects")
        else:
            self.report({"INFO"}, "✓ No missing data-blocks")
        return {"FINISHED"}


class ASSETDOCTOR_OT_reconnect_pick_source(bpy.types.Operator):
    bl_idname = "assetdoctor.reconnect_pick_source"
    bl_label = "Pick Source .blend"
    bl_description = (
        "Choose the .blend that should now provide this group's data-blocks (e.g. "
        "an upgraded copy of the same library). Its matching datablocks are listed "
        "and the closest name is suggested per row — nothing links yet"
    )
    bl_options = {"REGISTER", "INTERNAL"}

    library: bpy.props.StringProperty()  # type: ignore[valid-type]
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]
    filter_glob: bpy.props.StringProperty(default="*.blend", options={"HIDDEN"})  # type: ignore[valid-type]

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        path = os.path.normpath(bpy.path.abspath(self.filepath))
        if not os.path.isfile(path):
            self.report({"ERROR"}, "Choose a .blend file")
            return {"CANCELLED"}

        coll = context.window_manager.assetdoctor_missing_blocks
        for item in coll:
            if item.library == self.library:
                item.source_blend = path
        error = _enumerate_group(context, self.library)
        if context.area:
            context.area.tag_redraw()
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}

        total = sum(1 for item in coll if item.library == self.library)
        matched = sum(1 for item in coll
                      if item.library == self.library and item.confidence != "none")
        self.report({"INFO"}, f"Suggested {matched} of {total} reconnect(s) from "
                    f"{os.path.basename(path)}")
        return {"FINISHED"}


class ASSETDOCTOR_OT_reconnect_selected(bpy.types.Operator):
    bl_idname = "assetdoctor.reconnect_selected"
    bl_label = "Reconnect Selected"
    bl_options = {"REGISTER"}

    @classmethod
    def description(cls, context, properties):
        return ("Link each ticked data-block from its chosen source .blend and "
                "remap the placeholder's users onto it (then remove the "
                "placeholder). Takes a backup first")

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the file first")
            return {"CANCELLED"}

        wm = context.window_manager
        coll = wm.assetdoctor_missing_blocks
        chosen = [item for item in coll
                 if item.selected and item.target and item.source_blend]
        if not chosen:
            self.report({"WARNING"}, "Tick at least one data-block with a source and a target")
            return {"CANCELLED"}

        from ..log import get_logger
        from .safety import auto_backup

        log = get_logger()
        backup = auto_backup(context)
        reconnected = 0
        warnings: list[str] = []

        by_source: dict[str, list] = {}
        for item in chosen:
            by_source.setdefault(item.source_blend, []).append(item)

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
                warnings.append(f"{os.path.basename(source)}: {exc}")
                continue

            loaded: dict[tuple[str, str], object] = {}
            for attr in wanted_by_attr:
                for idblock in getattr(data_to, attr, None) or []:
                    if idblock is not None:
                        loaded[(attr, idblock.name)] = idblock

            for row in rows:
                target_coll = getattr(bpy.data, row.collection, None)
                placeholder = target_coll.get(row.name) if target_coll is not None else None
                if placeholder is None or not getattr(placeholder, "is_missing", False):
                    warnings.append(f"{row.name}: no longer a missing placeholder, skipped")
                    continue
                linked = loaded.get((row.collection, row.target))
                if linked is None:
                    warnings.append(f"{row.name}: '{row.target}' not found in "
                                    f"{os.path.basename(source)}")
                    continue
                placeholder.user_remap(linked)
                if placeholder.users == 0:
                    target_coll.remove(placeholder)
                reconnected += 1

        # Defensive depsgraph settle before the next viewport draw, same precaution
        # taken after bulk image remap/remove (see ops.image_dedup) — unverified but
        # cheap, and this also removes placeholder ID datablocks in bulk.
        try:
            context.view_layer.update()
        except Exception:
            pass

        _populate_missing_blocks(context)
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        msg = f"Reconnected {reconnected} data-block(s). Save to persist.{tail}"
        if warnings:
            msg += f" {len(warnings)} skipped — see debug log."
            for w in warnings:
                log.warning("Reconnect skipped: %s", w)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class ASSETDOCTOR_OT_reconnect_category_toggle(bpy.types.Operator):
    """Expand/collapse one library group in the Datablock Reconnect list."""

    bl_idname = "assetdoctor.reconnect_category_toggle"
    bl_label = "Expand/Collapse Library Group"
    bl_options = {"INTERNAL"}

    key: bpy.props.StringProperty()  # type: ignore[valid-type]

    def execute(self, context):
        wm = context.window_manager
        keys = set(filter(None, wm.assetdoctor_missing_expanded.split("\n")))
        keys.discard(self.key) if self.key in keys else keys.add(self.key)
        wm.assetdoctor_missing_expanded = "\n".join(sorted(keys))
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}
