"""Instance duplicate geometry: collapse identical-but-separate mesh datablocks
onto one shared datablock so the objects become instances (saving memory).

Report-first by default; on Apply (after auto-backup) each duplicate's users are
remapped onto the canonical via ``ID.user_remap`` and the now-unused local
datablocks are removed. Currently covers meshes; the engine is kind-agnostic so
curves/others can be added by extending the gather + a fingerprint.

Modal: fingerprinting every mesh is the heavy part, chunked through
:func:`_gather_steps` (progress bar + ESC). ``_gather`` keeps a synchronous path
for tests/scripting.
"""

import bpy

from ..core.geometry_dedup import build_instance_plan
from .progress import ModalProgressMixin

_FP_CHUNK = 32  # meshes fingerprinted between progress yields


def _mesh_id(me) -> str:
    if me.library is not None:
        return f"{me.name} [{bpy.path.basename(me.library.filepath) or 'linked'}]"
    return me.name


def _gather_steps(context):
    """Fingerprint every mesh, yielding ``(fraction, status)`` every ``_FP_CHUNK``.
    Returns ``(items, id_to_db)`` (via the generator's value)."""
    from .extract import extract_mesh
    from ..core.fingerprint import fingerprint_mesh

    meshes = list(bpy.data.meshes)
    total = len(meshes) or 1
    items, id_to_db = [], {}
    for i, me in enumerate(meshes, 1):
        mid = _mesh_id(me)
        id_to_db[mid] = me
        # A missing-linked-data placeholder mesh (ID.is_missing) has no real
        # vertex/polygon arrays allocated — reading them is a native access
        # violation, not a catchable Python exception (confirmed via crash4,
        # 2026-06-25: EXCEPTION_ACCESS_VIOLATION inside extract_mesh while
        # walking bpy.data.meshes during Analyze All). Skip before extracting,
        # same as every other generic bpy.data walk in this project already does.
        if getattr(me, "is_missing", False):
            fp = None
        else:
            try:
                fp = fingerprint_mesh(extract_mesh(me))
            except Exception:
                fp = None
        items.append({
            "id": mid,
            "name": me.name,
            "kind": "Mesh",
            "fingerprint": fp,
            "linked": me.library is not None,
            "users": me.users,
        })
        if i % _FP_CHUNK == 0:
            yield (0.8 * i / total, f"Fingerprinting meshes {i}/{total}…")
    return items, id_to_db


def _gather(context):
    """Synchronous gather (drains :func:`_gather_steps`). Kept for tests/scripting."""
    gen = _gather_steps(context)
    try:
        while True:
            next(gen)
    except StopIteration as done:
        return done.value


class ASSETDOCTOR_OT_instance_geometry(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "assetdoctor.instance_geometry"
    bl_label = "Instance Duplicate Geometry"
    bl_description = "Find identical separate meshes and make their objects share one (instancing)"
    bl_options = {"REGISTER"}

    apply: bpy.props.BoolProperty(
        name="Apply",
        description="Remap duplicate meshes onto one shared datablock and remove the copies. "
        "Takes a backup first. Leave off for a report-only dry run",
        default=False,
    )  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        if properties.apply:
            return ("Collapse identical separate meshes onto one shared datablock so the objects "
                    "become instances (saves memory). Takes a backup first")
        return "Report identical separate meshes that could be instanced to save memory (no changes)"

    def cancel_message(self):
        return "Geometry instancing cancelled" + (" (backup preserved)" if self.apply else "")

    def run_steps(self, context):
        from ..log import get_logger
        from .report_store import stash_report

        log = get_logger()
        items, id_to_db = yield from _gather_steps(context)

        yield (0.85, "Building report…")
        report, plan = build_instance_plan(items)
        stash_report(context, report, "geo")
        for f in report.findings:
            log.info("GEO [%s] %s: %s", f.severity, f.category, f.message)
        summary = next((f for f in report.findings if f.category == "summary"), None)
        msg = summary.message if summary else "scan complete"

        if not self.apply or not plan:
            level = "WARNING" if report.count("warning") else "INFO"
            self.report({level}, msg + (" (dry run)" if not self.apply else ""))
            return

        from .safety import auto_backup

        yield (0.9, "Backing up…")
        backup = auto_backup(context)
        yield (0.95, "Instancing duplicates…")
        remapped, removed = 0, 0
        for group in plan:
            canonical = id_to_db.get(group["canonical"])
            if canonical is None:
                continue
            for vid in group["victims"]:
                victim = id_to_db.get(vid)
                if victim is None or victim == canonical:
                    continue
                victim.user_remap(canonical)
                log.debug("GEO remap %s -> %s", vid, group["canonical"])
                remapped += 1
                if victim.library is None and victim.users == 0:
                    bpy.data.meshes.remove(victim)
                    removed += 1

        tail = f"Instanced {remapped}, removed {removed} duplicate mesh(es)."
        tail += f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"{msg}. {tail}")
