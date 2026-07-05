"""F2 - recursively make all linked assets in the current file fully local.

Default mode writes a separate fully-local .blend and leaves the working file's
linked setup untouched (copy + revert). In-place mode flattens the current file
(auto-backup preserves the original first). Both resolve library overrides and
iterate until no linked IDs remain, then purge the emptied libraries.

Performance: the heavy lifting is one **bulk** ``bpy.ops.object.make_local(
type='ALL')`` call (internally batched — vastly faster than thousands of per-ID
``make_local`` calls), followed by bounded per-ID passes only for whatever the
bulk op can't reach (linked collections, node groups, un-resolved overrides).

Responsiveness: the apply path runs as a **modal** operator. :func:`localize_steps`
is a generator that yields ``(fraction, status)`` after each chunk; the modal
steps it one chunk per timer tick (live progress bar + ESC to cancel), while
``execute`` (EXEC_DEFAULT / scripting / tests) just drains it synchronously.
"""

import os

import bpy

from ..core.f2_makelocal import build_makelocal_report, libname


def _id_collections():
    """All bpy.data ID collections (generic, version-proof)."""
    for prop in bpy.data.bl_rna.properties:
        if prop.type != "COLLECTION":
            continue
        coll = getattr(bpy.data, prop.identifier, None)
        if coll is None or len(coll) == 0:
            continue
        first = next(iter(coll), None)
        if first is not None and hasattr(first, "library"):
            yield coll


def _gather_linked():
    items = []
    for coll in _id_collections():
        for db in coll:
            if db.library is None:
                continue
            items.append({
                "type": type(db).__name__,
                "name": db.name,
                "library": db.library.filepath,
                "indirect": db.library.parent is not None,
            })
    return items


def _gather_all_names():
    """Every EXISTING datablock (local + linked), for
    core.f2_makelocal.find_rename_collisions — local items pass
    ``library=""`` so they group correctly against linked same-named ones."""
    return [
        {"type": type(db).__name__, "name": db.name,
         "library": db.library.filepath if db.library else ""}
        for coll in _id_collections() for db in coll
    ]


def _remaining_linked():
    """Every datablock still linked or carrying a library override."""
    return [
        db
        for coll in _id_collections()
        for db in coll
        if db.library is not None or db.override_library is not None
    ]


def _row_key(item: dict) -> str:
    """Unique per-row key for a linked item dict — matches
    :func:`_resolve_selected` below (same 3 fields identify a real
    datablock unambiguously: name collisions across libraries are exactly
    why ``library`` is part of the key, not just ``type``/``name``)."""
    return f"{item['type']}/{item['name']} [{libname(item['library'])}]"


def _populate_makelocal_rows(context, items: list[dict]) -> None:
    """Refill ``filelink_makelocal_rows`` (one row per linked datablock,
    docs/TODO.md #22) — the same actionable checkbox shape Materials/
    Geometry/Orphans already have, so Make Local can be ticked item-by-item
    instead of all-or-nothing. Flat (not grouped by library): a real project
    can have thousands of linked datablocks, and Blender's own UIList filter
    box already handles narrowing a big flat list down, so a custom group/
    member virtualization (like Missing Textures') isn't needed here."""
    wm = context.window_manager
    coll = wm.filelink_makelocal_rows
    coll.clear()
    for item in items:
        row = coll.add()
        row.name = _row_key(item)
        row.item_type = item["type"]
        row.item_name = item["name"]
        row.library = item["library"]
        row.indirect = bool(item.get("indirect"))
        row.selected = True
    wm.filelink_makelocal_active = 0


def _resolve_selected(rows) -> list:
    """Ticked rows -> the real, currently-live datablocks they name (a row
    can go stale between scan and apply if the file changed in between —
    silently skip anything that no longer matches, same tolerance the other
    3 "_selected" operators already have via their id_to_mat.get(...) is
    None checks)."""
    wanted = {
        (r.item_type, r.item_name, r.library) for r in rows if r.selected
    }
    if not wanted:
        return []
    out = []
    for coll in _id_collections():
        for db in coll:
            if db.library is None:
                continue
            key = (type(db).__name__, db.name, db.library.filepath)
            if key in wanted:
                out.append(db)
    return out


def _bulk_make_local(log) -> None:
    """Fast bulk pass: make all objects / obdata / materials local in one
    operator call. Best-effort — anything it can't reach (linked collections,
    node groups, library overrides) is mopped up by the per-ID passes that
    follow. Guarded by poll() (e.g. wrong context / no view-layer objects) and
    against RuntimeError so it degrades gracefully to the per-ID path."""
    try:
        if not bpy.ops.object.make_local.poll():
            log.debug("F2 bulk make_local: poll() False in this context — skipping")
            return
        bpy.ops.object.make_local(type="ALL")
        log.info("F2 bulk make_local(type='ALL') done")
    except RuntimeError as exc:
        log.warning("F2 bulk make_local failed (%s) — falling back to per-ID passes", exc)


