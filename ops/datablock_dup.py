"""Batch C #3 — generic "Duplicate Data-blocks" merge tool.

Finds ``.NNN`` name-families across every audited datablock type (mirroring
what the Overrides report (f7live) used to also report, read-only, until that
was removed 2026-06-26 as redundant with this tool — see
``core.datablock_graph.build_live_report``'s docstring). On a real file, most
of those families turn out to be `Action` datablocks from undisciplined
animating (Blender auto-names a new pose action ``ObjectName.PoseName``, then
``.001``, ``.002``, … on every re-take). This mirrors the F6 image-dedup
keeper-dropdown UI (find families → pick a keeper → Merge Selected) but
generalizes it to ANY datablock type via ``ID.user_remap()`` (which is generic,
not image-specific) and ``core.datablock_dedup`` (the same merge-planning
algorithm imagededup already uses, extracted so it isn't reimplemented per
type).

Materials, Meshes and Images are deliberately OUT of scope here — they already
have dedicated, more mature tools (F3 material dedup, F5 geometry instancing, F6
image dedup) with their own verified content fingerprints; duplicating that path
here would just be a second, weaker way to do the same job. Of the remaining
types, Action (``core.fingerprint.fingerprint_action``, F-curve keyframe data)
and Shape Key (``fingerprint_shape_key``, relative-key vertex data keyed to the
owning mesh's OWN geometry fingerprint — a Key's deltas mean nothing without
identifying what mesh they deform, batch C #3's "KEKey" half) have real
fingerprints — everything else still shows up (visibility matters even without
a merge path) but is reported "unverified", per the project's standing safety
rule: name similarity finds candidates, content identity gates the merge. Add a
fingerprinter to ``_fingerprint_for`` to light up another type later.
"""

from __future__ import annotations

import bpy

from ..core import datablock_dedup as dd
from ..core import datablock_graph as dg
from .datablock_inspect import _COLLECTIONS
from .progress import ModalProgressMixin

# Out of scope: F3/F5/F6 already own these types' dedup workflows.
_OUT_OF_SCOPE = {"materials", "meshes", "images"}
_GENERIC_COLLECTIONS = [(label, attr) for label, attr in _COLLECTIONS if attr not in _OUT_OF_SCOPE]

_LABEL_BY_ATTR = dict((attr, label) for label, attr in _COLLECTIONS)


def _fingerprint_for(attr: str, block, skipped: list[tuple[str, str]]) -> str:
    """Content fingerprint for one datablock, or ``""`` if this type has none yet
    (lands as an "unverified" conflict — never silently merged). ``skipped``
    is an out-param (mirrors `core.imagefamily.iter_resolve_group_in_dir`'s
    own ambiguous/skipped_dirs out-params — same reasoning: avoid reshaping
    this function's return just to carry one extra, rare case): appended to
    with ``(name, reason)`` whenever a block was deliberately NOT read because
    doing so risks a native crash (see `extract.shape_key_risk_reason`), so
    the caller can surface WHICH ones by name instead of silently dropping
    them into the generic "unverified" bucket."""
    if attr == "actions":
        from .extract import extract_action
        from ..core.fingerprint import fingerprint_action

        try:
            return fingerprint_action(extract_action(block))
        except Exception:
            return ""
    if attr == "shape_keys":
        from .extract import extract_shape_key, shape_key_risk_reason
        from ..core.fingerprint import fingerprint_shape_key

        reason = shape_key_risk_reason(block)
        if reason:
            skipped.append((block.name, reason))
            return ""
        try:
            return fingerprint_shape_key(extract_shape_key(block))
        except Exception:
            return ""
    return ""


_FP_CHUNK = 32  # members fingerprinted between progress yields — matches
                # ops.material_dedup/instance_dedup's own established pattern


def _gather_steps(context):
    """Fingerprint every LOCAL ``.NNN``-family member across the in-scope
    collections, yielding ``(fraction, status)`` every ``_FP_CHUNK`` members
    (2026-07-04 follow-up: this used to yield only ONCE PER COLLECTION TYPE,
    so a single huge collection — e.g. thousands of Actions in one family
    sweep, the real-world case that motivated this — blocked the whole modal
    tick with no progress update or ESC/Pause opportunity in between; matches
    the finer per-item chunking `ops.material_dedup`/`ops.instance_dedup`
    already use). Returns ``(members, id_by_key, skipped)`` (via the
    generator's value) — ``members`` use ``"{attr}:{name}"`` as their
    :class:`core.datablock_dedup.MemberInfo` name so one ``plan_merges`` call
    naturally keeps each type's families separate (the attr prefix survives
    ``.NNN``-suffix stripping); ``skipped`` is every ``(name, reason)`` a
    type's fingerprinter refused to read safely (currently only shape keys)."""
    members: list[dd.MemberInfo] = []
    id_by_key: dict[tuple[str, str], object] = {}
    skipped: list[tuple[str, str]] = []

    # Pre-scan every collection's family membership first (cheap — just names,
    # no fingerprinting yet) so the total item count is known up front and the
    # fingerprinting loop below can yield on a flat per-item cadence instead
    # of per collection-type.
    per_collection = []
    for label, attr in _GENERIC_COLLECTIONS:
        coll = getattr(bpy.data, attr, None)
        blocks = [b for b in coll if b.library is None] if coll is not None else []
        fams = dg.duplicate_families([b.name for b in blocks])
        family_names = {n for ms in fams.values() for n in ms}
        per_collection.append((label, attr, blocks, family_names))
    total = sum(len(family_names) for _l, _a, _b, family_names in per_collection) or 1

    done = 0
    for label, attr, blocks, family_names in per_collection:
        for block in blocks:
            if block.name not in family_names:
                continue
            id_by_key[(attr, block.name)] = block
            members.append(dd.MemberInfo(name=f"{attr}:{block.name}",
                                         fingerprint=_fingerprint_for(attr, block, skipped),
                                         users=block.users))
            done += 1
            if done % _FP_CHUNK == 0:
                yield (done / total, f"Fingerprinting {label} ({done}/{total})…")
    return members, id_by_key, skipped


