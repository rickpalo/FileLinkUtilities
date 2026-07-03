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
from .pickers import FilePickerMixin, resolve_existing_file


def _populate_missing_blocks(context) -> list[missingdata.MissingBlock]:
    """Refill ``assetdoctor_missing_blocks`` from the current file's placeholder
    (``is_missing``) data-blocks. A library group that already had a source .blend
    picked keeps that source string across a re-scan, so the user doesn't have to
    re-pick it — but candidates/confidence are NOT auto-recomputed for it here.

    Why not: a crash (EXCEPTION_ACCESS_VIOLATION inside core.imagematch.tokenize,
    real repro 2026-06-24) traced back to this re-scan calling _enumerate_group
    -> bpy.data.libraries.load(source, link=True) as a PEEK against a library that
    ASSETDOCTOR_OT_reconnect_selected had, moments earlier, just REALLY linked
    real data-blocks from (same source path) on a file independently known to have
    Blender-core fragility around missing/override data (see docs/TODO.md). Re-
    peeking an already-linked library right after a real link from it is the
    suspicious step; an access violation can't be caught in Python, so the only
    safe mitigation is to not trigger that peek automatically/silently. The user
    can still refresh a group's suggestions explicitly via Pick Source .blend
    (re-running _enumerate_group deliberately), which is the same code path but at
    least not fired silently on every re-scan.

    A group that has NEVER been picked/peeked before is a different, lower-risk
    case: if the block's STORED library path itself still resolves on disk (the
    "same library, renamed/numbered block at the source" pattern documented in
    docs/TODO.md — e.g. a link wants ``GeometricStichDesign`` but the library now
    only has ``GeometricStichDesign.001``), that library IS the obvious place to
    look first, and peeking it for the FIRST time carries none of the above
    "re-peek right after a real link" risk (this matches the two successful real
    peeks that preceded the crash, not the repeated one that triggered it). So a
    brand-new group auto-defaults ``source_blend`` to its own stored library path
    and is auto-enumerated immediately — the user requested this (2026-06-24:
    "it should automatically look in the original library... so I don't have to
    [manually pick it]"), and can still override the suggestion or pick a
    different source via Pick Source .blend, same as before.

    A group's own stored path sometimes does NOT resolve even though the SAME
    file is reachable via a different library entry in this very session —
    this project's own files commonly link one .blend many times under
    different path strings (absolute vs ``//``-relative, slash direction, a
    since-moved folder), and Blender treats each as a separate ``Library``
    datablock. User report 2026-06-24: most missing MATERIALS weren't
    auto-matched even though their library (materialMaster.blend) demonstrably
    resolves elsewhere in the same file. So a brand-new group whose own path
    doesn't resolve gets a SECOND chance via ``core.reconnect.
    find_sibling_library`` against every OTHER already-loaded library that
    DOES resolve, matched by basename only when unambiguous (never guessed).
    ``library_found`` records whether the group's OWN path resolves (distinct
    from a sibling match) so the UI can tell "library genuinely not found
    anywhere in this session" from "found via the original path" or "found via
    a sibling" — the user separately asked for this differentiation."""
    wm = context.window_manager
    coll = wm.assetdoctor_missing_blocks
    old_sources = {item.library: item.source_blend for item in coll if item.source_blend}

    # Every already-loaded library that resolves on THIS machine — the sibling-
    # match candidate pool. Built once per scan, not per block.
    resolving_lib_paths = []
    for lib in bpy.data.libraries:
        if not lib.filepath:
            continue
        p = os.path.normpath(bpy.path.abspath(lib.filepath))
        if os.path.isfile(p):
            resolving_lib_paths.append(p)

    blocks = list(_iter_missing_blocks())
    coll.clear()
    new_groups: set[str] = set()
    library_found: dict[str, bool] = {}
    library_auto_source: dict[str, str] = {}
    for b in blocks:
        item = coll.add()
        item.name = b.name
        item.kind = b.kind
        item.collection = b.collection
        item.library = b.library
        source = old_sources.get(b.library, "")
        if b.library not in library_found:
            own_path = os.path.normpath(bpy.path.abspath(b.library))
            found = os.path.isfile(own_path)
            library_found[b.library] = found
            auto = own_path if found else rc.find_sibling_library(own_path, resolving_lib_paths)
            library_auto_source[b.library] = auto
            # Only a GENUINELY first-time group (no remembered source from a
            # prior scan) gets auto-enumerated here — re-peeking an already-
            # known library on every re-scan is the exact crash-risky pattern
            # the docstring above describes fixing (v0.2.40), but this `auto`
            # check alone didn't actually exclude already-known groups, so it
            # kept re-peeking them every scan after all. Confirmed as the
            # likely cause of a real 2026-06-25 report: re-running Find
            # Reconnectable Data-blocks kept re-suggesting the SAME
            # transitively-missing candidates as fresh "available" matches
            # (their stuck/"transitive" state from a prior Reconnect attempt
            # was never remembered), making repeated attempts look like no
            # progress was made.
            if auto and b.library not in old_sources:
                new_groups.add(b.library)
        if not source:
            source = library_auto_source.get(b.library, "")
        item.source_blend = source
        item.library_found = library_found.get(b.library, False)
    wm.assetdoctor_missing_index = 0
    wm.assetdoctor_missing_scanned = True

    for library in new_groups:
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
            coll = context.window_manager.assetdoctor_missing_blocks
            matched = sum(1 for item in coll if item.confidence != "none")
            tail = (f" — {matched} auto-matched from their original library; pick a "
                    "source for the rest" if matched else
                    " — pick a source per group to suggest reconnects")
            self.report({"INFO"}, f"{len(blocks)} missing data-block(s) from "
                        f"{libs} librar{'y' if libs == 1 else 'ies'}{tail}")
        else:
            self.report({"INFO"}, "✓ No missing data-blocks")
        return {"FINISHED"}


