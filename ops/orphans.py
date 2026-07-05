"""F4 - find orphans & fake-user-only data, group identical ones.

Read-only report by default. Optional purge of true orphans (users==0) runs the
report-first/auto-backup safety model. Clearing fake users / remapping identical
duplicates is intentionally left to the user (or to F3 for materials) since it
reflects intent, not just cleanup.

Modal: classifying + fingerprinting every datablock is the heavy part, chunked
through :func:`_gather_steps` (progress bar + ESC). ``_gather`` keeps a
synchronous path for tests/scripting.
"""

import bpy

from ..core.f4_orphans import build_orphan_report
from .progress import ModalProgressMixin

_FP_CHUNK = 64  # datablocks processed between progress yields


def _collections():
    return [
        ("Material", bpy.data.materials),
        ("Mesh", bpy.data.meshes),
        ("Image", bpy.data.images),
        ("NodeGroup", bpy.data.node_groups),
        ("Texture", bpy.data.textures),
        ("Object", bpy.data.objects),
        ("Armature", bpy.data.armatures),
        ("Curve", bpy.data.curves),
    ]


def _gather_steps(context):
    """Collect datablock info dicts across the common asset collections, yielding
    ``(fraction, status)`` every ``_FP_CHUNK``. Returns ``(items, skipped)`` —
    ``skipped`` is every ``(label, reason)`` a fingerprintable datablock was
    deliberately NOT read because doing so risks a native crash (see
    ``extract.datablock_risk_reason`` — a missing placeholder or Library
    Override's geometry/node-tree/image data can be incomplete or dangling on
    a file with known override/dependency loops; real crash,
    EXCEPTION_ACCESS_VIOLATION, 2026-07-03/04, `fingerprint_mesh` via this
    exact scan). Mirrors ``ops.datablock_dup``'s shape-key skip pattern:
    report by name instead of silently dropping into "unverified."

    Materials/meshes/images get a content fingerprint (for identity grouping);
    other types are still classified as orphan/fake-only but not clustered.
    """
    from .extract import datablock_risk_reason, extract_image, extract_material, extract_mesh
    from ..core.fingerprint import (
        fingerprint_image,
        fingerprint_material,
        fingerprint_mesh,
    )

    fp_for = {
        "Material": lambda d: fingerprint_material(extract_material(d)),
        "Mesh": lambda d: fingerprint_mesh(extract_mesh(d)),
        "Image": lambda d: fingerprint_image(extract_image(d)),
    }
    collections = _collections()
    total = sum(len(coll) for _, coll in collections) or 1

    items = []
    skipped: list[tuple[str, str]] = []
    done = 0
    for type_name, coll in collections:
        maker = fp_for.get(type_name)
        for db in coll:
            linked = db.library is not None
            fingerprint = None
            if maker is not None and not linked:
                reason = datablock_risk_reason(db)
                if reason:
                    skipped.append((f"{type_name}: {db.name}", reason))
                else:
                    try:
                        fingerprint = maker(db)
                    except Exception:
                        fingerprint = None  # never let extraction break the scan
            items.append({
                "type": type_name,
                "name": db.name,
                "users": db.users,
                "fake": db.use_fake_user,
                "linked": linked,
                "fingerprint": fingerprint,
            })
            done += 1
            if done % _FP_CHUNK == 0:
                yield (0.85 * done / total, f"Scanning datablocks {done}/{total}…")
    return items, skipped


def _gather(context):
    """Synchronous gather (drains :func:`_gather_steps`). Kept for tests/scripting."""
    gen = _gather_steps(context)
    try:
        while True:
            next(gen)
    except StopIteration as done:
        return done.value


def _populate_orphan_rows(context, report) -> None:
    """Refill ``filelink_orphan_rows`` (one row per TRUE orphan, Group 11
    #45, 2026-06-26) from the report's ``orphan`` Finding — the actionable
    checkbox shape every other dedup/cleanup section already has. Fake-only
    and identical findings are deliberately NOT mirrored into a WM collection
    here; they stay read-only, drawn straight from the report (see this
    module's own docstring)."""
    wm = context.window_manager
    coll = wm.filelink_orphan_rows
    coll.clear()
    orphan_finding = next((f for f in report.findings if f.category == "orphan"), None)
    for label in (orphan_finding.items if orphan_finding else []):
        row = coll.add()
        row.name = label
        row.selected = True
    wm.filelink_orphan_index = 0


