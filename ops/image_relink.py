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

from ..core import imagematch, imagepaths, imagefamily
from ..core.imagepaths import ImgDesc
from .pickers import FilePickerMixin, resolve_existing_file
from .progress import ModalProgressMixin

# Image datablock sources whose filepath points at an external file we can relink.
_FILE_SOURCES = {"FILE", "SEQUENCE", "MOVIE", "TILED"}


def _walk_image_nodes(node_tree, seen):
    """Yield every image referenced anywhere in ``node_tree``, recursing into node
    groups (so a texture buried in a ShaderNodeGroup is still attributed to its
    material — the old top-level-only walk left those as '(no material)')."""
    if node_tree is None or node_tree in seen:
        return
    seen.add(node_tree)
    for node in node_tree.nodes:
        img = getattr(node, "image", None)
        if img is not None:
            yield img
        sub = getattr(node, "node_tree", None)  # ShaderNodeGroup -> nested tree
        if sub is not None:
            yield from _walk_image_nodes(sub, seen)


def _image_material_map() -> dict[str, str]:
    """``{image name: the representative material that uses it}``. Walks each
    material's node tree AND its nested node groups. When several materials use the
    same image, the one whose NAME best matches the image's (token affinity) wins —
    so a ``…_lightBlue_…`` texture groups under a lightBlue material, not whichever
    happened to be first (the FabricWool mis-grouping)."""
    image_to_mats: dict[str, list[str]] = {}
    for mat in bpy.data.materials:
        if not mat.use_nodes or mat.node_tree is None:
            continue
        for img in _walk_image_nodes(mat.node_tree, set()):
            mats = image_to_mats.setdefault(img.name, [])
            if mat.name not in mats:
                mats.append(mat.name)
    out: dict[str, str] = {}
    for img_name, mats in image_to_mats.items():
        # max() keeps the first on ties (mats is in discovery order).
        out[img_name] = (mats[0] if len(mats) == 1
                         else max(mats, key=lambda m: imagematch.name_affinity(img_name, m)))
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


def _gather_linked_missing_images() -> list[tuple[str, str, str]]:
    """Every LINKED image whose stored file doesn't resolve: ``[(name, library
    label, material)]``. These can't be relinked from here — the source library
    owns that file path, so the real fix is over there (top-down) — this is a
    READ-ONLY visibility list, never wired to any relink action.

    User report 2026-06-24: a render-time Dry-Run Render found 144 missing
    images while "List Missing Textures" only ever found 9 — because
    ``_gather_images`` deliberately skips every linked Image (see its
    docstring). The render evaluates EVERY image regardless of who owns it, so
    the static scan was silently undercounting by a lot; this surfaces the gap
    without pretending it can be fixed in the current file.

    A linked image's relative path is stored relative to ITS OWN library file,
    not this one — ``bpy.path.abspath(path, library=img.library)`` resolves
    against the right base directory (plain ``bpy.path.abspath`` would resolve
    against the CURRENT file and silently mis-flag a perfectly valid relative
    path as missing)."""
    mat_map = _image_material_map()
    out: list[tuple[str, str, str]] = []
    for img in bpy.data.images:
        if img.library is None:
            continue
        if img.source not in _FILE_SOURCES or img.packed_file is not None:
            continue
        stored = img.filepath
        if not stored:
            continue
        resolved = os.path.normpath(bpy.path.abspath(stored, library=img.library))
        if os.path.isfile(resolved):
            continue
        lib_label = img.library.filepath or img.library.name
        out.append((img.name, lib_label, mat_map.get(img.name, "")))
    return out


def _populate_broken_images(context) -> tuple[int, int]:
    """Refill ``assetdoctor_broken_imgs`` from the current file's missing LOCAL
    images, each paired with a found target where possible, AND the read-only
    ``assetdoctor_linked_missing_imgs`` companion list (linked images, fix-at-
    source — see ``_gather_linked_missing_images``). Returns
    (missing count, auto-found count) for the LOCAL list only — unchanged
    contract for existing callers."""
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

    linked_coll = wm.assetdoctor_linked_missing_imgs
    linked_coll.clear()
    for name, lib_label, material in _gather_linked_missing_images():
        item = linked_coll.add()
        item.name = name
        item.library = lib_label
        item.material = material

    return len(missing), len(targets)