def _purge_libraries(log):
    # Purge orphaned datablocks until stable (make_local can leave copies behind);
    # bounded so it can't loop forever on a pathological file.
    for _ in range(20):
        if not bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True):
            break
    # Remove now-unused libraries. user_map() maps id -> the ids that USE it, so a
    # library with no entry/empty set has no users and is safe to remove. (Library.users
    # can report a phantom count after make_local, so don't trust it.)
    user_map = bpy.data.user_map()
    for lib in list(bpy.data.libraries):
        if not user_map.get(lib):
            try:
                bpy.data.libraries.remove(lib)
            except RuntimeError:
                pass
    for _ in range(20):
        if not bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True):
            break
    log.info("F2 purge: %d librar(ies) remain", len(bpy.data.libraries))


def _purge_empty_libraries_only(log):
    """Remove a Library block ONLY if literally zero datablocks still point
    ``.library`` at it — unlike :func:`_purge_libraries` (which force-removes
    ANY library its ``user_map()`` check misses, safe only because the bulk
    flow has already localized EVERYTHING by the time it runs), this is the
    one safe for a deliberately PARTIAL/selective localize pass: some rows
    were left ticked-off on purpose (still linked), and must survive (docs/
    TODO.md #22 — confirmed via a live probe that the shared helper silently
    deleted a still-linked, still-in-use Object left un-ticked, because
    ``user_map()`` doesn't count a plain ``.library`` reference as "using"
    the Library block at all). Also skips purging linked orphans (``do_
    linked_ids=False``) for the same reason — only touch what was actually
    selected."""
    for _ in range(20):
        if not bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True):
            break
    still_used = {db.library for coll in _id_collections() for db in coll
                 if db.library is not None}
    for lib in list(bpy.data.libraries):
        if lib not in still_used:
            try:
                bpy.data.libraries.remove(lib)
            except RuntimeError:
                pass
    log.info("F2 purge (selected): %d librar(ies) remain", len(bpy.data.libraries))


def localize_steps(log, max_passes: int = 50):
    """Make every linked / overridden datablock local, incrementally.

    A generator: yields ``(fraction, status)`` after the bulk pass and after each
    ~100-datablock chunk, so a modal can repaint + honour ESC between yields.
    Drain it fully (``for _ in localize_steps(log): pass``) for synchronous use.

    One bulk ``make_local(type='ALL')`` does most of the work; the per-ID passes
    then resolve overrides / linked collections / node groups. Each pass logs a
    heartbeat and the per-datablock name at DEBUG (so the debug log's last line
    pinpoints a hanging call), and the loop stops early if a pass makes no
    progress (circular links / un-resolvable overrides) so it can never grind."""
    yield (0.02, "Making objects local…")
    _bulk_make_local(log)

    prev = None
    for n in range(1, max_passes + 1):
        remaining = _remaining_linked()
        count = len(remaining)
        log.info("F2 localize pass %d: %d linked/override datablock(s) remaining", n, count)
        if count == 0:
            break
        if prev is not None and count >= prev:
            log.warning("F2 localize: no progress at %d remaining — stopping (likely circular "
                        "links or un-resolvable overrides)", count)
            break
        prev = count
        for i, db in enumerate(remaining, 1):
            log.debug("F2 make_local: %s", db.name)  # last line = culprit if a call hangs
            try:
                db.make_local(clear_liboverride=True)
            except (RuntimeError, ReferenceError):
                pass
            if i % 100 == 0:
                log.info("F2 localize pass %d: %d/%d datablocks", n, i, count)
                yield (0.05 + 0.85 * (i / count), f"Localizing {i}/{count} (pass {n})")
        yield (0.9, f"Localized (pass {n})")

    yield (0.95, "Purging libraries…")
    _purge_libraries(log)
    yield (1.0, "Done")


