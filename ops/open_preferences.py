"""Open Blender's Preferences with the AssetDoctor add-on expanded.

Surfaced from the panel's Utilities section so the white/black lists, backup
folder and other prefs are one click away instead of a buried menu dive.
"""

import bpy

# The add-on's module id as Blender knows it (root package; matches
# AssetDoctorPreferences.bl_idname). This file lives in ``<root>.ops``.
_ADDON_MODULE = __package__.rpartition(".")[0]


class ASSETDOCTOR_OT_open_preferences(bpy.types.Operator):
    bl_idname = "assetdoctor.open_preferences"
    bl_label = "AssetDoctor Preferences"
    bl_description = ("Open the add-on preferences (material white/black lists, backup folder, "
                      "resolution tokens) with AssetDoctor expanded")

    def execute(self, context):
        try:
            bpy.ops.preferences.addon_show(module=_ADDON_MODULE)
        except (RuntimeError, TypeError):
            # Fallback: open the Preferences window on the Add-ons section.
            bpy.ops.screen.userpref_show()
            context.preferences.active_section = "ADDONS"
        return {"FINISHED"}
