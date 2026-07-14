"""F6 Layer 2/3 — lossless content-overlap image-datablock merge (report + apply).

Mirrors F3 material dedup: find content-identical duplicate images regardless of
name, keep one canonical, ``user_remap`` the rest onto it, and remove the now-
unused local copies. Content identity is VERIFIED by a fingerprint (dimensions +
a file/packed hash) before any merge — name similarity alone never triggers a
merge. Only local images are touched; linked images belong to their source
library.

(History: a narrower, name-only ".NNN family" fast-path scan — "Find .NNN" —
was removed 2026-06-24: confirmed redundant with the content scan below, which
uses the identical fingerprint over every local image, a strict superset of
what the narrower scan ever looked at.)
"""

from __future__ import annotations

import hashlib
import os

import bpy

from ..core import imagededup
from ..core.imagededup import ImgInfo
from .progress import ModalProgressMixin

# Session cache: (path, size, mtime) -> file hash, so repeated scans don't re-read.
_HASH_CACHE: dict[tuple[str, int, int], str] = {}

# Image datablock sources whose content we can fingerprint from a file.
_FILE_SOURCES = {"FILE", "SEQUENCE", "MOVIE", "TILED"}


def _file_hash(path: str) -> str:
    """SHA-1 of a file's bytes, cached by (path, size, mtime). ``""`` if unreadable."""
    try:
        st = os.stat(path)
    except OSError:
        return ""
    key = (path, st.st_size, int(st.st_mtime))
    if key in _HASH_CACHE:
        return _HASH_CACHE[key]
    digest = ""
    try:
        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        digest = h.hexdigest()
    except OSError:
        digest = ""
    _HASH_CACHE[key] = digest
    return digest


def _fingerprint(img) -> str:
    """``"WxH:channels:depth:hash"`` for an image, or ``""`` when it can't be
    verified (missing file, not packed). Packed images hash from their packed data."""
    w, h = (img.size[0], img.size[1]) if len(img.size) >= 2 else (0, 0)
    dims = f"{w}x{h}:{img.channels}:{img.depth}"
    if img.packed_file is not None:
        data = img.packed_file.data
        content = hashlib.sha1(data).hexdigest() if data else ""
    else:
        content = _file_hash(os.path.normpath(bpy.path.abspath(img.filepath)))
    return f"{dims}:{content}" if content else ""


def _fill_families(context, plans, conflicts):
    """Fill ``filelink_dup_families`` + the summary counts from a content-merge
    plan. Each row carries its members (for the keeper dropdown) and a
    representative material.

    ``removable`` counts only LOCAL redundant members — the ones Merge Selected
    will actually remove. A redundant member that's linked (2026-07-14: the
    scan now includes linked images, see ``FILELINK_OT_scan_content_dups``)
    is tracked separately in ``linked_count`` and never merged — it's reported
    so the user knows the cross-library overlap exists, not touched, same rule
    F3 material dedup applies to its own linked victims."""
    from .image_relink import _image_material_map

    wm = context.window_manager
    coll = wm.filelink_dup_families
    coll.clear()
    mat_map = _image_material_map()
    linked_total = 0
    for p in plans:
        members = [p.canonical, *p.redundant]  # canonical first => default keeper
        row = coll.add()
        row.name = p.base
        row.members = "\n".join(members)
        # keeper left at its default (first enum item == canonical); the user may
        # repoint it. Setting a dynamic-enum value explicitly is fragile, so don't.
        row.selected = True
        row.material = next((mat_map[m] for m in members if m in mat_map), "")
        linked_here = sum(1 for m in p.redundant
                          if (img := bpy.data.images.get(m)) is not None and img.library is not None)
        row.removable = len(p.redundant) - linked_here
        row.linked_count = linked_here
        linked_total += linked_here
    wm.filelink_dup_index = 0
    wm.filelink_dup_removable = imagededup.removable_count(plans) - linked_total
    wm.filelink_dup_linked = linked_total
    wm.filelink_dup_conflicts = len(conflicts)
    wm.filelink_dup_conflicts_text = "\n".join(f"{c.base} — {c.reason}" for c in conflicts)


