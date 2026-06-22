"""F6 Layer 1 — relink missing image textures (report-first + per-link + backup).

The image analogue of ``ops/relink.py``'s broken-library flow: "Find Missing
Textures" lists each LOCAL image whose file is missing, with an auto-found target
(de-dup of doubled path segments / folder search) where possible; the user ticks
the ones to fix (or picks a file manually) and relinks only those. This is what
unblocks the magenta from missing textures.

Only LOCAL images are handled here — images owned by a linked library belong to
that library file and must be fixed at the source (top-down).
"""

from __future__ import annotations

import os

import bpy

from ..core import imagepaths, imagefamily
from ..core.imagepaths import ImgDesc

# Image datablock sources whose filepath points at an external file we can relink.
_FILE_SOURCES = {"FILE", "SEQUENCE", "MOVIE", "TILED"}


def _image_material_map() -> dict[str, str]:
    """``{image name: a material that uses it}`` — a representative material per
    image (the first found), for the B1 material-fallback grouping. Walks material
    node trees for any node carrying an ``image`` (TEX_IMAGE & friends)."""
    out: dict[str, str] = {}
    for mat in bpy.data.materials:
        if not mat.use_nodes or mat.node_tree is None:
            continue
        for node in mat.node_tree.nodes:
            img = getattr(node, "image", None)
            if img is not None and img.name not in out:
                out[img.name] = mat.name
    return out


def _gather_images() -> list[ImgDesc]:
    out: list[ImgDesc] = []
    for img in bpy.data.images:
        if img.library is not None:
            continue  # linked image -> fix in its source file, not here
        if img.source not in _FILE_SOURCES or img.packed_file is not None:
            continue  # generated/viewer or packed -> no external file to relink
        stored = img.filepath
        if not stored:
            continue
        resolved = os.path.normpath(bpy.path.abspath(stored))
        out.append(ImgDesc(name=img.name, stored=stored, resolved=resolved,
                           exists=os.path.isfile(resolved)))
    return out


def _populate_broken_images(context) -> tuple[int, int]:
    """Refill ``assetdoctor_broken_imgs`` from the current file's missing LOCAL
    images, each paired with a found target where possible. Returns
    (missing count, auto-found count)."""
    wm = context.window_manager
    coll = wm.assetdoctor_broken_imgs
    coll.clear()
    imgs = _gather_images()
    missing = [i for i in imgs if not i.exists]
    blend_dir = os.path.dirname(bpy.data.filepath)
    # Search the folders of resolvable images (+ this file's folder) by basename.
    search_dirs = [blend_dir] + [os.path.dirname(i.resolved) for i in imgs if i.exists]
    targets = imagepaths.find_relink_targets(missing, search_dirs)
    mat_map = _image_material_map()  # for B1 material-fallback grouping
    for img in missing:
        item = coll.add()
        item.name = img.name
        item.stored = img.stored
        cand = targets.get(img.name, "")
        item.target = cand
        item.has_candidate = bool(cand)
        item.selected = bool(cand)  # pre-tick only confident auto-matches
        item.group = os.path.dirname((img.resolved or img.stored).replace("\\", "/"))
        item.material = mat_map.get(img.name, "")
    wm.assetdoctor_broken_imgs_index = 0
    return len(missing), len(targets)


class ASSETDOCTOR_OT_scan_broken_textures(bpy.types.Operator):
    bl_idname = "assetdoctor.scan_broken_textures"
    bl_label = "Find Missing Textures"
    bl_description = ("List this file's missing image textures so you can relink them "
                      "individually (auto-fixing doubled path segments and finding files "
                      "by name where possible)")
    bl_options = {"REGISTER"}

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the file first")
            return {"CANCELLED"}
        missing, found = _populate_broken_images(context)
        if context.area:
            context.area.tag_redraw()
        if not missing:
            self.report({"INFO"}, "No missing image textures")
        else:
            self.report({"INFO"}, f"{missing} missing texture(s); {found} with an auto-found match")
        return {"FINISHED"}


class ASSETDOCTOR_OT_find_missing_files_folder(bpy.types.Operator):
    """Follow-up A — wrap Blender's NATIVE recursive missing-file search and report
    the result (which Blender omits). Our Layer-1 search is single-level; this is
    recursive by filename. Affects ALL external files (images, libraries…), not just
    the textures listed above; backs up first."""

    bl_idname = "assetdoctor.find_missing_files_folder"
    bl_label = "Find Missing Files (folder)…"
    bl_options = {"REGISTER"}

    # A directory picker: the file browser fills `directory` with the chosen folder.
    directory: bpy.props.StringProperty(subtype="DIR_PATH")  # type: ignore[valid-type]
    filter_folder: bpy.props.BoolProperty(default=True, options={"HIDDEN"})  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        return ("Search a folder RECURSIVELY (by filename) for every missing external "
                "file and relink what it finds — Blender's native search — then report "
                "which were found and which are still missing. Affects ALL external "
                "files (images, libraries…), not just the list above. Backs up first")

    def invoke(self, context, event):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the file first")
            return {"CANCELLED"}
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        if not self.directory or not os.path.isdir(self.directory):
            self.report({"ERROR"}, "Choose a folder to search")
            return {"CANCELLED"}

        before_missing = [i for i in _gather_images() if not i.exists]
        if not before_missing:
            self.report({"INFO"}, "No missing image textures to find")
            return {"CANCELLED"}

        from .safety import auto_backup

        backup = auto_backup(context)
        try:
            # Native, recursive-by-filename; relocates found files silently.
            bpy.ops.file.find_missing_files(directory=self.directory)
        except RuntimeError as exc:
            self.report({"ERROR"}, f"Native search failed: {exc}")
            return {"CANCELLED"}

        after_by_name = {i.name: i for i in _gather_images()}
        result = imagepaths.diff_found(before_missing, after_by_name)

        from . import report_store

        blend_name = os.path.basename(bpy.data.filepath) or "current file"
        report = imagepaths.build_find_missing_report(result, blend_name)
        report_store.stash_report(context, report, "f6tex")

        _populate_broken_images(context)  # found ones drop off; still-missing remain
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Found {len(result.found)}, "
                    f"{len(result.still_missing)} still missing. Save to persist.{tail}")
        return {"FINISHED"}


