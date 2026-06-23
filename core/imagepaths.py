"""F6 Layer 1 — relink missing image textures (bpy-free core).

The image analogue of :mod:`core.relink` (library paths). Given the current
file's images, find an on-disk target for each MISSING one by trying, in
confidence order:

  1. **de-duplicating accidentally repeated path segments** — the real
     ``E:\\BlenderSync\\BlenderSync\\SynologyDrive\\…`` case (a doubled folder),
  2. **user prefix find/replace remaps** (e.g. ``D:\\`` → ``E:\\`` cross-drive),
  3. **folder search by basename** in the supplied directories (unique match only),

and only ever returns a path that actually EXISTS, so a bad guess can't be
applied. Turning a found absolute target into a stored ``//``-relative path
reuses :func:`core.relink.relink_stored_path`.

Layers 2 (name-family consolidation) and 3 (content-overlap dedup) build on top
of this and live in separate modules; this file is just the relinker.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .relink import relink_stored_path  # reused: same //-relative logic
from .report import Finding, Report


@dataclass
class ImgDesc:
    """A current-file image datablock, as the operator extracts it from bpy.data."""

    name: str
    stored: str  # image.filepath as stored ("//…" or absolute)
    resolved: str  # absolute, resolved path
    exists: bool


def dedup_path(path: str) -> str:
    """Collapse **consecutive duplicate** path components (case-insensitive).

    ``E:\\BlenderSync\\BlenderSync\\SynologyDrive\\a.png`` →
    ``E:/BlenderSync/SynologyDrive/a.png``. Non-consecutive repeats (``a/b/a``)
    are kept — only an immediately-doubled segment is treated as the error.
    Returns a forward-slash path; callers normalise before hitting disk."""
    parts = path.replace("\\", "/").split("/")
    out: list[str] = []
    for p in parts:
        if out and p and out[-1].lower() == p.lower():
            continue  # drop the immediate duplicate
        out.append(p)
    return "/".join(out)


def apply_prefix_remap(path: str, old: str, new: str) -> str:
    """Case-insensitive prefix find/replace (e.g. ``D:\\`` → ``E:\\``). Returns the
    path unchanged when ``old`` is not a prefix. Forward-slash normalised."""
    np = path.replace("\\", "/")
    no = old.replace("\\", "/")
    if no and np.lower().startswith(no.lower()):
        return new.replace("\\", "/") + np[len(no):]
    return np


def _candidate_paths(img: ImgDesc, remaps: list[tuple[str, str]]):
    """Yield candidate absolute paths for a missing image, best-confidence first:
    the de-duped path, then each prefix remap (and its de-duped form)."""
    seen: set[str] = set()

    def _emit(p: str):
        n = os.path.normpath(p)
        key = n.replace("\\", "/").lower()
        if key not in seen:
            seen.add(key)
            return n
        return None

    base = img.resolved
    for cand in (dedup_path(base), *(apply_prefix_remap(base, o, n) for o, n in remaps),
                 *(dedup_path(apply_prefix_remap(base, o, n)) for o, n in remaps)):
        out = _emit(cand)
        if out is not None:
            yield out


def _scan_dir_into(index: dict[str, list[str]], seen: set[str], d: str) -> None:
    """Add ``d``'s files to a lowercased-basename → paths ``index`` (skipping dirs
    already in ``seen``). Factored out of :func:`_index_dirs` so a modal operator can
    build the same index one folder at a time and report progress between folders."""
    key = d.replace("\\", "/").rstrip("/").lower()
    if key in seen:
        return
    seen.add(key)
    try:
        for entry in os.scandir(d):
            if entry.is_file():
                index.setdefault(entry.name.lower(), []).append(
                    os.path.normpath(entry.path))
    except OSError:
        return


def _index_dirs(search_dirs: list[str]) -> dict[str, list[str]]:
    """Map lowercased basename → list of absolute paths, across the dirs (deduped)."""
    index: dict[str, list[str]] = {}
    seen: set[str] = set()
    for d in search_dirs:
        _scan_dir_into(index, seen, d)
    return index


def iter_walk_dirs(root: str, recursive: bool = True):
    """Yield directories under ``root`` (``root`` itself first), one per step. When
    ``recursive`` descend subfolders via ``os.walk``; otherwise yield only ``root``.
    A thin generator so a modal operator can build the file index folder-by-folder
    and stay responsive / cancellable over a large tree."""
    if recursive:
        for cur, _sub, _files in os.walk(root):
            yield cur
    else:
        yield root


def find_image_target(
    img: ImgDesc, search_dirs: list[str], remaps: list[tuple[str, str]] | None = None,
    _index: dict[str, list[str]] | None = None,
) -> str | None:
    """An existing on-disk path for a MISSING image, or None. Tries de-dup +
    prefix remaps first (high confidence), then a unique basename match in
    ``search_dirs``. Never returns a non-existent path."""
    remaps = remaps or []
    for cand in _candidate_paths(img, remaps):
        if os.path.isfile(cand):
            return cand
    index = _index if _index is not None else _index_dirs(search_dirs)
    base = os.path.basename((img.resolved or img.stored).replace("\\", "/")).lower()
    matches = index.get(base, [])
    if len(matches) == 1:
        return matches[0]
    return None


def find_relink_targets(
    missing: list[ImgDesc], search_dirs: list[str],
    remaps: list[tuple[str, str]] | None = None,
) -> dict[str, str]:
    """``{image name: found absolute path}`` for every missing image we can place.
    Builds the basename index once and reuses it across all images."""
    index = _index_dirs(search_dirs)
    out: dict[str, str] = {}
    for img in missing:
        target = find_image_target(img, search_dirs, remaps, _index=index)
        if target is not None:
            out[img.name] = target
    return out


@dataclass
class FindMissingResult:
    """Outcome of a native ``find_missing_files`` run, computed by diffing each
    previously-missing image's resolved-exists before vs after."""

    found: list[tuple[str, str]]          # (image name, resolved path now on disk)
    still_missing: list[tuple[str, str]]  # (image name, stored path)