# Sentinel for a texture with no attributed material — matches the one the
# panel used before virtualization. NOT "\x00": Blender's StringProperty
# round-trips through a C string, which truncates at the first NUL byte, so
# a lone "\x00" silently vanished from assetdoctor_tex_expanded on write.
_UNGROUPED = "\x02"


def rebuild_missing_tex_picker_rows(wm) -> None:
    """Rebuild ``wm.assetdoctor_missingtex_picker_rows`` (Group 12 Phase 3)
    from the current ``assetdoctor_broken_imgs`` + expand state.

    Called after every op that changes GROUP MEMBERSHIP (scan / relink
    selected) or a row's ``target`` (pick / accept / folder-search) — the
    group header's "N of M matched" count would otherwise go stale between
    scans, since (unlike the old hand-drawn loop) it's no longer recomputed
    on every redraw. A bare checkbox tick needs no rebuild (drawn live by
    ``ASSETDOCTOR_UL_missing_tex_picker`` straight off the real row)."""
    from ..core import picker as picker_mod
    from .report_store import get_expanded

    coll = wm.assetdoctor_broken_imgs
    if not len(coll):
        wm.assetdoctor_missingtex_picker_rows.clear()
        return

    expanded = get_expanded(wm, "assetdoctor_tex_expanded")
    groups: dict[str, list[int]] = {}
    order: list[str] = []
    for i, item in enumerate(coll):
        key = item.material or _UNGROUPED
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(i)

    specs = []
    for key in sorted(order):
        indices = groups[key]
        total = len(indices)
        matched = sum(1 for i in indices if coll[i].target)
        disp = "(no material)" if key == _UNGROUPED else key
        label = f"{disp}  ({matched} of {total} matched)" if matched else f"{disp}  ({total})"
        specs.append(picker_mod.GroupSpec(
            key=key,
            label=label,
            icon="CHECKMARK" if matched and matched == total else "MATERIAL",
            members=[picker_mod.MemberRef(ref_index=i) for i in indices],
            has_action=key != _UNGROUPED,
        ))
    picker_rows = picker_mod.flatten_group_member_rows(
        specs, expanded, ref_prop="assetdoctor_broken_imgs")

    picker_coll = wm.assetdoctor_missingtex_picker_rows
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


class ASSETDOCTOR_OT_scan_broken_textures(bpy.types.Operator):
    bl_idname = "assetdoctor.scan_broken_textures"
    bl_label = "List Missing Textures"
    bl_description = ("List this file's missing image textures, grouped by material "
                      "(or folder), so you can relink them — point a whole group at a "
                      "folder, search a folder recursively, or pick a file per texture")
    bl_options = {"REGISTER"}

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the file first")
            return {"CANCELLED"}
        missing, found = _populate_broken_images(context)
        wm = context.window_manager
        wm.assetdoctor_tex_scanned = True
        wm.assetdoctor_tex_initial_missing = missing  # "found" later = initial − still-missing
        rebuild_missing_tex_picker_rows(wm)
        if context.area:
            context.area.tag_redraw()
        linked = len(wm.assetdoctor_linked_missing_imgs)
        linked_tail = (f"; {linked} more are linked — fix at the source library" if linked else "")
        if not missing:
            msg = "No missing image textures" if not linked else "No LOCAL missing textures"
            self.report({"INFO"}, msg + linked_tail)
        else:
            self.report({"INFO"},
                       f"{missing} missing texture(s); {found} with an auto-found match{linked_tail}")
        return {"FINISHED"}