class ASSETDOCTOR_OT_reconnect_pick_source(FilePickerMixin, bpy.types.Operator):
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

    def execute(self, context):
        path = resolve_existing_file(self.filepath)
        if not path:
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
        transitively_missing = 0
        externally_linked = 0
        warnings: list[str] = []
        # (collection, name) of every row caught by the transitive-missing check
        # below — _populate_missing_blocks rebuilds the whole list from scratch
        # afterward, so this is replayed onto the fresh rows to keep the "found
        # in the library, but it's ALSO missing upstream" state visible in the UI
        # (user report 2026-06-24: "did not differentiate between data-blocks
        # that were missing in linked libraries" — a transitively-missing row
        # looked identical to an ordinary unmatched one once the count scrolled
        # off in the status line).
        transitive_keys: set[tuple[str, str]] = set()
        # Same idea for the OTHER way a "successful" remap turns out not to have
        # actually fixed anything — see the loop below for the root cause this
        # was diagnosed from (2026-06-25, headless probe against a real file).
        external_keys: set[tuple[str, str]] = set()

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
                # A bare name lookup (`target_coll.get(row.name)`) is ambiguous: this
                # project's real files routinely have a LOCAL data-block sharing the
                # exact same name as the linked-but-missing placeholder (e.g. a local
                # "Std_Tongue.026" alongside the linked placeholder of the same name),
                # and Blender's plain-name `.get()` silently returns the wrong one (the
                # local, non-missing one), making every row look "already resolved" —
                # confirmed via a real headless probe against human_bundle.blend
                # (2026-06-28). The (name, library) tuple form is the documented way to
                # disambiguate ID lookups by library.
                placeholder = (target_coll.get((row.name, row.library))
                                if target_coll is not None else None)
                if placeholder is None or not getattr(placeholder, "is_missing", False):
                    warnings.append(f"{row.name}: no longer a missing placeholder, skipped")
                    continue
                linked = loaded.get((row.collection, row.target))
                if linked is None:
                    warnings.append(f"{row.name}: '{row.target}' not found in "
                                    f"{os.path.basename(source)}")
                    continue
                if getattr(linked, "is_missing", False):
                    # The candidate we just linked is ITSELF an unresolved
                    # placeholder inside the source .blend — it links onward to a
                    # further-upstream library that isn't available either (real,
                    # documented disease on this project's own files:
                    # materialMaster.blend/human_bundle.blend transitively miss
                    # content from libraries further upstream — see docs/TODO.md
                    # "MAGENTA = MISSING TEXTURES"). Remapping the placeholder onto
                    # it would just trade one missing name for another and falsely
                    # report success (the exact bug reported 2026-06-24: items
                    # "successfully reconnected" reappeared as missing right after).
                    # Skip, and drop the orphaned still-missing block we just
                    # linked rather than leaving it cluttering bpy.data.
                    transitively_missing += 1
                    transitive_keys.add((row.collection, row.name))
                    if linked.users == 0:
                        target_coll.remove(linked)
                    warnings.append(f"{row.name}: '{row.target}' in "
                                    f"{os.path.basename(source)} is itself "
                                    "unresolved (missing further upstream) — not "
                                    "actually fixed, skipped")
                    continue
                placeholder.user_remap(linked)
                if placeholder.users == 0:
                    target_coll.remove(placeholder)
                    reconnected += 1
                    continue
                # user_remap() reported success (no exception) but the
                # placeholder STILL has real users — diagnosed via a headless
                # probe against a real production file (2026-06-25): the
                # remaining reference almost always lives inside data that is
                # ITSELF linked from another library (e.g. a Material's node
                # tree sourced from a DIFFERENT file than the one we're
                # editing) — you cannot rewrite a pointer inside someone
                # else's linked data from the linking file; it has to be
                # fixed by opening THAT library directly. Without this check,
                # `reconnected` silently counted these as fixed even though
                # nothing changed (the user-reported "Reconnected N, but the
                # missing-block count never goes down" bug).
                remaining = bpy.data.user_map(subset={placeholder}).get(placeholder, set())
                external_libs = sorted({
                    os.path.basename(u.library.filepath) for u in remaining
                    if u.library is not None
                })
                if external_libs:
                    externally_linked += 1
                    external_keys.add((row.collection, row.name))
                    warnings.append(
                        f"{row.name}: matched and linked, but still referenced from "
                        f"{', '.join(external_libs)} — open that file directly to fix it there")
                else:
                    warnings.append(
                        f"{row.name}: still has {placeholder.users} user(s) after "
                        "remap (unexpected — not the usual linked-reference case)")

        # Defensive depsgraph settle before the next viewport draw, same precaution
        # taken after bulk image remap/remove (see ops.image_dedup) — unverified but
        # cheap, and this also removes placeholder ID datablocks in bulk.
        try:
            context.view_layer.update()
        except Exception:
            pass

        _populate_missing_blocks(context)
        if transitive_keys or external_keys:
            for item in coll:
                key = (item.collection, item.name)
                if key in transitive_keys:
                    item.confidence = "transitive"
                    item.selected = False
                elif key in external_keys:
                    item.confidence = "external"
                    item.selected = False
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        msg = f"Reconnected {reconnected} data-block(s). Save to persist.{tail}"
        if transitively_missing:
            msg += (f" {transitively_missing} candidate(s) were themselves unresolved "
                    "in the source .blend (missing further upstream — that library "
                    "doesn't actually have this data either).")
        if externally_linked:
            msg += (f" {externally_linked} candidate(s) are still referenced from another "
                    "linked file — open that file directly to fix those.")
        if warnings:
            msg += f" {len(warnings)} skipped — see debug log."
            for w in warnings:
                log.warning("Reconnect skipped: %s", w)
        self.report({"INFO"}, msg)
        from .progress import set_result

        set_result(context, msg, ok=not warnings)
        return {"FINISHED"}