def localize_selected_steps(log, targets: list, max_passes: int = 50):
    """Make ONLY ``targets`` (already-resolved datablocks) local, chunked.
    Unlike :func:`localize_steps`, this deliberately skips the fast bulk
    ``bpy.ops.object.make_local(type='ALL')`` pass — that operator has no
    per-item filter, so it would localize things the user un-ticked. Pure
    per-ID ``make_local()`` calls are the only mechanism with real per-item
    granularity (docs/TODO.md #22) — slower on a huge ticked set than the
    bulk path, a known, accepted trade-off of selective apply.

    Multi-pass, same shape as :func:`localize_steps`'s own retry loop —
    confirmed via a live probe that a SINGLE pass isn't enough: ``ID.
    make_local()`` on a datablock needs at least one already-LOCAL user to
    attach the new local copy to, so e.g. a material used only by a mesh
    that itself only just became local THIS pass silently no-ops until the
    next pass re-checks it. Scoped to the ORIGINAL ticked set only (re-
    deriving "remaining" from the whole file, like the bulk version does,
    would silently pull in un-ticked items too)."""
    total = len(targets) or 1
    prev = None
    for n in range(1, max_passes + 1):
        remaining = [db for db in targets if db.library is not None]
        count = len(remaining)
        log.info("F2 localize (selected) pass %d: %d/%d remaining", n, count, total)
        if count == 0:
            break
        if prev is not None and count >= prev:
            log.warning("F2 localize (selected): no progress at %d remaining — stopping "
                       "(likely circular links or un-resolvable overrides)", count)
            break
        prev = count
        for i, db in enumerate(remaining, 1):
            log.debug("F2 make_local (selected): %s", db.name)
            try:
                db.make_local(clear_liboverride=True)
            except (RuntimeError, ReferenceError):
                pass
            if i % 100 == 0 or i == count:
                yield (0.05 + 0.85 * (i / count), f"Localizing {i}/{count} (selected, pass {n})")
    yield (0.95, "Purging libraries…")
    _purge_empty_libraries_only(log)
    yield (1.0, "Done")


