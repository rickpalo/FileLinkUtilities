"""Logging for File & Link Utilities.

A single "filelink" logger always echoes INFO to the console (preserving the
per-finding output operators emit). When the user ticks Utilities > Enable Debug
Log, a DEBUG-level file handler is attached that writes ``debugLog.txt`` next to
the current .blend (or to Blender's temp dir for an unsaved file), so a remote
user can send it back for diagnosis.
"""

from __future__ import annotations

import logging
import os

_LOGGER_NAME = "filelink"
_file_handler: logging.Handler | None = None


def get_logger() -> logging.Logger:
    log = logging.getLogger(_LOGGER_NAME)
    if not getattr(log, "_ad_inited", False):
        log.setLevel(logging.DEBUG)
        stream = logging.StreamHandler()
        stream.setLevel(logging.INFO)
        stream.setFormatter(logging.Formatter("[FileLink] %(message)s"))
        log.addHandler(stream)
        log.propagate = False
        log._ad_inited = True  # type: ignore[attr-defined]
    return log


def debug_log_path(blend_path: str) -> str:
    """Where the debug log goes: next to the .blend, else Blender's temp dir."""
    if blend_path:
        return os.path.join(os.path.dirname(blend_path), "FileLinkDebugLog.txt")
    import bpy  # only needed for the unsaved-file fallback

    return os.path.join(bpy.app.tempdir, "FileLinkDebugLog.txt")


def set_debug_enabled(enabled: bool, blend_path: str = "") -> str | None:
    """Attach/detach the file handler. Returns the log path when enabling."""
    global _file_handler
    log = get_logger()
    if enabled and _file_handler is None:
        path = debug_log_path(blend_path)
        # mode="w": each enable / file-open starts a FRESH log, so the file holds one
        # reproduction (easy to read and send) rather than an ever-growing append.
        handler = logging.FileHandler(path, mode="w", encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        log.addHandler(handler)
        _file_handler = handler
        log.info("Debug log enabled → %s", path)
        return path
    if not enabled and _file_handler is not None:
        log.info("Debug log disabled")
        log.removeHandler(_file_handler)
        _file_handler.close()
        _file_handler = None
    return None