class ASSETDOCTOR_OT_search_textures_folder(FilePickerMixin, bpy.types.Operator):
    """Recursively search ONE folder for ALL the listed missing textures by filename
    and STAGE the matches (set each found texture's target + tick it) without
    changing anything yet — the user reviews, then Relink Selected applies. Unlike
    Blender's native find-missing-files this touches only the textures listed here
    (libraries have their own Broken Library Links section) and never writes until applied."""

    bl_idname = "assetdoctor.search_textures_folder"
    bl_label = "Search a Folder (recursive)"
    bl_options = {"REGISTER"}

    directory: bpy.props.StringProperty(subtype="DIR_PATH")  # type: ignore[valid-type]
    filter_folder: bpy.props.BoolProperty(default=True, options={"HIDDEN"})  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        return ("Pick a folder; every missing texture above is searched for by filename "
                "in it and its subfolders, and matches are staged (target set + ticked). "
                "Nothing is written until you Relink Selected")

    def execute(self, context):
        if not self.directory or not os.path.isdir(self.directory):
            self.report({"ERROR"}, "Choose a folder to search")
            return {"CANCELLED"}
        if not len(context.window_manager.assetdoctor_broken_imgs):
            self.report({"INFO"}, "No missing textures to search for")
            return {"CANCELLED"}
        # Hand off to the modal worker so a large tree doesn't freeze the UI.
        bpy.ops.assetdoctor.relink_folder_search(
            "INVOKE_DEFAULT", directory=self.directory, mode="EXACT_ALL", recursive=True)
        return {"FINISHED"}


def _wanted_basename(item) -> str:
    """The filename a missing-texture row wants on disk (basename of its stored path)."""
    return os.path.basename((item.stored or item.name).replace("\\", "/"))


def _diagnostics_tail(ambiguous: dict | None, skipped_dirs: list | None) -> str:
    """A short suffix for the folder-search status message surfacing the two ways a
    broad (e.g. drive-level) search can silently miss a file that a narrower one
    finds: a same-filename collision elsewhere in the tree (skipped, never guessed
    at) or a subfolder ``os.walk`` couldn't list at all (permission / Windows'
    MAX_PATH) — both otherwise look identical to "genuinely not there"."""
    bits = []
    if ambiguous:
        bits.append(f"{len(ambiguous)} skipped (same filename found in 2+ places — pick "
                    "manually for those)")
    if skipped_dirs:
        bits.append(f"{len(skipped_dirs)} folder(s) could not be scanned "
                    "(permission, or a path too long for Windows)")
    return "  ⚠ " + "; ".join(bits) + "." if bits else ""


def _stage_proposals(todo, proposals) -> int:
    """Copy ``{wanted basename: (path, Match)}`` proposals onto the still-unplaced
    rows (the shared tail of every 'suggest from a corpus' op). Returns the count
    staged. Rows with no proposal have theirs cleared."""
    staged = 0
    for item in todo:
        res = proposals.get(_wanted_basename(item))
        if res is None:
            item.proposal = ""
            continue
        path, m = res
        item.proposal = path
        item.proposal_confidence = m.confidence
        item.proposal_res_mismatch = m.res_mismatch
        staged += 1
    return staged


