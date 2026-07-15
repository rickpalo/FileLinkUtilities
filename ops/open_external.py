"""Open another .blend in a SEPARATE new Blender instance (user request
2026-07-15). Wherever the addon points at a problem that must be fixed in a
different file — a library to fix at its source, an indirect duplicate, ... —
the file name is drawn as a clickable "link" (``ui.panels._draw_file_link``)
that launches this operator. It starts a fresh, independent Blender on that
file (``bpy.app.binary_path``, the running executable) so the user can go fix
it without disturbing the current session.
"""

from __future__ import annotations

import os
import subprocess

import bpy

# Fire-and-forget child Blenders we launch but never wait on. We keep each
# Popen referenced here on purpose: if it were discarded, CPython finalizes it
# later (whenever GC runs) and — seeing the child still alive — emits a
# ResourceWarning. That warning can fire mid-frame while a modal operator is
# pumping its run_steps generator (e.g. Analyze All), and emitting a warning
# with a suspended generator frame on the stack crashed Blender with an access
# violation in the CPython frame walker (v0.3.13 crash, EXCEPTION_ACCESS_VIOLATION
# reading 0xA8). Holding the reference defers finalization to interpreter
# shutdown, when no modal is running. Each launch first reaps already-exited
# children via poll() (which clears their returncode so they, too, never warn).
_LAUNCHED: list[subprocess.Popen] = []


class FILELINK_OT_open_blend_external(bpy.types.Operator):
    bl_idname = "filelink.open_blend_external"
    bl_label = "Open in New Blender"
    bl_description = ("Open this .blend in a separate new Blender instance, to fix it there "
                      "without disturbing the current session")
    bl_options = {"INTERNAL"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]

    def execute(self, context):
        path = bpy.path.abspath(self.filepath) if self.filepath else ""
        path = os.path.normpath(path) if path else ""
        if not path or not os.path.isfile(path):
            self.report({"ERROR"}, f"File not found: {self.filepath or '(none)'}")
            return {"CANCELLED"}
        blender = bpy.app.binary_path
        if not blender or not os.path.isfile(blender):
            self.report({"ERROR"}, "Can't locate the Blender executable to launch")
            return {"CANCELLED"}
        try:
            # Reap any previously launched children that have since exited, so
            # the list stays bounded and their Popen objects finalize cleanly
            # (poll() sets returncode → no ResourceWarning on GC).
            _LAUNCHED[:] = [p for p in _LAUNCHED if p.poll() is None]
            # Detached: a fresh independent Blender, not a child that dies with
            # this one and not something we wait on. Keep the handle in _LAUNCHED
            # (see module note) so its finalizer can't warn mid-modal and crash.
            _LAUNCHED.append(subprocess.Popen([blender, path], close_fds=True))
        except Exception as exc:  # noqa: BLE001 — surface any launch failure to the user
            self.report({"ERROR"}, f"Couldn't launch Blender: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Opening {os.path.basename(path)} in a new Blender…")
        return {"FINISHED"}