# Below this name-token overlap, a duplicate family's material looks mis-attributed
# (e.g. a lightBlue texture under a brown material) → flag it + offer the eyedropper.
_DUP_MISMATCH_AFFINITY = 0.5


def effective_material(row) -> str:
    """The material a duplicate-texture family displays under: the user's
    eyedropper override if set, else the auto-attributed material (or
    "(no material)"). Shared by the panel's virtualized picker and
    ``FILELINK_OT_dup_material_keeper`` — both used to compute this inline."""
    return row.material_override.name if row.material_override else (row.material or "(no material)")


def is_mismatch(row) -> bool:
    """True when the (effective) material's name barely overlaps the
    texture's own — e.g. a lightBlue texture under a brown material —
    flagged so the user can re-home it via the eyedropper."""
    from ..core.imagematch import name_affinity

    eff = effective_material(row)
    return eff != "(no material)" and name_affinity(row.name, eff) < _DUP_MISMATCH_AFFINITY


def rebuild_dup_tex_picker_rows(wm) -> None:
    """Rebuild ``wm.filelink_duptex_picker_rows`` (Group 12 Phase 3, item 2)
    from the current ``filelink_dup_families`` + expand state.

    Called after every op that changes group MEMBERSHIP (scan / merge) and
    from ``ui.panels``'s ``material_override`` PointerProperty ``update``
    callback — unlike Missing Textures' ``target``, that field can change
    from a bare ``row.prop()`` edit with no operator involved at all, since it
    changes which GROUP a family belongs under (and the mismatch flag/count),
    not just one row's own display."""
    from ..core import picker as picker_mod
    from .report_store import get_expanded

    coll = wm.filelink_dup_families
    if not len(coll):
        wm.filelink_duptex_picker_rows.clear()
        return

    expanded = get_expanded(wm, "filelink_dup_expanded")
    groups: dict[str, list[int]] = {}
    for i, row in enumerate(coll):
        groups.setdefault(effective_material(row), []).append(i)

    specs = []
    for key in sorted(groups, key=str.lower):
        indices = groups[key]
        members_rows = [coll[i] for i in indices]
        removable_here = sum(r.removable for r in members_rows)
        mism = sum(1 for r in members_rows if is_mismatch(r))
        suffix = f", ⚠{mism} mismatch" if mism else ""
        specs.append(picker_mod.GroupSpec(
            key=key,
            label=f"{key}  ({len(indices)} family, {removable_here}{suffix})",
            icon="ERROR" if mism else "MATERIAL",
            members=[picker_mod.MemberRef(ref_index=i) for i in indices],
            has_action=True,
            alert=bool(mism),
        ))
    picker_rows = picker_mod.flatten_group_member_rows(
        specs, expanded, ref_prop="filelink_dup_families")

    picker_coll = wm.filelink_duptex_picker_rows
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