class ASSETDOCTOR_OT_relink_folder_search(ModalProgressMixin, bpy.types.Operator):
    """Modal worker behind the folder-search relink actions (Search a folder / Point
    group at folder / Suggest matches). It walks the chosen tree under the shared
    progress bar — cancellable, so a big import tree no longer freezes the UI — and
    stages matches onto the missing-texture rows. The thin picker ops own the file
    browser and launch this via INVOKE_DEFAULT: a fileselect modal and a progress
    modal can't share one operator, hence the two-op split."""

    bl_idname = "assetdoctor.relink_folder_search"
    bl_label = "Searching folder for textures"
    bl_options = {"REGISTER", "INTERNAL"}

    directory: bpy.props.StringProperty()  # type: ignore[valid-type]
    # EXACT_ALL (search a folder for every row) | EXACT_GROUP (one material/dir group)
    # | FUZZY (name-similarity proposals for still-unplaced rows).
    mode: bpy.props.StringProperty(default="EXACT_ALL")  # type: ignore[valid-type]
    group_key: bpy.props.StringProperty()  # type: ignore[valid-type]
    by: bpy.props.StringProperty(default="DIR")  # type: ignore[valid-type]  # DIR | MATERIAL
    recursive: bpy.props.BoolProperty(default=True)  # type: ignore[valid-type]

    def _members(self, coll):
        if self.mode == "EXACT_GROUP":
            return [it for it in coll
                    if (it.group if self.by == "DIR" else it.material) == self.group_key]
        if self.mode == "FUZZY":
            return [it for it in coll if not it.target]  # only still-unplaced rows
        return list(coll)  # EXACT_ALL

    def cancel_message(self) -> str:
        return "Folder search cancelled — nothing changed"

    def run_steps(self, context):
        coll = context.window_manager.assetdoctor_broken_imgs
        members = self._members(coll)
        if not members:
            msg = ("Every missing texture already has a match" if self.mode == "FUZZY"
                   else "No textures in this group" if self.mode == "EXACT_GROUP"
                   else "No missing textures to search for")
            self.report({"INFO"}, msg)
            return
        if self.mode == "FUZZY":
            yield from self._run_fuzzy(context, members)
        else:
            yield from self._run_exact(context, members)

    def _run_exact(self, context, members):
        descs = [ImgDesc(name=it.name, stored=it.stored,
                         resolved=os.path.normpath(bpy.path.abspath(it.stored)), exists=False)
                 for it in members]
        ambiguous: dict[str, list[str]] = {}
        skipped_dirs: list[str] = []
        gen = imagefamily.iter_resolve_group_in_dir(
            descs, self.directory, self.recursive,
            ambiguous=ambiguous, skipped_dirs=skipped_dirs)
        found: dict[str, str] = {}
        try:
            while True:
                walked = next(gen)
                yield (min(0.9, walked / (walked + 20.0)),
                       f"Searching {self.directory}… {walked} folder(s)")
        except StopIteration as stop:
            found = stop.value or {}

        yield (0.97, f"Staging {len(found)} match(es)…")
        for it in members:
            target = found.get(it.name)
            if target:
                it.target = target
                it.has_candidate = True
                it.selected = True
                it.ambiguous_count = 0
            else:
                it.ambiguous_count = len(ambiguous.get(_wanted_basename(it), []))
        rebuild_missing_tex_picker_rows(context.window_manager)
        if context.area:
            context.area.tag_redraw()
        yield (1.0, "Done")

        total = len(members)
        tail = _diagnostics_tail(ambiguous, skipped_dirs)
        if found and self.mode == "EXACT_GROUP":
            self.report({"INFO"}, f"Matched {len(found)} of {total} in this group — "
                        f"targets set in the list above. Tick/adjust, then Relink Selected.{tail}")
        elif found:
            self.report({"INFO"}, f"Staged {len(found)} of {total} texture(s) from "
                        f"{self.directory}. Review, then Relink Selected.{tail}")
        elif self.mode == "EXACT_GROUP":
            scope = "and subfolders" if self.recursive else "(this folder only)"
            self.report({"WARNING"}, f"No matching filenames found in {self.directory} {scope}. "
                        f"Nothing changed — try another folder or pick files individually.{tail}")
        else:
            self.report({"WARNING"}, f"No matching filenames found under {self.directory}. "
                        f"Nothing changed.{tail}")

    def _run_fuzzy(self, context, members):
        index: dict[str, list[str]] = {}
        seen: set[str] = set()
        skipped_dirs: list[str] = []
        walked = 0
        for d in imagepaths.iter_walk_dirs(self.directory, True, skipped=skipped_dirs):
            imagepaths._scan_dir_into(index, seen, d)
            walked += 1
            yield (min(0.9, walked / (walked + 20.0)),
                   f"Scanning {self.directory}… {walked} folder(s)")
        if not index:
            self.report({"WARNING"}, f"No files found under {self.directory}."
                        f"{_diagnostics_tail(None, skipped_dirs)}")
            return

        name_to_path = {os.path.basename(paths[0]): paths[0] for paths in index.values()}
        cand_names = list(name_to_path)
        wanted = sorted({_wanted_basename(it) for it in members})
        yield (0.95, f"Matching {len(wanted)} name(s) by similarity…")
        proposals = imagematch.propose_matches(wanted, cand_names, min_confidence="low")

        staged = 0
        for it in members:
            m = proposals.get(_wanted_basename(it))
            if m is None:
                it.proposal = ""
                continue
            it.proposal = name_to_path.get(m.candidate, "")
            it.proposal_confidence = m.confidence
            it.proposal_res_mismatch = m.res_mismatch
            if it.proposal:
                staged += 1
        if context.area:
            context.area.tag_redraw()
        yield (1.0, "Done")
        tail = _diagnostics_tail(None, skipped_dirs)
        if staged:
            self.report({"INFO"}, f"Found {staged} possible match(es) by name in "
                        f"{self.directory}. Review the Possible Matches list and Accept.{tail}")
        else:
            self.report({"WARNING"}, f"No similar filenames found under {self.directory}.{tail}")