class FILELINK_OT_make_local(bpy.types.Operator):
    bl_idname = "filelink.make_local"
    bl_label = "Make All Local"
    bl_description = "Recursively make every linked asset local (report first, then apply)"
    bl_options = {"REGISTER"}

    mode: bpy.props.EnumProperty(
        name="Mode",
        items=[
            ("NEW_FILE", "New File", "Write a separate fully-local copy; leave this file untouched"),
            ("IN_PLACE", "In Place", "Flatten this file to local (a backup is taken first)"),
        ],
        default="NEW_FILE",
    )  # type: ignore[valid-type]

    filepath: bpy.props.StringProperty(
        name="Output",
        description="Destination for the local copy (New File mode). Defaults to "
        "<name>_local.blend next to the current file",
        subtype="FILE_PATH",
        default="",
    )  # type: ignore[valid-type]

    apply: bpy.props.BoolProperty(
        name="Apply",
        description="Perform the make-local. Leave off for a report-only dry run",
        default=False,
    )  # type: ignore[valid-type]

    # ---- modal state ----
    _timer = None
    _gen = None
    _log = None
    _out = ""
    _backup = None
    _n_items = 0
    _n_collisions = 0  # name collisions found pre-mutation, surfaced again in the final message
    _aborted = ""  # set by _apply_steps when it gives up early (no work / setup error)

    @classmethod
    def description(cls, context, properties):
        if not properties.apply:
            return "List everything linked into this file, grouped by library (no changes)"
        if properties.mode == "NEW_FILE":
            return ("Write a fully-local copy beside this file (<name>_local.blend) and leave "
                    "this file's links untouched (the session is reverted). Save the file first")
        return ("Make every linked asset in THIS file local. Takes a timestamped backup "
                "first. Runs with a progress bar — press ESC to cancel")

    # ---- shared helpers ----

    def _prepare(self, context, log):
        """Build + stash the F2 report; return (items, summary message)."""
        items = _gather_linked()
        report = build_makelocal_report(items, _gather_all_names())
        from .report_store import stash_report

        stash_report(context, report, "f2")
        _populate_makelocal_rows(context, items)
        for f in report.findings:
            log.info("F2 [%s] %s: %s", f.severity, f.category, f.message)
        summary = next((f for f in report.findings if f.category == "summary"), None)
        self._n_collisions = summary.data.get("collisions", 0) if summary else 0
        return items, (summary.message if summary else "scan complete")

    def _setup_apply(self, context, items):
        """Resolve output path / take the in-place backup before any mutation.
        Returns an error string to abort with, or None on success."""
        self._n_items = len(items)
        if self.mode == "NEW_FILE":
            src = bpy.data.filepath
            if not src:
                return "Save the file first (New File mode reverts the session)"
            self._out = (bpy.path.abspath(self.filepath) if self.filepath
                         else os.path.splitext(src)[0] + "_local.blend")
            self._backup = None
        else:  # IN_PLACE: back up the original before we flatten it
            from .safety import auto_backup

            self._backup = auto_backup(context)
        return None

    def _finalize_apply(self, context):
        """Save the copy + revert (New File) or report the flattened result."""
        # docs/TODO.md Group 6 #19, 2026-06-27: name collisions found pre-mutation
        # (core.f2_makelocal.find_rename_collisions) mean SOMETHING just got
        # auto-renamed -- flagged again here, not just in the pre-apply report,
        # since this is the moment a file that links one of those names by
        # name would actually break.
        collide = (f" {self._n_collisions} name collision(s) were renamed — re-check any "
                   f"other file linking this one by name." if self._n_collisions else "")
        if self.mode == "NEW_FILE":
            self._log.debug("F2 NEW_FILE: writing %s", self._out)
            bpy.ops.wm.save_as_mainfile(filepath=self._out, copy=True)
            bpy.ops.wm.revert_mainfile()  # restore the original linked session
            self.report(
                {"WARNING" if self._n_collisions else "INFO"},
                f"Wrote fully-local copy: {self._out} ({self._n_items} datablock(s) localized). "
                f"This file left unchanged.{collide}",
            )
        else:  # IN_PLACE
            tail = (f"Backup: {self._backup}" if self._backup
                    else "(no backup written — save the file to enable backups)")
            self.report(
                {"WARNING"},
                f"Localized {self._n_items} datablock(s); {len(bpy.data.libraries)} librar(ies) "
                f"remain. {tail}{collide}",
            )
        return {"FINISHED"}

    # ---- synchronous path (EXEC_DEFAULT / scripting / tests) ----

    def execute(self, context):
        from ..log import get_logger

        self._log = log = get_logger()
        items, msg = self._prepare(context, log)

        if not self.apply:
            self.report({"INFO"}, msg + " (dry run)")
            return {"FINISHED"}
        if not items:
            self.report({"INFO"}, "Nothing linked — already fully local")
            return {"FINISHED"}

        err = self._setup_apply(context, items)
        if err:
            self.report({"ERROR"}, err)
            return {"CANCELLED"}

        for _ in localize_steps(log):  # drain synchronously
            pass
        return self._finalize_apply(context)

    # ---- modal path (interactive, with progress + ESC) ----

    def _apply_steps(self, context, log):
        """The WHOLE apply path as one generator (docs/TODO.md Group 6 #18,
        2026-06-27): gathering every linked datablock + (for IN_PLACE) writing
        the pre-mutation backup used to run synchronously in invoke(), BEFORE
        the modal/progress bar existed — on a huge file that gather + backup
        write (can be minutes) showed nothing at all. Now the modal/timer
        starts FIRST and these heavy phases are simply the early steps of the
        same generator, so status text is live throughout. Sets
        ``self._aborted`` instead of returning early so ``modal()`` can report
        the right message/result once the generator actually stops."""
        yield (0.0, "Scanning linked data…")
        items, _msg = self._prepare(context, log)
        if not items:
            self._aborted = "Nothing linked — already fully local"
            return
        yield (0.01, "Backing up…" if self.mode == "IN_PLACE" else "Preparing…")
        err = self._setup_apply(context, items)
        if err:
            self._aborted = err
            return
        yield from localize_steps(log)

    def invoke(self, context, event):
        from ..log import get_logger

        self._log = log = get_logger()
        self._aborted = ""

        if not self.apply:  # report-only is cheap — no modal needed
            items, msg = self._prepare(context, log)
            self.report({"INFO"}, msg + " (dry run)")
            return {"FINISHED"}

        from .progress import set_progress

        self._gen = self._apply_steps(context, log)
        wm = context.window_manager
        wm.progress_begin(0, 100)
        set_progress(context, 0.0, "Starting make-local…")
        context.workspace.status_text_set("FileLink: making local… (ESC to cancel)")
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            return self._cancel(context)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        from .progress import set_progress

        # One chunk per tick: each yield is already ~100 datablocks (or the bulk
        # pass) of work, so the UI repaints between chunks and ESC stays live.
        try:
            fraction, status = next(self._gen)
        except StopIteration:
            self._teardown(context)
            if self._aborted:
                ok = self._aborted.startswith("Nothing linked")
                self.report({"INFO"} if ok else {"ERROR"}, self._aborted)
                return {"FINISHED"} if ok else {"CANCELLED"}
            return self._finalize_apply(context)

        context.window_manager.progress_update(int(fraction * 100))
        set_progress(context, fraction, status)
        return {"RUNNING_MODAL"}

    def _teardown(self, context):
        from .progress import clear_progress

        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        wm.progress_end()
        clear_progress(context)
        context.workspace.status_text_set(None)

    def _cancel(self, context):
        self._teardown(context)
        if self.mode == "NEW_FILE":
            # Nothing has been written yet; restore the original linked session.
            try:
                bpy.ops.wm.revert_mainfile()
            except RuntimeError:
                pass
            self.report({"WARNING"}, "Make Local cancelled — this file left unchanged")
        else:
            tail = f" Backup: {self._backup}" if self._backup else ""
            self.report({"WARNING"},
                        f"Make Local cancelled — this file is partially localized.{tail}")
        return {"CANCELLED"}