class FILELINK_OT_merge_dup_selected(bpy.types.Operator):
    bl_idname = "filelink.merge_dup_selected"
    bl_label = "Merge Selected Duplicates"
    bl_description = ("Merge each ticked family into its chosen keeper (remap users, "
                      "remove the rest). Takes a backup first")
    bl_options = {"REGISTER"}

    def execute(self, context):
        from .safety import auto_backup

        wm = context.window_manager
        chosen = [row for row in wm.filelink_dup_families if row.selected]
        if not chosen:
            self.report({"WARNING"}, "Tick at least one family to merge")
            return {"CANCELLED"}

        backup = auto_backup(context)
        removed = 0
        for row in chosen:
            members = [n for n in row.members.split("\n") if n]
            keeper_name = row.keeper or (members[0] if members else "")
            keeper = bpy.data.images.get(keeper_name)
            if keeper is None:
                continue
            for victim_name in imagededup.victims_for_keeper(members, keeper_name):
                victim = bpy.data.images.get(victim_name)
                if victim is None or victim == keeper or victim.library is not None:
                    continue
                victim.user_remap(keeper)
                if victim.users == 0:
                    bpy.data.images.remove(victim)
                    removed += 1

        # Defensive: let the dependency graph settle after bulk image removal before
        # the next viewport draw. The relink/merge crash (human_bundle.crash) was the
        # EEVEE draw acquiring a freed image buffer; this is a precaution, NOT a
        # verified fix — the crash still needs isolating (Solid vs Material shading).
        try:
            context.view_layer.update()
        except Exception:
            pass

        # A deep content scan is too heavy to re-run synchronously here; clear the
        # (now partly-merged) list and let the user re-run Find Content Dups.
        wm = context.window_manager
        wm.filelink_dup_families.clear()
        wm.filelink_dup_removable = 0
        wm.filelink_dup_linked = 0
        wm.filelink_dup_conflicts = 0
        wm.filelink_dup_conflicts_text = ""
        rebuild_dup_tex_picker_rows(wm)
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Merged and removed {removed} duplicate texture(s). "
                    f"Save to persist.{tail} Re-run Find Content Dups to see any remaining.")
        return {"FINISHED"}


def _populate_res_variant_members(context, variants) -> None:
    """Refill ``filelink_res_variant_members`` from ``plan_res_variants``
    (item 11, 2026-06-25): one row per member, ``group`` = the variant set's
    key, ``tag`` = its own resolution token. No default keeper — unlike items
    6/7's safe normalizations, picking a default here would silently choose
    WHICH resolution to keep; the user must tick one (or use Select High/Low
    Resolution) before Remove Excess Variants can do anything."""
    coll = context.window_manager.filelink_res_variant_members
    coll.clear()
    for variant in variants:
        for name, res in variant.members:
            item = coll.add()
            item.name = name
            item.group = variant.key
            item.tag = res
            item.selected = False


def _rescan_res_variants(context):
    """Shared by Find Resolution Variants and Remove Excess Variants (the
    latter re-runs this after mutating so the list/report reflect the new
    state)."""
    from . import report_store
    from ..core import imageres

    names = [img.name for img in bpy.data.images if img.library is None]
    variants = imageres.plan_res_variants(names)
    blend_name = os.path.basename(bpy.data.filepath) or "current file"
    report_store.stash_report(context, imageres.build_res_report(variants, blend_name), "f6res")
    _populate_res_variant_members(context, variants)
    return variants


class FILELINK_OT_scan_res_variants(bpy.types.Operator):
    """F6 Layer 2 — report textures that exist at multiple resolutions (1k/2k/…).
    Footprint analysis only: standardizing to one resolution is LOSSY (changes the
    render), so finding never mutates — it stashes a report + the checkbox list,
    and the user decides (Select High/Low Resolution + Remove Excess Variants)."""

    bl_idname = "filelink.scan_res_variants"
    bl_label = "Find Resolution Variants"
    bl_description = ("Report textures present at multiple resolutions (1k/2k/4k) so you "
                      "can decide whether to standardize down. Standardizing is lossy — "
                      "this only reports, never changes anything")
    bl_options = {"REGISTER"}

    def execute(self, context):
        variants = _rescan_res_variants(context)
        if context.area:
            context.area.tag_redraw()
        if variants:
            self.report({"INFO"}, f"{len(variants)} texture(s) at multiple resolutions. "
                        "Tick a preferred resolution per group (or Select High/Low), "
                        "then Remove Excess Variants.")
        else:
            self.report({"INFO"}, "✓ No multi-resolution texture variants found")
        return {"FINISHED"}


