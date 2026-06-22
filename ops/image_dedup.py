"""F6 Layer 2 (step 3) — lossless ``.NNN`` image-datablock merge (report + apply).

Mirrors F3 material dedup: find content-identical ``.NNN`` duplicate images, keep
one canonical, ``user_remap`` the rest onto it, and remove the now-unused local
copies. Content identity is VERIFIED by a fingerprint (dimensions + a file/packed
hash) before any merge — name similarity alone never triggers a merge. Only local
images are touched; linked images belong to their source library.
"""

from __future__ import annotations

import hashlib
import os

import bpy

from ..core import imagededup
from ..core.imagededup import ImgInfo
from ..core.datablock_graph import duplicate_families

# Session cache: (path, size, mtime) -> file hash, so repeated scans don't re-read.
_HASH_CACHE: dict[tuple[str, int, int], str] = {}


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


def _family_member_infos() -> list[ImgInfo]:
    """:class:`ImgInfo` for the members of every local ``.NNN`` name-family — only
    those need fingerprinting (the rest can't be duplicates), so a big file isn't
    fully hashed for Layer 2."""
    local = [img for img in bpy.data.images if img.library is None]
    fams = duplicate_families([img.name for img in local])
    family_names = {n for members in fams.values() for n in members}
    return [ImgInfo(name=img.name, fingerprint=_fingerprint(img), users=img.users)
            for img in local if img.name in family_names]


class ASSETDOCTOR_OT_dedup_textures(bpy.types.Operator):
    bl_idname = "assetdoctor.dedup_textures"
    bl_label = "Dedup Textures"
    bl_options = {"REGISTER"}

    apply: bpy.props.BoolProperty(default=False)  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        if properties.apply:
            return ("Merge content-identical .NNN duplicate image datablocks: keep one, "
                    "remap its users, remove the rest. Verifies content (dimensions + "
                    "hash) before merging. Takes a backup first")
        return ("Find content-identical .NNN duplicate image datablocks — report only "
                "(verifies content before proposing any merge)")

    def execute(self, context):
        from . import report_store

        blend_name = os.path.basename(bpy.data.filepath) or "current file"
        plans, conflicts = imagededup.plan_dup_merges(_family_member_infos())
        report = imagededup.build_dedup_report(plans, conflicts, blend_name)

        if not self.apply:
            report_store.stash_report(context, report, "f6dup")
            n = imagededup.removable_count(plans)
            if context.area:
                context.area.tag_redraw()
            self.report({"INFO"}, f"{len(plans)} merge group(s); ~{n} removable. See report.")
            return {"FINISHED"}

        if not plans:
            report_store.stash_report(context, report, "f6dup")
            self.report({"INFO"}, "No duplicate textures to merge")
            return {"CANCELLED"}

        from .safety import auto_backup

        backup = auto_backup(context)
        removed = 0
        for plan in plans:
            canonical = bpy.data.images.get(plan.canonical)
            if canonical is None:
                continue
            for name in plan.redundant:
                victim = bpy.data.images.get(name)
                if victim is None or victim == canonical or victim.library is not None:
                    continue
                victim.user_remap(canonical)
                if victim.users == 0:
                    bpy.data.images.remove(victim)
                    removed += 1

        # Re-report the post-merge state.
        post_plans, post_conf = imagededup.plan_dup_merges(_family_member_infos())
        report_store.stash_report(
            context, imagededup.build_dedup_report(post_plans, post_conf, blend_name), "f6dup")
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Merged and removed {removed} duplicate texture(s). "
                    f"Save to persist.{tail}")
        return {"FINISHED"}
