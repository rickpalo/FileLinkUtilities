"""F3 - find duplicate / multi-resolution materials and remap them to one source.

Report-first by default; on Apply (after auto-backup) every duplicate's users
are remapped onto the chosen canonical via ``ID.user_remap`` and local victims
are removed. Linked victims keep existing in their library (we only repoint
their local users).

Runs as a modal operator: fingerprinting every material is the heavy part, so it
is chunked through :func:`_gather_steps` (progress bar + ESC). ``_gather`` keeps a
synchronous path for tests/scripting.
"""

import bpy

from ..core import datablock_dedup as dd
from ..core.f3_materials import build_dedup_plan, parse_name_list
from ..prefs import get_prefs
from .progress import ModalProgressMixin

_FP_CHUNK = 32  # materials fingerprinted between progress yields


def _populate_material_families(context, plan: list[dict]) -> None:
    """Refill ``filelink_mat_families`` (one row per fingerprint-identical
    cluster) from ``build_dedup_plan``'s ``plan`` — the actionable, keeper-
    dropdown shape every other dedup section already has (user feedback,
    2026-06-25: Find Duplicate Materials reported findings but gave no way
    to act on them). Defaults each row's keeper to the SAME canonical
    ``build_dedup_plan`` already picked via the white/black lists in
    Preferences — the dropdown only matters when the user wants to override
    that pick for one specific group."""
    wm = context.window_manager
    coll = wm.filelink_mat_families
    coll.clear()
    linked_total = 0
    for group in plan:
        members = [group["canonical"], *group["victims"]]
        row = coll.add()
        row.name = group["canonical"]
        row.members = "\n".join(members)
        row.selected = True
        row.removable = len(group["victims"])
        linked_total += len(group["linked_victims"])
    wm.filelink_mat_index = 0
    wm.filelink_mat_removable = sum(len(g["victims"]) for g in plan)
    wm.filelink_mat_linked = linked_total
    wm.filelink_mat_scanned = True


def _populate_material_conflicts(context, items: list[dict]) -> None:
    """Same-``.NNN``-name-family materials that didn't end up in one content-
    merge group — informational only (content fingerprint still gates every
    actual merge, unchanged). Reuses the generic name-family + fingerprint
    conflict algorithm every other dedup section already relies on, fed with
    this scan's own material fingerprints."""
    wm = context.window_manager
    members = [dd.MemberInfo(name=it["name"], fingerprint=it["fingerprint"] or "")
              for it in items]
    conflicts = dd.plan_merges(members)[1]
    wm.filelink_mat_conflicts = len(conflicts)
    wm.filelink_mat_conflicts_text = "\n".join(
        f"{c.base} — {c.reason} ({', '.join(c.members)})" for c in conflicts)


def _material_id(mat) -> str:
    """Unique, human-readable key (handles a local + linked same-named pair)."""
    if mat.library is not None:
        return f"{mat.name} [{bpy.path.basename(mat.library.filepath) or 'linked'}]"
    return mat.name


def _max_texture_res(mat) -> int:
    if not mat.use_nodes or mat.node_tree is None:
        return 0
    best = 0
    for node in mat.node_tree.nodes:
        img = getattr(node, "image", None)
        if img is not None and len(img.size) >= 1:
            best = max(best, max(img.size))
    return best


def _gather_steps(context):
    """Fingerprint every material, yielding ``(fraction, status)`` every
    ``_FP_CHUNK``. Returns ``(items, id_to_mat)`` (via the generator's value)."""
    from .extract import extract_material
    from ..core.fingerprint import fingerprint_material

    prefs = get_prefs(context)
    res_pattern = prefs.resolution_token_regex if prefs else None

    mats = list(bpy.data.materials)
    total = len(mats) or 1
    items, id_to_mat = [], {}
    for i, mat in enumerate(mats, 1):
        mid = _material_id(mat)
        id_to_mat[mid] = mat
        # A missing-linked-data placeholder material (ID.is_missing) has no real
        # node-tree data allocated — walking it is a native access violation, not
        # a catchable Python exception (same disease confirmed for meshes via
        # crash4, 2026-06-25 -- see ops/instance_dedup.py). Skip the deep reads
        # entirely rather than relying on try/except.
        if getattr(mat, "is_missing", False):
            fp, max_res = None, 0
        else:
            try:
                fp = fingerprint_material(extract_material(mat, res_pattern))
            except Exception:
                fp = None
            max_res = _max_texture_res(mat)
        items.append({
            "id": mid,
            "name": mat.name,
            "fingerprint": fp,
            "linked": mat.library is not None,
            "max_res": max_res,
        })
        if i % _FP_CHUNK == 0:
            yield (0.8 * i / total, f"Fingerprinting materials {i}/{total}…")
    return items, id_to_mat


def _gather(context):
    """Synchronous gather (drains :func:`_gather_steps`). Kept for tests/scripting."""
    gen = _gather_steps(context)
    try:
        while True:
            next(gen)
    except StopIteration as done:
        return done.value