class ASSETDOCTOR_OT_suggest_fuzzy_matches(FilePickerMixin, bpy.types.Operator):
    """F6 step 4 — fuzzy FALLBACK for textures exact search couldn't place. Pick a
    folder; for every missing texture that still has NO target, score the folder's
    files with the rename matcher (``core.imagematch``: stem identity + PBR-channel
    synonyms + resolution, with numbered-variant conflicts disqualified) and STAGE
    the best candidate as a *proposal* — shown in a separate "Possible Matches"
    list for the user to Accept. Nothing is applied here; Accept moves a proposal
    into the main Missing Textures list, then Relink Selected writes it."""

    bl_idname = "assetdoctor.suggest_fuzzy_matches"
    bl_label = "Suggest Matches (fuzzy)"
    bl_options = {"REGISTER"}

    directory: bpy.props.StringProperty(subtype="DIR_PATH")  # type: ignore[valid-type]
    filter_folder: bpy.props.BoolProperty(default=True, options={"HIDDEN"})  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        return ("Pick a folder; each missing texture with no exact match is matched "
                "by NAME SIMILARITY (renamed channels, e.g. _ao -> _AO) against the "
                "files in it and its subfolders. Best guesses are staged as Possible "
                "Matches to review and Accept — nothing is written here")

    def execute(self, context):
        if not self.directory or not os.path.isdir(self.directory):
            self.report({"ERROR"}, "Choose a folder to search")
            return {"CANCELLED"}
        coll = context.window_manager.assetdoctor_broken_imgs
        if not any(not item.target for item in coll):  # nothing still-unplaced
            self.report({"INFO"}, "Every missing texture already has a match")
            return {"CANCELLED"}
        # Hand off to the modal worker so a large tree doesn't freeze the UI.
        bpy.ops.assetdoctor.relink_folder_search(
            "INVOKE_DEFAULT", directory=self.directory, mode="FUZZY", recursive=True)
        return {"FINISHED"}


class ASSETDOCTOR_OT_suggest_from_material(bpy.types.Operator):
    """B4 — propose substitutes for the missing textures from ANOTHER material's
    existing (on-disk) textures (the eyedropper datablock-picker). The picked source
    material's image files become the candidate corpus, matched by name against every
    missing texture that still has no target, and staged as Possible Matches to
    Accept. All-local (reads `bpy.data`, no folder walk) so it's instant; nothing is
    written here."""

    bl_idname = "assetdoctor.suggest_from_material"
    bl_label = "Suggest from Material"
    bl_description = ("Use the picked source material's existing textures as substitute "
                      "candidates for the missing ones (matched by name). Staged as "
                      "Possible Matches to review — nothing is written")
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        wm = context.window_manager
        mat = wm.assetdoctor_tex_source_material
        if mat is None:
            self.report({"ERROR"}, "Pick a source material first (the eyedropper)")
            return {"CANCELLED"}
        coll = wm.assetdoctor_broken_imgs
        todo = [item for item in coll if not item.target]  # still-unplaced rows only
        if not todo:
            self.report({"INFO"}, "Every missing texture already has a match")
            return {"CANCELLED"}

        # Harvest the source material's images (recursing node groups), keeping only
        # local, file-backed images whose file is actually on disk.
        cand_paths: list[str] = []
        if mat.use_nodes and mat.node_tree is not None:
            for img in _walk_image_nodes(mat.node_tree, set()):
                if img.library is not None or img.source not in _FILE_SOURCES or not img.filepath:
                    continue
                p = os.path.normpath(bpy.path.abspath(img.filepath))
                if os.path.isfile(p):
                    cand_paths.append(p)
        if not cand_paths:
            self.report({"WARNING"}, f"'{mat.name}' has no on-disk textures to offer")
            return {"CANCELLED"}

        wanted = sorted({_wanted_basename(item) for item in todo})
        proposals = imagematch.propose_from_paths(wanted, cand_paths, min_confidence="low")
        staged = _stage_proposals(todo, proposals)
        if context.area:
            context.area.tag_redraw()
        if staged:
            self.report({"INFO"}, f"Staged {staged} possible match(es) from '{mat.name}'. "
                        "Review the Possible Matches list and Accept.")
        else:
            self.report({"WARNING"}, f"No similar texture names found in '{mat.name}'.")
        return {"FINISHED"}