def diff_found(before_missing: list[ImgDesc],
               after_by_name: dict[str, ImgDesc]) -> FindMissingResult:
    """Classify each image that was MISSING before as found (now exists) or still
    missing, by looking up its post-run state. Blender's ``find_missing_files``
    relocates silently — this is the report it omits."""
    found: list[tuple[str, str]] = []
    still: list[tuple[str, str]] = []
    for img in before_missing:
        after = after_by_name.get(img.name)
        if after is not None and after.exists:
            found.append((img.name, after.resolved))
        else:
            still.append((img.name, img.stored))
    return FindMissingResult(found=found, still_missing=still)


def build_find_missing_report(result: FindMissingResult,
                              blend_name: str = "current file") -> Report:
    """Report a native-search run: the textures it FOUND (info) first, then the
    ones STILL missing (error). Category headers carry the counts."""
    report = Report(title=f"Find missing files: {blend_name}", feature="f6tex")
    for name, path in result.found:
        report.add(Finding(category="found_texture",
                           message=f"{name}:  found  →  {path}",
                           severity="info", items=[name, path]))
    for name, stored in result.still_missing:
        report.add(Finding(category="unresolved_texture",
                           message=f"{name}:  {stored}  (still missing)",
                           severity="error", items=[name, stored]))
    if not result.found and not result.still_missing:
        report.add(Finding(category="clean",
                           message="✓ No missing image textures",
                           severity="info"))
    return report


def build_image_report(targets: dict[str, str], unresolved: list[ImgDesc],
                       blend_name: str = "current file") -> Report:
    """Report the missing-texture relink plan: found targets (info) first, then
    the ones still unresolved (error). Category headers carry the counts."""
    report = Report(title=f"Missing textures: {blend_name}", feature="f6tex")
    for name, target in targets.items():
        report.add(Finding(category="relink_texture",
                           message=f"{name}:  missing  →  {target}",
                           severity="info", items=[name, target],
                           data={"name": name, "new": target}))
    for img in unresolved:
        report.add(Finding(category="unresolved_texture",
                           message=f"{img.name}:  {img.stored}  (no candidate found)",
                           severity="error", items=[img.name, img.stored]))
    if not targets and not unresolved:
        report.add(Finding(category="clean",
                           message="✓ All image textures resolve — nothing missing",
                           severity="info"))
    return report


__all__ = ["ImgDesc", "dedup_path", "apply_prefix_remap", "find_image_target",
           "find_relink_targets", "build_image_report", "relink_stored_path",
           "FindMissingResult", "diff_found", "build_find_missing_report"]
