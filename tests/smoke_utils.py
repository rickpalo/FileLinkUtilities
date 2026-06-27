"""End-to-end check for the UI plumbing added for the TODO batch:

    blender --background --factory-startup --python tests/smoke_utils.py

Verifies the Scene properties register, the Enable Debug Log toggle writes a
file, and each operator's tooltip description() returns a non-empty string for
its variants.
"""

import glob
import pathlib
import sys
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
_bat = glob.glob(str(REPO_ROOT / "wheels" / "blender_asset_tracer-*.whl"))
if _bat:
    sys.path.insert(0, _bat[0])
PKG = REPO_ROOT.name


class _Props:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()
    checks = []
    try:
        sc = bpy.context.scene
        wm = bpy.context.window_manager
        checks.append(("scan_dir prop registered", hasattr(sc, "assetdoctor_scan_dir")))
        checks.append(("debug_log prop registered", hasattr(sc, "assetdoctor_debug_log")))
        checks.append(("op progress props registered",
                       hasattr(wm, "assetdoctor_op_active")
                       and hasattr(wm, "assetdoctor_op_progress")
                       and hasattr(wm, "assetdoctor_op_status")))

        # Toggle debug on (unsaved file -> temp dir) and confirm the file appears.
        sc.assetdoctor_debug_log = True
        log_path = pathlib.Path(bpy.app.tempdir) / "AssetDoctorDebugLog.txt"
        checks.append(("debug log file created", log_path.is_file()))
        sc.assetdoctor_debug_log = False

        # description() returns text for each variant.
        ml = __import__(f"{PKG}.ops.make_local", fromlist=["x"]).ASSETDOCTOR_OT_make_local
        md = __import__(f"{PKG}.ops.material_dedup", fromlist=["x"]).ASSETDOCTOR_OT_material_dedup
        orp = __import__(f"{PKG}.ops.orphans", fromlist=["x"]).ASSETDOCTOR_OT_scan_orphans
        d1 = ml.description(bpy.context, _Props(apply=True, mode="NEW_FILE"))
        d2 = ml.description(bpy.context, _Props(apply=True, mode="IN_PLACE"))
        d3 = ml.description(bpy.context, _Props(apply=False, mode="NEW_FILE"))
        d4 = md.description(bpy.context, _Props(apply=True))
        d5 = orp.description(bpy.context, _Props(purge_orphans=True))
        checks.append(("descriptions non-empty & distinct",
                       all(isinstance(d, str) and d for d in (d1, d2, d3, d4, d5))
                       and d1 != d2))

        # Open-preferences operator registered + reachable.
        checks.append(("open_preferences op registered",
                       hasattr(bpy.types, "ASSETDOCTOR_OT_open_preferences")
                       and hasattr(bpy.ops.assetdoctor, "open_preferences")))

        # Collapsible feature sub-panels registered + parented to the Scene panel
        # (Batch 5, 2026-06-23 — migrated off the retired VIEW_3D N-panel root;
        # Current File Data/Analyze added Phase 3a, 2026-06-25; Orphans/Geometry/
        # Results all retired in the Group 11 panel-consolidation pass, 2026-06-26,
        # once Analyze/Utilities grew real inline homes for everything they held).
        sub_ids = ["ASSETDOCTOR_PT_current_file_data", "ASSETDOCTOR_PT_analyze",
                   "ASSETDOCTOR_PT_analyze_external", "ASSETDOCTOR_PT_utilities"]
        panels_ok = all(
            getattr(getattr(bpy.types, pid, None), "bl_parent_id", None) == "ASSETDOCTOR_PT_scene_deps"
            for pid in sub_ids
        )
        checks.append((f"{len(sub_ids)} collapsible sub-panels parented to scene_deps", panels_ok))

        # The retired VIEW_3D N-panel root + its now-redundant standalone Report/
        # Resource panels must not still be registered (Batch 5). The Resource
        # Analyzer SCENE sub-panel joined this list later (its by-type breakdown
        # moved into the Analyze panel's "Analyze Memory/Disk" row instead).
        # Orphans/Geometry/Results joined in the Group 11 pass (2026-06-26) once
        # their one remaining button each got a real selective-apply UI inline
        # in Analyze, and the generic Reports selector was replaced by every
        # feature having its own inline display.
        retired_ids = ["ASSETDOCTOR_PT_main", "ASSETDOCTOR_PT_project",
                       "ASSETDOCTOR_PT_report", "ASSETDOCTOR_PT_resources",
                       "ASSETDOCTOR_PT_resource_tools", "ASSETDOCTOR_PT_make_local",
                       "ASSETDOCTOR_PT_materials", "ASSETDOCTOR_PT_orphans",
                       "ASSETDOCTOR_PT_geometry", "ASSETDOCTOR_PT_results"]
        checks.append(("retired N-panel classes are gone",
                       all(not hasattr(bpy.types, pid) for pid in retired_ids)))

        # f3 (Materials) has its own inline keeper-dropdown UI in Analyze
        # (_draw_material_dups) — available_features() still surfaces it as a
        # generic stashed-report feature too (used by inline Export buttons
        # elsewhere), confirming the underlying report_store plumbing the now-
        # deleted generic selector used is still intact for other consumers.
        wm.assetdoctor_rep_f3 = '{"title": "t", "findings": []}'
        report_store = __import__(f"{PKG}.ops.report_store", fromlist=["x"])
        present = [k for k, _ in report_store.available_features(wm)]
        checks.append(("f3 (Materials) report surfaces via available_features",
                       "f3" in present))
        wm.assetdoctor_rep_f3 = ""

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("UTILS_SMOKE_OK" if ok else "UTILS_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("UTILS_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