class ASSETDOCTOR_OT_suggest_from_blend(FilePickerMixin, bpy.types.Operator):
    """B4 — propose substitutes for the missing textures from the images referenced by
    ANOTHER .blend file. Pick a .blend; its texture FILE PATHS (harvested offline via
    BAT, wherever they point) become the candidate corpus, matched by name against
    every still-unplaced missing texture and staged as Possible Matches. Nothing is
    written here. (Images are file-backed, so this just finds the right FILE — no
    Blender linking, which is only needed for missing DATA-BLOCKS.)"""

    bl_idname = "assetdoctor.suggest_from_blend"
    bl_label = "Suggest from Another .blend"
    bl_options = {"REGISTER", "INTERNAL"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]
    filter_blender: bpy.props.BoolProperty(default=True, options={"HIDDEN"})  # type: ignore[valid-type]
    filter_glob: bpy.props.StringProperty(default="*.blend", options={"HIDDEN"})  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        return ("Pick another .blend; the image files IT references become substitute "
                "candidates for the missing textures (matched by name). Staged as "
                "Possible Matches to review — nothing is written")

    def execute(self, context):
        from ..core import blendscan

        src = resolve_existing_file(self.filepath) if self.filepath else ""
        if not src:
            self.report({"ERROR"}, "Choose a .blend file")
            return {"CANCELLED"}
        coll = context.window_manager.assetdoctor_broken_imgs
        todo = [item for item in coll if not item.target]  # still-unplaced rows only
        if not todo:
            self.report({"INFO"}, "Every missing texture already has a match")
            return {"CANCELLED"}
        if not blendscan.bat_available():
            self.report({"ERROR"}, "Blender Asset Tracer unavailable; reinstall the extension")
            return {"CANCELLED"}

        try:
            cand_paths = blendscan.harvest_image_paths(src)
        except Exception as exc:  # unreadable/corrupt .blend
            self.report({"ERROR"}, f"Could not read {os.path.basename(src)}: {exc}")
            return {"CANCELLED"}
        cand_paths = [p for p in cand_paths if os.path.isfile(p)]  # on-disk targets only
        if not cand_paths:
            self.report({"WARNING"}, f"{os.path.basename(src)} references no on-disk textures")
            return {"CANCELLED"}

        wanted = sorted({_wanted_basename(item) for item in todo})
        proposals = imagematch.propose_from_paths(wanted, cand_paths, min_confidence="low")
        staged = _stage_proposals(todo, proposals)
        if context.area:
            context.area.tag_redraw()
        if staged:
            self.report({"INFO"}, f"Staged {staged} possible match(es) from "
                        f"{os.path.basename(src)}. Review the Possible Matches list and Accept.")
        else:
            self.report({"WARNING"}, f"No similar texture names in {os.path.basename(src)}.")
        return {"FINISHED"}