def _populate_datablock_families(context, plans, conflicts, skipped) -> None:
    """Refill ``assetdoctor_datablock_families`` (one row per merge-plan family,
    grouped by KIND in the panel) + the summary counts + the conflict-list and
    skipped-list text."""
    wm = context.window_manager
    coll = wm.assetdoctor_datablock_families
    coll.clear()
    for p in plans:
        attr, base = p.base.split(":", 1)
        members = [n.split(":", 1)[1] for n in (p.canonical, *p.redundant)]
        row = coll.add()
        row.name = p.base
        row.kind = _LABEL_BY_ATTR.get(attr, attr)
        row.collection = attr
        row.members = "\n".join(members)
        row.selected = True
        row.removable = len(p.redundant)
    wm.assetdoctor_datablock_index = 0
    wm.assetdoctor_datablock_removable = dd.removable_count(plans)
    wm.assetdoctor_datablock_conflicts = len(conflicts)

    lines = []
    for c in conflicts:
        attr, base = c.base.split(":", 1)
        names = [n.split(":", 1)[1] for n in c.members]
        lines.append(f"{_LABEL_BY_ATTR.get(attr, attr)}: {base} — {c.reason} ({', '.join(names)})")
    wm.assetdoctor_datablock_conflicts_text = "\n".join(lines)

    wm.assetdoctor_datablock_skipped_text = "\n".join(
        f"Shape Key: {name} — not read, {reason}" for name, reason in skipped)


class ASSETDOCTOR_OT_scan_datablock_dups(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "assetdoctor.scan_datablock_dups"
    bl_label = "Find Duplicate Data-blocks"
    bl_description = (
        "Find .NNN name-family duplicates across Objects, Actions, Node Groups and "
        "other datablock types (Materials/Meshes/Images have their own dedicated "
        "dedup tools already). Verified by content where a fingerprint exists "
        "(currently Actions); everything else is listed but never auto-merged. "
        "Nothing is changed yet"
    )
    bl_options = {"REGISTER"}

    def run_steps(self, context):
        members, _id_by_key, skipped = yield from _gather_steps(context)
        yield (0.95, "Building merge plan…")
        plans, conflicts = dd.plan_merges(members)
        _populate_datablock_families(context, plans, conflicts, skipped)
        wm = context.window_manager
        wm.assetdoctor_datablock_scanned = True
        yield (1.0, "Done")
        n = dd.removable_count(plans)
        tail = f"; {len(skipped)} shape key(s) skipped, unsafe to read (see below)" if skipped else ""
        if plans or conflicts or skipped:
            self.report({"WARNING"} if skipped else {"INFO"},
                        f"{len(plans)} merge group(s); ~{n} removable; "
                        f"{len(conflicts)} differing/unverified{tail}")
        else:
            self.report({"INFO"}, "✓ No duplicate data-blocks found")


class ASSETDOCTOR_OT_merge_datablock_selected(bpy.types.Operator):
    bl_idname = "assetdoctor.merge_datablock_selected"
    bl_label = "Merge Selected Duplicates"
    bl_description = ("Merge each ticked family into its chosen keeper (remap users, "
                      "remove the rest). Takes a backup first")
    bl_options = {"REGISTER"}

    def execute(self, context):
        wm = context.window_manager
        chosen = [row for row in wm.assetdoctor_datablock_families if row.selected]
        if not chosen:
            self.report({"WARNING"}, "Tick at least one family to merge")
            return {"CANCELLED"}

        from .safety import auto_backup

        backup = auto_backup(context)
        removed = 0
        for row in chosen:
            members = [n for n in row.members.split("\n") if n]
            keeper_name = row.keeper or (members[0] if members else "")
            target_coll = getattr(bpy.data, row.collection, None)
            keeper = target_coll.get(keeper_name) if target_coll is not None else None
            if keeper is None:
                continue
            for victim_name in dd.victims_for_keeper(members, keeper_name):
                victim = target_coll.get(victim_name)
                if victim is None or victim == keeper or victim.library is not None:
                    continue
                victim.user_remap(keeper)
                if victim.users == 0:
                    target_coll.remove(victim)
                    removed += 1

        try:
            context.view_layer.update()
        except Exception:
            pass

        # A deep re-fingerprint is too heavy to auto-run synchronously here (same
        # call as image dedup's CONTENT mode) — clear + prompt re-scan.
        wm.assetdoctor_datablock_families.clear()
        wm.assetdoctor_datablock_removable = 0
        wm.assetdoctor_datablock_conflicts = 0
        wm.assetdoctor_datablock_conflicts_text = ""
        wm.assetdoctor_datablock_scanned = False
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Merged and removed {removed} duplicate data-block(s). "
                    f"Save to persist.{tail} Re-run Find to see any remaining.")
        return {"FINISHED"}


