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
    """Fill ``assetdoctor_dup_families`` + the summary counts from a content-merge
    plan. Each row carries its members (for the keeper dropdown) and a
    representative material."""
    from .image_relink import _image_material_map

    wm = context.window_manager
    coll = wm.assetdoctor_dup_families
    coll.clear()
    mat_map = _image_material_map()
    for p in plans:
        members = [p.canonical, *p.redundant]  # canonical first => default keeper
        row = coll.add()
        row.name = p.base
        row.members = "\n".join(members)
        # keeper left at its default (first enum item == canonical); the user may
        # repoint it. Setting a dynamic-enum value explicitly is fragile, so don't.
        row.selected = True
        row.material = next((mat_map[m] for m in members if m in mat_map), "")
        row.removable = len(p.redundant)
    wm.assetdoctor_dup_index = 0
    wm.assetdoctor_dup_removable = imagededup.removable_count(plans)
    wm.assetdoctor_dup_conflicts = len(conflicts)
    wm.assetdoctor_dup_conflicts_text = "\n".join(f"{c.base} — {c.reason}" for c in conflicts)


class ASSETDOCTOR_OT_merge_dup_selected(bpy.types.Operator):
    bl_idname = "assetdoctor.merge_dup_selected"
    bl_label = "Merge Selected Duplicates"
    bl_description = ("Merge each ticked family into its chosen keeper (remap users, "
                      "remove the rest). Takes a backup first")
    bl_options = {"REGISTER"}

    def execute(self, context):
        from .safety import auto_backup

        wm = context.window_manager
        chosen = [row for row in wm.assetdoctor_dup_families if row.selected]
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
        wm.assetdoctor_dup_families.clear()
        wm.assetdoctor_dup_removable = 0
        wm.assetdoctor_dup_conflicts = 0
        wm.assetdoctor_dup_conflicts_text = ""
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Merged and removed {removed} duplicate texture(s). "
                    f"Save to persist.{tail} Re-run Find Content Dups to see any remaining.")
        return {"FINISHED"}


class ASSETDOCTOR_OT_scan_res_variants(bpy.types.Operator):
    """F6 Layer 2 — report textures that exist at multiple resolutions (1k/2k/…).
    Footprint analysis only: standardizing to one resolution is LOSSY (changes the
    render), so this never mutates — it stashes a report for the user to decide."""

    bl_idname = "assetdoctor.scan_res_variants"
    bl_label = "Find Resolution Variants"
    bl_description = ("Report textures present at multiple resolutions (1k/2k/4k) so you "
                      "can decide whether to standardize down. Standardizing is lossy — "
                      "this only reports, never changes anything")
    bl_options = {"REGISTER"}

    def execute(self, context):
        from . import report_store
        from ..core import imageres

        names = [img.name for img in bpy.data.images if img.library is None]
        variants = imageres.plan_res_variants(names)
        blend_name = os.path.basename(bpy.data.filepath) or "current file"
        report_store.stash_report(context, imageres.build_res_report(variants, blend_name), "f6res")
        if context.area:
            context.area.tag_redraw()
        if variants:
            self.report({"INFO"}, f"{len(variants)} texture(s) at multiple resolutions. "
                        "See the Resolution Variants report (standardizing is lossy).")
        else:
            self.report({"INFO"}, "✓ No multi-resolution texture variants found")
        return {"FINISHED"}


class ASSETDOCTOR_OT_scan_content_dups(ModalProgressMixin, bpy.types.Operator):
    """F6 Layer 3 — the deep content-overlap scan (the real bloat-killer). Hashes
    EVERY local image and collapses exact-content duplicates regardless of name —
    the same texture imported under different names across many CC4 folders becomes
    one. Modal with progress + pause/ESC because hashing the whole set is slow.
    Populates the same Duplicate list (keeper dropdown + Merge Selected apply)."""

    bl_idname = "assetdoctor.scan_content_dups"
    bl_label = "Find Content Duplicates"
    bl_options = {"REGISTER"}

    def run_steps(self, context):
        from . import report_store

        local = [img for img in bpy.data.images
                 if img.library is None
                 and (img.source in _FILE_SOURCES or img.packed_file is not None)]
        total = len(local)
        infos: list[ImgInfo] = []
        for idx, img in enumerate(local):
            infos.append(ImgInfo(name=img.name, fingerprint=_fingerprint(img),
                                 users=img.users))
            # Reserve the last 5% for planning/report; hashing is the long part.
            yield (0.95 * (idx + 1) / max(total, 1),
                   f"Hashing textures by content… {idx + 1}/{total}")

        plans = imagededup.plan_content_merges(infos)
        _fill_families(context, plans, [])
        blend_name = os.path.basename(bpy.data.filepath) or "current file"
        report_store.stash_report(
            context, imagededup.build_dedup_report(plans, [], blend_name), "f6dup",
            set_active=False)
        wm = context.window_manager
        wm.assetdoctor_dup_scanned = True
        yield (1.0, "Done")
        n = imagededup.removable_count(plans)
        if plans:
            self.report({"INFO"}, f"{len(plans)} content-duplicate group(s); ~{n} removable "
                        "across the file. Pick keepers, then Merge Selected.")
        else:
            self.report({"INFO"}, "✓ No content-identical duplicate textures found")


class ASSETDOCTOR_OT_dup_material_keeper(bpy.types.Operator):
    """Master keeper control for a whole MATERIAL group: set the keeper of every
    duplicate family under it at once by a policy (so you don't touch each family's
    dropdown individually). Per-family dropdowns still override afterward."""

    bl_idname = "assetdoctor.dup_material_keeper"
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

        coll = context.window_manager.assetdoctor_dup_families
        n = 0
        for row in coll:
            eff = (row.material_override.name if row.material_override
                   else (row.material or "(no material)"))
            if eff != self.material:
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


class ASSETDOCTOR_OT_dup_category_toggle(bpy.types.Operator):
    """Expand/collapse one material group in the Duplicate Materials/Textures list."""

    bl_idname = "assetdoctor.dup_category_toggle"
    bl_label = "Expand/Collapse Material"
    bl_options = {"INTERNAL"}

    key: bpy.props.StringProperty()  # type: ignore[valid-type]

    def execute(self, context):
        wm = context.window_manager
        keys = set(filter(None, wm.assetdoctor_dup_expanded.split("\n")))
        keys.discard(self.key) if self.key in keys else keys.add(self.key)
        wm.assetdoctor_dup_expanded = "\n".join(sorted(keys))
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}
