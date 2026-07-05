"""Shared safety helpers for mutating operators (F2/F3/F4 Apply paths).

The locked safety model: report-first, then explicit Apply, with a timestamped
.blend backup taken *before* any mutation. ``auto_backup`` writes that copy
without disturbing the current working file (save_as_mainfile copy=True).
"""

from __future__ import annotations

import datetime
import os

import bpy

from ..prefs import get_prefs


def auto_backup(context) -> str | None:
    """Save a timestamped backup copy if enabled in prefs.

    Returns the backup path, or None if backups are disabled or no destination
    can be determined (e.g. an unsaved file with no configured backup dir).
    """
    prefs = get_prefs(context)
    if prefs is None or not prefs.auto_backup:
        return None

    src = bpy.data.filepath
    if prefs.backup_dir:
        dirpath = bpy.path.abspath(prefs.backup_dir)
    elif src:
        dirpath = os.path.dirname(src)
    else:
        return None  # unsaved, nowhere safe to put it

    os.makedirs(dirpath, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = os.path.splitext(os.path.basename(src))[0] if src else "untitled"
    dst = os.path.join(dirpath, f"{stem}_filelink_{stamp}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=dst, copy=True)
    return dst