class FILELINK_OT_scan_orphans(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "filelink.scan_orphans"
    bl_label = "Scan Orphans & Fake Users"
    bl_description = "List orphaned and fake-user-only datablocks and group identical ones"
    bl_options = {"REGISTER"}

    purge_orphans: bpy.props.BoolProperty(
        name="Purge Orphans",
        description="After reporting, delete true orphans (users==0). Takes a backup first",
        default=False,
    )  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        if properties.purge_orphans:
            return ("Report orphaned / fake-user-only / identical datablocks, then delete true "
                    "orphans (users==0). Takes a backup first")
        return ("List orphaned datablocks, fake-user-only data, and groups of identical "
                "datablocks (no changes)")

    def cancel_message(self):
        return "Orphan scan cancelled" + (" (backup preserved)" if self.purge_orphans else "")

    def run_steps(self, context):
        from ..log import get_logger
        from .report_store import stash_report

        log = get_logger()
        items, skipped = yield from _gather_steps(context)

        yield (0.9, "Building report…")
        report = build_orphan_report(items)
        stash_report(context, report, "f4")
        _populate_orphan_rows(context, report)
        wm = context.window_manager
        wm.filelink_orphan_skipped_text = "\n".join(
            f"{label} — not read, {reason}" for label, reason in skipped)
        for f in report.findings:
            log.info("F4 [%s] %s: %s", f.severity, f.category, f.message)
        for label, reason in skipped:
            log.warning("F4 skipped %s: %s", label, reason)
        summary = next((f for f in report.findings if f.category == "summary"), None)
        msg = summary.message if summary else "scan complete"
        if skipped:
            msg += f" ({len(skipped)} skipped — unsafe to read, see the list below)"

        if not self.purge_orphans:
            level = "WARNING" if report.count("warning") else "INFO"
            self.report({level}, msg)
            return

        from .safety import auto_backup

        yield (0.95, "Backing up & purging…")
        backup = auto_backup(context)
        purged = bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False,
                                        do_recursive=True)
        context.window_manager.filelink_orphan_rows.clear()
        tail = f"Purged {purged} orphan(s)."
        tail += f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"{msg}. {tail}")


class FILELINK_OT_purge_orphans_selected(bpy.types.Operator):
    """Purge only the ticked orphans from ``filelink_orphan_rows`` (Group
    11 #45, 2026-06-26) — mirrors ``merge_material_selected``'s shape, except
    removal itself uses ``bpy.data.batch_remove`` (the same generic, mixed-
    type-safe primitive Blender's own native orphan purge uses internally),
    since the resolved datablocks span arbitrary types."""

    bl_idname = "filelink.purge_orphans_selected"
    bl_label = "Purge Selected"
    bl_description = "Delete each ticked orphan datablock. Takes a backup first"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from .report_store import resolve_datablock

        wm = context.window_manager
        chosen = [row.name for row in wm.filelink_orphan_rows if row.selected]
        if not chosen:
            self.report({"WARNING"}, "Tick at least one orphan to purge")
            return {"CANCELLED"}

        ids = []
        for label in chosen:
            type_name, _, name = label.partition("/")
            block = resolve_datablock(type_name, name)
            if block is not None:
                ids.append(block)
        if not ids:
            self.report({"WARNING"}, "None of the ticked orphans could be resolved")
            return {"CANCELLED"}

        from .safety import auto_backup

        backup = auto_backup(context)
        bpy.data.batch_remove(ids=ids)

        wm.filelink_orphan_rows.clear()
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Purged {len(ids)} orphan(s). Save to persist.{tail} "
                    f"Re-run Find to see any remaining.")
        return {"FINISHED"}
