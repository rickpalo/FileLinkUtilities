"""Addon preferences for AssetDoctor.

Holds user-tunable settings that the operators read: scan root, backup
directory, the resolution-token regex used for near-duplicate material
matching, and feature toggles. Defaults are chosen to be safe (report-first,
backups on).
"""

import bpy

# Shared by Material/Geometry dedup (docs/TODO.md #21, 2026-06-27): which side
# of a local+linked duplicate cluster to keep as canonical. Materials already
# mix local/linked in one cluster; Geometry now does too (previously local-
# only) -- "Prefer Linked" repoints local users onto the shared library
# datablock instead, reducing local footprint. A linked datablock is never
# removed either way -- only local IDs can be.
_KEEP_PREF_ITEMS = [
    ("LOCAL", "Prefer Local", "Keep the LOCAL copy as canonical (today's default)"),
    ("LINKED", "Prefer Linked", "Keep the LINKED copy as canonical instead, repointing "
     "local users onto it"),
]


class AssetDoctorPreferences(bpy.types.AddonPreferences):
    # Must match the extension id / package name.
    bl_idname = __package__

    backup_dir: bpy.props.StringProperty(
        name="Backup Folder",
        description="Where to write timestamped .blend backups before any mutating op. "
        "Leave empty to back up next to the current file",
        subtype="DIR_PATH",
        default="",
    )  # type: ignore[valid-type]

    auto_backup: bpy.props.BoolProperty(
        name="Auto-backup before mutating",
        description="Save a timestamped .blend copy before make-local / remap / purge",
        default=True,
    )  # type: ignore[valid-type]

    # Tokens stripped from image/material names when deciding multi-res near-duplicates.
    # Pipe-separated regex fragments; see core.fingerprint.strip_resolution_tokens.
    resolution_token_regex: bpy.props.StringProperty(
        name="Resolution Tokens",
        description="Regex of resolution/dup suffixes to ignore when matching textures "
        r"(e.g. _1k, _2k, -2048, Blender's .001 dup suffix)",
        default=r"[._-]?\d{1,2}k|[._-]\d{3,4}|\.\d{3}$",
    )  # type: ignore[valid-type]

    material_whitelist: bpy.props.StringProperty(
        name="Material Whitelist",
        description="Names/globs to always KEEP as the canonical material when duplicates "
        "are found (comma/newline separated; * wildcards allowed)",
        default="",
    )  # type: ignore[valid-type]

    material_blacklist: bpy.props.StringProperty(
        name="Material Blacklist",
        description="Names/globs to always REPLACE when an identical duplicate exists",
        default="",
    )  # type: ignore[valid-type]

    material_keep_preference: bpy.props.EnumProperty(
        name="Materials: Keep",
        description="When a duplicate spans both a local and a linked material, which one "
        "to keep as canonical (the whitelist/blacklist above still take precedence)",
        items=_KEEP_PREF_ITEMS, default="LOCAL",
    )  # type: ignore[valid-type]

    geometry_keep_preference: bpy.props.EnumProperty(
        name="Geometry: Keep",
        description="When a duplicate spans both a local and a linked mesh, which one to "
        "keep as canonical",
        items=_KEEP_PREF_ITEMS, default="LOCAL",
    )  # type: ignore[valid-type]

    # Batch E feasibility prototype — see core.idle / ops.idle_scan. Off by
    # default: it only proves the OS-idle poll works from inside Blender, it
    # does NOT trigger any scan yet.
    idle_scan_enabled: bpy.props.BoolProperty(
        name="Idle-scan prototype (experimental)",
        description="Poll Windows for how long the keyboard/mouse have been idle and show it "
        "below — a feasibility check only, no scan is triggered yet",
        default=False,
    )  # type: ignore[valid-type]

    idle_scan_threshold: bpy.props.IntProperty(
        name="Idle Threshold (seconds)",
        description="How long the user must be idle before the prototype flags it",
        default=120,
        min=10,
    )  # type: ignore[valid-type]

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "auto_backup")
        col.prop(self, "backup_dir")
        col.separator()
        col.prop(self, "resolution_token_regex")
        col.label(text="Material dedup (F3):")
        col.prop(self, "material_whitelist")
        col.prop(self, "material_blacklist")
        col.prop(self, "material_keep_preference")
        col.separator()
        col.label(text="Geometry dedup (F5):")
        col.prop(self, "geometry_keep_preference")
        col.separator()
        col.label(text="Idle-scan (experimental prototype, Windows only):")
        col.prop(self, "idle_scan_enabled")
        sub = col.column()
        sub.enabled = self.idle_scan_enabled
        sub.prop(self, "idle_scan_threshold")


def get_prefs(context=None):
    """Return the AssetDoctorPreferences instance, or None if unavailable."""
    context = context or bpy.context
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon else None