class FILELINK_OT_material_dedup(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "filelink.material_dedup"
    bl_label = "Find Duplicate Materials"
    bl_description = "Find duplicate / multi-resolution materials and remap them to a single source"
    bl_options = {"REGISTER"}

    apply: bpy.props.BoolProperty(
        name="Apply (remap & purge)",
        description="Remap duplicates onto the canonical material and remove local victims. "
        "Takes a backup first. Leave off for a report-only dry run",
        default=False,
    )  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        if properties.apply:
            return ("Remap duplicate/near-duplicate (incl. 1K/2K) materials onto a single "
                    "canonical and remove local duplicates. Takes a backup first")
        return ("Find duplicate / multi-resolution materials and report which would be merged "
                "(no changes). Canonical chosen via the white/black lists in Preferences")

    def cancel_message(self):
        return "Material dedup cancelled" + (" (backup preserved)" if self.apply else "")

    def run_steps(self, context):
        from ..log import get_logger
        from .report_store import stash_report

        log = get_logger()
        prefs = get_prefs(context)
        whitelist = parse_name_list(prefs.material_whitelist if prefs else "")
        blacklist = parse_name_list(prefs.material_blacklist if prefs else "")
        prefer_linked = bool(prefs and prefs.material_keep_preference == "LINKED")

        items, id_to_mat = yield from _gather_steps(context)

        yield (0.85, "Building report…")
        report, plan = build_dedup_plan(items, whitelist, blacklist, prefer_linked)
        stash_report(context, report, "f3")
        _populate_material_families(context, plan)
        _populate_material_conflicts(context, items)
        for f in report.findings:
            log.info("F3 [%s] %s: %s", f.severity, f.category, f.message)
        n_victims = sum(len(g["victims"]) for g in plan)
        n_linked = sum(len(g["linked_victims"]) for g in plan)
        msg = (f"{len(plan)} duplicate group(s); {n_victims} material(s) remappable "
               f"({n_linked} linked stay in library)" if plan
               else "No duplicate materials found")

        if not self.apply or not plan:
            level = "WARNING" if report.count("warning") else "INFO"
            self.report({level}, msg + (" (dry run)" if not self.apply else ""))
            return

        from .safety import auto_backup

        yield (0.9, "Backing up…")
        backup = auto_backup(context)
        yield (0.95, "Remapping duplicates…")
        remapped, removed = 0, 0
        for group in plan:
            canonical = id_to_mat.get(group["canonical"])
            if canonical is None:
                continue
            for vid in group["victims"]:
                victim = id_to_mat.get(vid)
                if victim is None or victim == canonical:
                    continue
                victim.user_remap(canonical)
                log.debug("F3 remap %s -> %s", vid, group["canonical"])
                remapped += 1
                # Remove now-unused local victims; linked ones stay in their library.
                if victim.library is None and victim.users == 0:
                    bpy.data.materials.remove(victim)
                    removed += 1

        tail = f"Remapped {remapped}, removed {removed} local duplicate(s)."
        tail += f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"{msg}. {tail}")


class FILELINK_OT_merge_material_selected(bpy.types.Operator):
    bl_idname = "filelink.merge_material_selected"
    bl_label = "Merge Selected Duplicates"
    bl_description = ("Merge each ticked group into its chosen keeper (remap users, "
                      "remove local duplicates). Takes a backup first")
    bl_options = {"REGISTER"}

    def execute(self, context):
        wm = context.window_manager
        chosen = [row for row in wm.filelink_mat_families if row.selected]
        if not chosen:
            self.report({"WARNING"}, "Tick at least one group to merge")
            return {"CANCELLED"}

        from .safety import auto_backup

        # Cheap re-resolve (no fingerprinting needed to merge) — ids are
        # already verified content-identical by the scan that built these rows.
        id_to_mat = {_material_id(m): m for m in bpy.data.materials}

        backup = auto_backup(context)
        remapped = removed = 0
        for row in chosen:
            members = [n for n in row.members.split("\n") if n]
            keeper_id = row.keeper or (members[0] if members else "")
            keeper = id_to_mat.get(keeper_id)
            if keeper is None:
                continue
            for vid in dd.victims_for_keeper(members, keeper_id):
                victim = id_to_mat.get(vid)
                if victim is None or victim == keeper:
                    continue
                victim.user_remap(keeper)
                remapped += 1
                # Linked victims stay in their library (only their local
                # users are repointed) — same rule the old bulk-apply path
                # used, NOT the generic Duplicate Data-blocks tool's "skip
                # linked entirely" (materials' victims_for_keeper already
                # verified content-identity, so remapping a linked one's
                # local users is safe; only REMOVAL needs local ownership).
                if victim.library is None and victim.users == 0:
                    bpy.data.materials.remove(victim)
                    removed += 1

        try:
            context.view_layer.update()
        except Exception:
            pass

        # A deep re-fingerprint is too heavy to auto-run synchronously here
        # (same call as the other dedup tools' post-merge UX) — clear +
        # prompt re-scan.
        wm.filelink_mat_families.clear()
        wm.filelink_mat_removable = 0
        wm.filelink_mat_linked = 0
        wm.filelink_mat_scanned = False
        wm.filelink_mat_conflicts = 0
        wm.filelink_mat_conflicts_text = ""
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Remapped {remapped}, removed {removed} local duplicate(s). "
                    f"Save to persist.{tail} Re-run Find to see any remaining.")
        return {"FINISHED"}
