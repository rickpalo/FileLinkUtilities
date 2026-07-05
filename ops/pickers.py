"""Phase 2a (2026-06-24 code-review plan) — shared file-browser boilerplate for
File & Link Utilities' many "pick a file/folder to fix this" operators (Pick Source
.blend, Pick Library File, Relink Pick Texture, Examine Library's per-row pick,
etc.). ``invoke()`` is 100% identical across every one of them (open the
native file browser, run modally); only the after-pick validation in
``execute()`` still varies per operator (different targets, different
collections to update), so this only extracts what's genuinely shared —
deliberately not trying to unify ``execute()`` into one shape.
"""

from __future__ import annotations

import os

import bpy


class FilePickerMixin:
    """Mix into any ``bpy.types.Operator`` that needs ONE file/folder pick
    before doing its real work in ``execute()``. The subclass still declares
    its own ``filepath``/``directory`` + ``filter_glob``/``filter_folder``
    properties — Blender's file-browser UI needs concrete properties on the
    operator class itself — this only removes the repeated ``invoke()`` body."""

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


def resolve_existing_file(filepath: str) -> str:
    """Normalize a file-browser-picked path to an absolute path. Returns ``""``
    if it doesn't resolve to a real file on disk — callers check truthiness,
    the same "not found" handling repeated across several Pick-a-file
    operators in this addon."""
    path = os.path.normpath(bpy.path.abspath(filepath))
    return path if os.path.isfile(path) else ""


__all__ = ["FilePickerMixin", "resolve_existing_file"]