class FILELINK_OT_res_variant_keep(bpy.types.Operator):
    """Tick exactly one member per resolution-variant group as the one to
    keep (radio behaviour via checkboxes — Blender has no native radio-
    checkbox), item 11."""

    bl_idname = "filelink.res_variant_keep"
    bl_label = "Keep This Resolution"
    bl_options = {"INTERNAL"}

    index: bpy.props.IntProperty()  # type: ignore[valid-type]

    def execute(self, context):
        coll = context.window_manager.filelink_res_variant_members
        if not (0 <= self.index < len(coll)):
            return {"CANCELLED"}
        group = coll[self.index].group
        for i, item in enumerate(coll):
            if item.group == group:
                item.selected = (i == self.index)
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class FILELINK_OT_res_variant_select(bpy.types.Operator):
    """"Select High/Low Resolution" (item 11): tick every group's highest- or
    lowest-resolution member at once, instead of clicking each group."""

    bl_idname = "filelink.res_variant_select"
    bl_label = "Select Resolution"
    bl_options = {"REGISTER"}

    which: bpy.props.EnumProperty(
        items=[("HIGH", "High", ""), ("LOW", "Low", "")], default="HIGH")  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        return f"Tick the {properties.which.lower()}-resolution member in every group"

    def execute(self, context):
        from ..core import imageres

        coll = context.window_manager.filelink_res_variant_members
        groups: dict[str, list[int]] = {}
        for i, item in enumerate(coll):
            groups.setdefault(item.group, []).append(i)
        pick = max if self.which == "HIGH" else min
        for indices in groups.values():
            best = pick(indices, key=lambda i: imageres.res_value(coll[i].tag))
            for i in indices:
                coll[i].selected = (i == best)
        if context.area:
            context.area.tag_redraw()
        self.report({"INFO"}, f"Selected the {self.which.lower()}-resolution member in "
                    f"{len(groups)} group(s)")
        return {"FINISHED"}


class FILELINK_OT_remove_excess_variants(bpy.types.Operator):
    """"Remove Excess Variants" (item 11): for every group with a ticked
    member, transfer every OTHER member's users onto it and delete them."""

    bl_idname = "filelink.remove_excess_variants"
    bl_label = "Remove Excess Variants"
    bl_description = ("For each group with a ticked resolution, transfer every OTHER "
                      "member's users onto it and delete them. LOSSY — this changes "
                      "the render wherever the removed resolution was used. Takes a "
                      "backup first")
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ..core import datablock_dedup as dd

        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the file first")
            return {"CANCELLED"}

        coll = context.window_manager.filelink_res_variant_members
        groups: dict[str, list] = {}
        for item in coll:
            groups.setdefault(item.group, []).append(item)

        targets = []
        for items in groups.values():
            keeper = next((i for i in items if i.selected), None)
            if keeper is None:
                continue
            targets.append((keeper, [i.name for i in items]))
        if not targets:
            self.report({"WARNING"}, "Tick a preferred resolution for at least one group "
                        "(or use Select High/Low Resolution)")
            return {"CANCELLED"}

        from .safety import auto_backup

        backup = auto_backup(context)
        removed = 0
        for keeper_item, member_names in targets:
            keeper = bpy.data.images.get(keeper_item.name)
            if keeper is None:
                continue
            for victim_name in dd.victims_for_keeper(member_names, keeper_item.name):
                victim = bpy.data.images.get(victim_name)
                if victim is None or victim is keeper or victim.library is not None:
                    continue
                victim.user_remap(keeper)
                if victim.users == 0:
                    bpy.data.images.remove(victim)
                    removed += 1

        try:
            context.view_layer.update()
        except Exception:
            pass

        _rescan_res_variants(context)
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Removed {removed} excess variant(s) across "
                    f"{len(targets)} group(s).{tail} Save to persist.")
        return {"FINISHED"}


