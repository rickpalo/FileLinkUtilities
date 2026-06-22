"""F6 unifying model — group missing images so a whole GROUP can be targeted at
one folder (Follow-up B1), and (later) so name-families can be consolidated
(Layer 2). bpy-free: the operator extracts :class:`~core.imagepaths.ImgDesc` (plus
a per-image material map) from ``bpy.data`` and feeds it here.

Step 2 (this module today) owns the **grouping + folder-resolve** logic for B1.
Name-family detection + content classification (the ``.NNN`` / ``_2k`` families
that Layer 2 merges) lands in step 3 alongside the dims/hash extraction it needs;
it is intentionally NOT here yet so B1 ships on a small, fully-tested surface.
"""

from __future__ import annotations

import os
from typing import Callable

from .imagepaths import ImgDesc, find_relink_targets


def _norm_dir(path: str) -> str:
    """The directory part of a stored/resolved path, forward-slash normalised."""
    return os.path.dirname(path.replace("\\", "/"))


def group_by_directory(missing: list[ImgDesc]) -> dict[str, list[ImgDesc]]:
    """``{original directory: [members]}`` for missing images, keyed by the folder
    their path points at. Files that lived together likely still do, so the user
    can point the whole group at one folder. The default B1 grouping."""
    groups: dict[str, list[ImgDesc]] = {}
    for img in missing:
        groups.setdefault(_norm_dir(img.resolved or img.stored), []).append(img)
    return groups


def group_by_key(missing: list[ImgDesc],
                 key_of: Callable[[ImgDesc], str]) -> dict[str, list[ImgDesc]]:
    """Group by an arbitrary key (used for the material-fallback grouping, where
    the operator supplies image→material). Members whose key is empty land under
    ``""`` so the caller can hide them (e.g. images no material uses directly)."""
    groups: dict[str, list[ImgDesc]] = {}
    for img in missing:
        groups.setdefault(key_of(img), []).append(img)
    return groups


def resolve_group_in_dir(members: list[ImgDesc], directory: str,
                         recursive: bool = False) -> dict[str, str]:
    """``{image name: found path}`` for members whose basename UNIQUELY exists in
    ``directory``. Reuses the Layer-1 folder search (unique-match only, never a
    non-existent path). ``recursive`` walks subfolders too; an ambiguous basename
    (present in more than one place) is skipped, not guessed."""
    if recursive:
        dirs = [root for root, _sub, _files in os.walk(directory)]
    else:
        dirs = [directory]
    return find_relink_targets(members, dirs)


__all__ = ["group_by_directory", "group_by_key", "resolve_group_in_dir"]
