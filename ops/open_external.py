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
            # Detached: a fresh independent Blender, not a child that dies with
            # this one and not something we wait on.
            subprocess.Popen([blender, path], close_fds=True)
        except Exception as exc:  # noqa: BLE001 — surface any launch failure to the user
            self.report({"ERROR"}, f"Couldn't launch Blender: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Opening {os.path.basename(path)} in a new Blender…")
        return {"FINISHED"}
