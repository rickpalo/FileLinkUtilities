"""AssetDoctor — Blender 5+ asset dependency & dedup addon.

Top-level registration. Keep this file thin: it only wires up the operator,
panel and preferences classes plus a couple of Scene properties. All real logic
lives in ``core`` (bpy-free, unit-testable) and ``ops`` (thin bpy operators that
call into ``core``).

bpy-dependent submodules are imported *lazily inside register()* so that simply
importing this package (e.g. during pytest collection, outside Blender) never
pulls in ``bpy``. See docs/ARCHITECTURE.md.
"""

# Populated by register(); used by unregister() to tear down in reverse order.
_REGISTERED: list = []
_load_post_handler = None  # the persistent load_post callback, for unregister


def _debug_update(self, context):
    """Scene 'Enable Debug Log' toggle callback."""
    import bpy

    from .log import set_debug_enabled

    set_debug_enabled(self.assetdoctor_debug_log, bpy.data.filepath)


def _debug_log_on_load(_dummy):
    """On opening a file with the debug toggle on, start a FRESH log for it.

    The Scene-prop ``update`` callback doesn't fire on load, so without this an
    enabled toggle wouldn't reactivate after opening a file."""
    import bpy

    from .log import set_debug_enabled

    scene = bpy.context.scene
    if scene and getattr(scene, "assetdoctor_debug_log", False):
        set_debug_enabled(False)  # detach any stale handler
        set_debug_enabled(True, bpy.data.filepath)  # fresh log for the opened file