class FILELINK_OT_scan_content_dups(ModalProgressMixin, bpy.types.Operator):
    """F6 Layer 3 — the deep content-overlap scan (the real bloat-killer). Hashes
    EVERY local image and collapses exact-content duplicates regardless of name —
    the same texture imported under different names across many CC4 folders becomes
    one. Modal with progress + pause/ESC because hashing the whole set is slow.
    Populates the same Duplicate list (keeper dropdown + Merge Selected apply)."""

    bl_idname = "filelink.scan_content_dups"
    bl_label = "Find Content Duplicates"
    bl_options = {"REGISTER"}

    def run_steps(self, context):
        from . import report_store

        # 2026-07-14 (user report: a local 1K + linked 2K identical-content pair
        # was invisible because this used to filter to `img.library is None`
        # before hashing) — now scans EVERY image, local or linked; only the
        # MERGE step (below) still only ever removes a local one, same rule F3
        # material dedup already applies to its own linked victims.
        candidates = [img for img in bpy.data.images
                      if img.source in _FILE_SOURCES or img.packed_file is not None]
        total = len(candidates)
        infos: list[ImgInfo] = []
        for idx, img in enumerate(candidates):
            infos.append(ImgInfo(name=img.name, fingerprint=_fingerprint(img),
                                 users=img.users, linked=img.library is not None))
            # Reserve the last 5% for planning/report; hashing is the long part.
            yield (0.95 * (idx + 1) / max(total, 1),
                   f"Hashing textures by content… {idx + 1}/{total}")

        plans = imagededup.plan_content_merges(infos)
        conflicts = imagededup.find_image_conflicts(infos)
        _fill_families(context, plans, conflicts)
        blend_name = os.path.basename(bpy.data.filepath) or "current file"
        report_store.stash_report(
            context, imagededup.build_dedup_report(plans, conflicts, blend_name), "f6dup",
            set_active=False)
        wm = context.window_manager
        wm.filelink_dup_scanned = True
        rebuild_dup_tex_picker_rows(wm)
        yield (1.0, "Done")
        n = imagededup.removable_count(plans)
        if plans:
            self.report({"INFO"}, f"{len(plans)} content-duplicate group(s); ~{n} removable "
                        "across the file. Pick keepers, then Merge Selected.")
        else:
            self.report({"INFO"}, "✓ No content-identical duplicate textures found")


class FILELINK_OT_dup_material_keeper(bpy.types.Operator):
    """Master keeper control for a whole MATERIAL group: set the keeper of every
    duplicate family under it at once by a policy (so you don't touch each family's
    dropdown individually). Per-family dropdowns still override afterward."""

    bl_idname = "filelink.dup_material_keeper"
    bl_label = "Set Keepers for Material"
    bl_options = {"REGISTER", "INTERNAL"}

    material: bpy.props.StringProperty()  # type: ignore[valid-type]
    policy: bpy.props.EnumProperty(
        name="Keep",
        items=[("RECOMMENDED", "Recommended",
                "Keep each family's recommended datablock (un-suffixed base, else most-used)"),
               ("BASE", "Un-suffixed base",
                "Keep the name without a .NNN suffix where present")],
        default="RECOMMENDED")  # type: ignore[valid-type]

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "policy")

    def execute(self, context):
        from ..core.datablock_graph import strip_dup_suffix

        coll = context.window_manager.filelink_dup_families
        n = 0
        for row in coll:
            if effective_material(row) != self.material:
                continue
            members = [m for m in row.members.split("\n") if m]
            if not members:
                continue
            if self.policy == "BASE":
                base = strip_dup_suffix(members[0])
                pick = next((m for m in members if m == base), members[0])
            else:
                pick = members[0]  # canonical (populate puts it first)
            try:
                row.keeper = pick
                n += 1
            except (TypeError, ValueError):
                pass  # dynamic-enum value rejected -> leave this family as is
        if context.area:
            context.area.tag_redraw()
        self.report({"INFO"}, f"Set {n} keeper(s) for {self.material}.")
        return {"FINISHED"}