class FILELINK_OT_make_local_selected(bpy.types.Operator):
    """Per-datablock Make Local (docs/TODO.md #22) — the ticked-selection
    counterpart to "Make All Local", same shape as ``filelink.merge_
    material_selected``/``instance_geometry_selected``/``purge_orphans_
    selected``. Modal (unlike those 3): this is the one apply path in the
    codebase already known to be slow on large ticked sets (it can't use the
    fast bulk operator — see :func:`localize_selected_steps`), so it needs
    its own progress bar + ESC rather than a plain single-shot ``execute``."""

    bl_idname = "filelink.make_local_selected"
    bl_label = "Make Local Selected"
    bl_description = ("Make each ticked linked datablock local (per-item, not the fast bulk "
                      "pass). Takes a backup first. Runs with a progress bar — press ESC to cancel")
    bl_options = {"REGISTER"}

    _timer = None
    _gen = None
    _log = None
    _backup = None
    _targets: list = []

    def cancel_message(self):
        return "Make Local Selected cancelled (backup preserved)"

    def _apply_steps(self, context, log):
        from .safety import auto_backup

        self._targets = _resolve_selected(context.window_manager.filelink_makelocal_rows)
        yield (0.0, "Backing up…")
        self._backup = auto_backup(context)
        yield from localize_selected_steps(log, self._targets)

    def invoke(self, context, event):
        from ..log import get_logger
        from .progress import set_progress

        self._log = log = get_logger()
        targets = _resolve_selected(context.window_manager.filelink_makelocal_rows)
        if not targets:
            self.report({"WARNING"}, "Tick at least one linked datablock")
            return {"CANCELLED"}

        self._gen = self._apply_steps(context, log)
        wm = context.window_manager
        wm.progress_begin(0, 100)
        set_progress(context, 0.0, "Starting make-local (selected)…")
        context.workspace.status_text_set("FileLink: making selected local… (ESC to cancel)")
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        from ..log import get_logger

        self._log = log = get_logger()
        targets = _resolve_selected(context.window_manager.filelink_makelocal_rows)
        if not targets:
            self.report({"WARNING"}, "Tick at least one linked datablock")
            return {"CANCELLED"}
        for _ in self._apply_steps(context, log):  # drain synchronously
            pass
        return self._finalize(context)

    def modal(self, context, event):
        if event.type == "ESC":
            return self._cancel(context)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        from .progress import set_progress

        try:
            fraction, status = next(self._gen)
        except StopIteration:
            self._teardown(context)
            return self._finalize(context)

        context.window_manager.progress_update(int(fraction * 100))
        set_progress(context, fraction, status)
        return {"RUNNING_MODAL"}

    def _finalize(self, context):
        wm = context.window_manager
        # Count ACTUAL successes (.library is None now), not just attempted —
        # a ticked child (mesh/material) whose OWNING object was left un-
        # ticked can never actually localize (confirmed via a live probe:
        # ID.make_local() needs at least one already-local user to attach
        # the new local copy to), so "attempted" would silently overstate
        # what really happened.
        localized = sum(1 for db in self._targets if db.library is None)
        failed = len(self._targets) - localized
        wm.filelink_makelocal_rows.clear()
        wm.filelink_makelocal_active = 0
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {self._backup}" if self._backup else " (no backup written)"
        fail_note = (f" {failed} could NOT be localized — their owning object may still be "
                    "linked (tick it too) or the reference is circular/unresolvable."
                    if failed else "")
        self.report({"WARNING"} if failed else {"INFO"},
                    f"Localized {localized} selected datablock(s); "
                    f"{len(bpy.data.libraries)} librar(ies) remain.{tail}{fail_note} "
                    "Re-run Make Local to see any remaining.")
        return {"FINISHED"}

    def _teardown(self, context):
        from .progress import clear_progress

        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        wm.progress_end()
        clear_progress(context)
        context.workspace.status_text_set(None)

    def _cancel(self, context):
        self._teardown(context)
        tail = f" Backup: {self._backup}" if self._backup else ""
        self.report({"WARNING"},
                    f"Make Local Selected cancelled — this file is partially localized.{tail}")
        return {"CANCELLED"}