class ASSETDOCTOR_OT_accept_match(bpy.types.Operator):
    """Accept one staged fuzzy proposal: copy it into the row's target (so it joins
    the main Missing Textures list, ticked) and clear the proposal."""

    bl_idname = "assetdoctor.accept_match"
    bl_label = "Accept Match"
    bl_description = "Use this proposed file as the relink target for this texture"
    bl_options = {"REGISTER", "INTERNAL"}

    index: bpy.props.IntProperty()  # type: ignore[valid-type]

    def execute(self, context):
        coll = context.window_manager.assetdoctor_broken_imgs
        if not (0 <= self.index < len(coll)):
            return {"CANCELLED"}
        item = coll[self.index]
        if not item.proposal:
            return {"CANCELLED"}
        item.target = item.proposal
        item.has_candidate = os.path.isfile(item.proposal)
        item.selected = True
        item.proposal = ""
        rebuild_missing_tex_picker_rows(context.window_manager)
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ASSETDOCTOR_OT_accept_material_matches(bpy.types.Operator):
    """Accept every staged proposal under one MATERIAL group at once (the textures
    rolled up beneath that material header in the Possible Matches list)."""

    bl_idname = "assetdoctor.accept_material_matches"
    bl_label = "Accept Material's Matches"
    bl_description = ("Accept all proposed files for this material's textures — they "
                      "move into the Missing Textures list above, ticked")
    bl_options = {"REGISTER", "INTERNAL"}

    material: bpy.props.StringProperty()  # type: ignore[valid-type]

    def execute(self, context):
        coll = context.window_manager.assetdoctor_broken_imgs
        accepted = 0
        for item in coll:
            if not item.proposal or item.target:
                continue
            if (item.material or "(no material)") != self.material:
                continue
            item.target = item.proposal
            item.has_candidate = os.path.isfile(item.proposal)
            item.selected = True
            item.proposal = ""
            accepted += 1
        rebuild_missing_tex_picker_rows(context.window_manager)
        if context.area:
            context.area.tag_redraw()
        self.report({"INFO"}, f"Accepted {accepted} match(es) for {self.material}.")
        return {"FINISHED"}


class ASSETDOCTOR_OT_accept_all_matches(bpy.types.Operator):
    """Accept every staged fuzzy proposal at once, moving them all into the main
    Missing Textures list (ticked) ready for Relink Selected."""

    bl_idname = "assetdoctor.accept_all_matches"
    bl_label = "Accept All Matches"
    bl_options = {"REGISTER"}

    @classmethod
    def description(cls, context, properties):
        return ("Use every proposed file as its texture's relink target — they move "
                "into the Missing Textures list above, ticked. Then Relink Selected")

    def execute(self, context):
        coll = context.window_manager.assetdoctor_broken_imgs
        accepted = 0
        for item in coll:
            if not item.proposal:
                continue
            item.target = item.proposal
            item.has_candidate = os.path.isfile(item.proposal)
            item.selected = True
            item.proposal = ""
            accepted += 1
        rebuild_missing_tex_picker_rows(context.window_manager)
        if context.area:
            context.area.tag_redraw()
        if accepted:
            self.report({"INFO"}, f"Accepted {accepted} match(es). Review the ticks above, "
                        "then Relink Selected.")
        else:
            self.report({"INFO"}, "No proposed matches to accept")
        return {"FINISHED"}


class ASSETDOCTOR_OT_point_group_at_folder(FilePickerMixin, bpy.types.Operator):
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
        # Hand off to the modal worker so a large tree doesn't freeze the UI.
        bpy.ops.assetdoctor.relink_folder_search(
            "INVOKE_DEFAULT", directory=self.directory, mode="EXACT_GROUP",
            group_key=self.group_key, by=self.by, recursive=self.recursive)
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
        # If this texture already has a match, open the browser AT that match's
        # folder (with the file selected) instead of wherever the UI was last —
        # so "the folder icon opens the folder for THIS match" (user, 2026-06-22).
        coll = context.window_manager.assetdoctor_broken_imgs
        if 0 <= self.index < len(coll) and coll[self.index].target:
            self.filepath = bpy.path.abspath(coll[self.index].target)
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
            rebuild_missing_tex_picker_rows(context.window_manager)
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

        # Defensive: settle the dependency graph after bulk filepath/reload changes
        # before the next viewport draw (the relink/merge crash was the EEVEE draw
        # acquiring a stale image buffer). Precaution, not a verified fix.
        try:
            context.view_layer.update()
        except Exception:
            pass

        _populate_broken_images(context)
        rebuild_missing_tex_picker_rows(context.window_manager)
        if context.area:
            context.area.tag_redraw()
        tail = f" Backup: {backup}" if backup else " (no backup written)"
        self.report({"INFO"}, f"Relinked {relinked} texture(s). Save to persist.{tail}")
        return {"FINISHED"}