def register() -> None:
    import bpy

    from . import prefs
    from .ops import REGISTER_CLASSES as op_classes
    from .ui import REGISTER_CLASSES as ui_classes

    # Order matters: preferences first, then operators, then panels.
    classes = (prefs.AssetDoctorPreferences, *op_classes, *ui_classes)
    for cls in classes:
        bpy.utils.register_class(cls)
        _REGISTERED.append(cls)

    bpy.types.Scene.assetdoctor_scan_dir = bpy.props.StringProperty(
        name="Project Folder",
        description="Folder to recursively scan for .blend link relationships",
        subtype="DIR_PATH",
        default="",
    )
    bpy.types.Scene.assetdoctor_debug_log = bpy.props.BoolProperty(
        name="Enable Debug Log",
        description="Write AssetDoctorDebugLog.txt next to the .blend (or Blender's temp folder "
        "if unsaved) capturing detailed activity, to help diagnose issues. A fresh log starts "
        "each time it's enabled or a file is opened",
        default=False,
        update=_debug_update,
    )

    global _load_post_handler
    from bpy.app.handlers import persistent

    _load_post_handler = persistent(_debug_log_on_load)
    bpy.app.handlers.load_post.append(_load_post_handler)

    # Live progress for any modal operation (folder scan, make-local, …) shown as
    # one shared progress bar at the top of the panel. See ops.progress.
    bpy.types.WindowManager.assetdoctor_op_active = bpy.props.BoolProperty(default=False)
    bpy.types.WindowManager.assetdoctor_op_progress = bpy.props.FloatProperty(
        default=0.0, min=0.0, max=1.0
    )
    bpy.types.WindowManager.assetdoctor_op_status = bpy.props.StringProperty(default="")
    # Pause flag for the running modal op (held between steps; ESC still cancels).
    bpy.types.WindowManager.assetdoctor_op_paused = bpy.props.BoolProperty(default=False)
    # Cancel flag, set by the panel's Cancel button; the modal stops at the next step.
    bpy.types.WindowManager.assetdoctor_op_cancel = bpy.props.BoolProperty(default=False)

    # Persistent per-feature reports: data JSON + expanded keys per feature, plus
    # the currently-shown feature key. See ops/report_store.FEATURES.
    from .ops.report_store import FEATURES

    for key, _label in FEATURES:
        setattr(bpy.types.WindowManager, f"assetdoctor_rep_{key}",
                bpy.props.StringProperty(default=""))
        setattr(bpy.types.WindowManager, f"assetdoctor_repx_{key}",
                bpy.props.StringProperty(default=""))
    bpy.types.WindowManager.assetdoctor_active_report = bpy.props.StringProperty(default="")

    # F5 resource tree (JSON) + its expanded node keys.
    bpy.types.WindowManager.assetdoctor_resource_tree = bpy.props.StringProperty(default="")
    bpy.types.WindowManager.assetdoctor_resource_expanded = bpy.props.StringProperty(default="")
    # Real peak RAM from the last Profile Render (human-readable string).
    bpy.types.WindowManager.assetdoctor_profiled_ram = bpy.props.StringProperty(default="")

    # Materialised, flattened tree rows that the Report/Resource UILists draw
    # (virtualized + scrollable — fixes blank rows on large reports). Rebuilt by
    # ops.report_store from the JSON above whenever a report or its expansion
    # changes. WM-scoped (ephemeral), matching the report JSON's lifetime.
    from .ui.panels import ASSETDOCTOR_PG_broken_lib, ASSETDOCTOR_PG_tree_row

    bpy.types.WindowManager.assetdoctor_report_rows = bpy.props.CollectionProperty(
        type=ASSETDOCTOR_PG_tree_row)
    bpy.types.WindowManager.assetdoctor_report_index = bpy.props.IntProperty(default=0)
    bpy.types.WindowManager.assetdoctor_resource_rows = bpy.props.CollectionProperty(
        type=ASSETDOCTOR_PG_tree_row)
    bpy.types.WindowManager.assetdoctor_resource_index = bpy.props.IntProperty(default=0)

    # F7 per-link relink list: the current file's broken/missing library links,
    # each with a relink target + a per-row checkbox. See ops.relink.
    bpy.types.WindowManager.assetdoctor_broken_libs = bpy.props.CollectionProperty(
        type=ASSETDOCTOR_PG_broken_lib)
    bpy.types.WindowManager.assetdoctor_broken_index = bpy.props.IntProperty(default=0)
    # F6 per-texture relink list: the current file's missing image textures (same
    # row shape, reusing ASSETDOCTOR_PG_broken_lib). See ops.image_relink.
    bpy.types.WindowManager.assetdoctor_broken_imgs = bpy.props.CollectionProperty(
        type=ASSETDOCTOR_PG_broken_lib)
    bpy.types.WindowManager.assetdoctor_broken_imgs_index = bpy.props.IntProperty(default=0)


def unregister() -> None:
    import bpy

    global _load_post_handler
    if _load_post_handler is not None and _load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_post_handler)
    _load_post_handler = None

    for attr in ("assetdoctor_scan_dir", "assetdoctor_debug_log"):
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)
    from .ops.report_store import FEATURES

    wm_attrs = ["assetdoctor_op_active", "assetdoctor_op_progress", "assetdoctor_op_status",
                "assetdoctor_op_paused", "assetdoctor_op_cancel",
                "assetdoctor_active_report", "assetdoctor_resource_tree",
                "assetdoctor_resource_expanded", "assetdoctor_profiled_ram",
                "assetdoctor_report_rows", "assetdoctor_report_index",
                "assetdoctor_resource_rows", "assetdoctor_resource_index",
                "assetdoctor_broken_libs", "assetdoctor_broken_index",
                "assetdoctor_broken_imgs", "assetdoctor_broken_imgs_index"]
    for key, _label in FEATURES:
        wm_attrs += [f"assetdoctor_rep_{key}", f"assetdoctor_repx_{key}"]
    for attr in wm_attrs:
        if hasattr(bpy.types.WindowManager, attr):
            delattr(bpy.types.WindowManager, attr)

    # Reverse order so dependents go before their dependencies.
    while _REGISTERED:
        bpy.utils.unregister_class(_REGISTERED.pop())