class ASSETDOCTOR_OT_point_group_at_folder(bpy.types.Operator):
    """Follow-up B1 — point a whole GROUP of missing textures at one folder and
    resolve every member by filename within it (directory-level relink). Groups are
    by original directory; the material fallback (``by='MATERIAL'``) lets the user
    fix all of one material's textures when the original folder is gone. Fills the
    rows' targets (unique basename match only) — the user then Relinks Selected."""

    bl_idname = "assetdoctor.point_group_at_folder"
    bl_label = "Point Group at Folder"
    bl_options = {"REGISTER", "INTERNAL"}

    group_key: bpy.props.StringProperty()  # type: ignore[valid-type]
    by: bpy.props.StringProperty(default="DIR")  # type: ignore[valid-type]  # DIR | MATERIAL
    recursive: bpy.props.BoolProperty(
        name="Search subfolders",
        description="Also search inside subfolders of the chosen folder",
        default=True)  # type: ignore[valid-type]
    directory: bpy.props.StringProperty(subtype="DIR_PATH")  # type: ignore[valid-type]
    filter_folder: bpy.props.BoolProperty(default=True, options={"HIDDEN"})  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        return ("Choose a folder; every missing texture in this group is matched by "
                "filename within it (and subfolders) and its target set. Then Relink "
                "Selected to apply")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        if not self.directory or not os.path.isdir(self.directory):
            self.report({"ERROR"}, "Choose a folder to search")
            return {"CANCELLED"}

        coll = context.window_manager.assetdoctor_broken_imgs
        members = [item for item in coll
                   if (item.group if self.by == "DIR" else item.material) == self.group_key]
        if not members:
            self.report({"WARNING"}, "No textures in this group")
            return {"CANCELLED"}

        descs = [ImgDesc(name=item.name, stored=item.stored,
                         resolved=os.path.normpath(bpy.path.abspath(item.stored)), exists=False)
                 for item in members]
        found = imagefamily.resolve_group_in_dir(descs, self.directory, recursive=self.recursive)
        for item in members:
            target = found.get(item.name)
            if target:
                item.target = target
                item.has_candidate = True
                item.selected = True
        if context.area:
            context.area.tag_redraw()
        self.report({"INFO"}, f"Matched {len(found)} of {len(members)} in this group. "
                    "Tick/adjust, then Relink Selected.")
        return {"FINISHED"}


class ASSETDOCTOR_OT_relink_pick_texture(bpy.types.Operator):
    bl_idname = "assetdoctor.relink_pick_texture"
    bl_label = "Pick Texture File"
    bl_description = "Choose the image file to relink this missing texture to"
    bl_options = {"REGISTER", "INTERNAL"}

    index: bpy.props.IntProperty()  # type: ignore[valid-type]
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]
    filter_image: bpy.props.BoolProperty(default=True, options={"HIDDEN"})  # type: ignore[valid-type]
    filter_glob: bpy.props.StringProperty(
        default="*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.exr;*.tga;*.bmp;*.hdr;*.tx;*.psd",
        options={"HIDDEN"})  # type: ignore[valid-type]

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        coll = context.window_manager.assetdoctor_broken_imgs
        if 0 <= self.index < len(coll):
            item = coll[self.index]
            target = os.path.normpath(bpy.path.abspath(self.filepath))
            item.target = target
            item.has_candidate = os.path.isfile(target)
            item.selected = True
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ASSETDOCTOR_OT_relink_textures_selected(bpy.types.Operator):
    bl_idname = "assetdoctor.relink_textures_selected"
    bl_label = "Relink Selected Textures"
    bl_options = {"REGISTER"}

    @classmethod
    def description(cls, context, properties):
        return ("Repoint each ticked missing texture to its target file (and reload it). "
                "Takes a backup first")

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the file first")
            return {"CANCELLED"}

        coll = context.window_manager.assetdoctor_broken_imgs
        chosen = [item for item in coll if item.selected and item.target]
        if not chosen:
            self.report({"WARNING"}, "Tick at least one texture that has a target file")
            return {"CANCELLED"}

        targets = {item.name: os.path.normpath(bpy.path.abspath(item.target)) for item in chosen}
        absent = [name for name, t in targets.items() if not os.path.isfile(t)]
        if absent:
            self.report({"ERROR"}, f"Target file not found for: {', '.join(absent)}")
            return {"CANCELLED"}

        from .safety import auto_backup

        backup = auto_backup(context)
        blend_dir = os.path.dirname(bpy.data.filepath)
        relinked = 0
        for item in chosen:
            img = bpy.data.images.get(item.name)
            if img is None or img.library is not None:
                continue
            img.filepath = imagepaths.relink_stored_path(targets[item.name], blend_dir)
            try:
                img.reload()
                relinked += 1
            except Exception as exc:
                self.report({"WARNING"}, f"Relinked {item.name} but reload failed: {exc}")

        _populate_broken_images(context)
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Relinked {relinked} texture(s). Save to persist.{tail}")
        return {"FINISHED"}
