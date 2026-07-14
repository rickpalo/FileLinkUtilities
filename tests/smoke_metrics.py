"""Health-dashboard metrics smoke test:

    blender --background --factory-startup --python tests/smoke_metrics.py

Exercises ops.metrics.current / sync_baseline / rows + the "since you opened
the file" baseline reset, without a UI — the panel draw only formats what
rows() returns, so covering rows() covers the dashboard's logic.
"""

import glob
import json
import pathlib
import sys
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
_bat = glob.glob(str(REPO_ROOT / "wheels" / "blender_asset_tracer-*.whl"))
if _bat:
    sys.path.insert(0, _bat[0])
PKG = REPO_ROOT.name


def main():
    import bpy
    from importlib import import_module

    addon = __import__(PKG)
    addon.register()
    metrics = import_module(f"{PKG}.ops.metrics")

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        wm = bpy.context.window_manager
        wm.filelink_metrics_baseline = ""  # simulate a just-opened file

        def dash():
            # key rows by label -> (key, label, unit, base, cur)
            return {t[1]: t for t in metrics.rows(wm)}

        d = dash()
        checks.append(("size on disk always shown", "Size on disk" in d))
        checks.append(("linked libs always shown", "Linked libs" in d))
        checks.append(("dup materials hidden when unscanned", "Dup materials" not in d))

        base = json.loads(wm.filelink_metrics_baseline or "{}")
        checks.append(("instant metrics baselined on first draw",
                       "size_on_disk" in base and "linked_libs" in base))

        # A duplicate-material scan finds 14 -> reveal + baseline at 14.
        wm.filelink_mat_scanned = True
        wm.filelink_mat_removable = 14
        d = dash()
        dm = d.get("Dup materials")
        checks.append(("dup materials revealed + baselined at 14",
                       dm is not None and dm[3] == 14 and dm[4] == 14))
        checks.append(("dup materials > 0 reads 'attention'",
                       metrics.status("dup_materials", 14, 14) == "attention"))

        # Merge down to 2 -> baseline 14 held, current 2.
        wm.filelink_mat_removable = 2
        dm = dash().get("Dup materials")
        checks.append(("dup materials shows 14 -> 2", dm is not None and dm[3] == 14 and dm[4] == 2))
        checks.append(("dup materials cleared to 0 reads 'good'",
                       metrics.status("dup_materials", 14, 0) == "good"))

        # reveal_nonzero: a metric that scans to zero from the start stays hidden.
        wm.filelink_geo_scanned = True
        wm.filelink_geo_removable = 0
        checks.append(("zero dup meshes stays hidden", "Dup meshes" not in dash()))

        # Render RAM appears once the raw byte prop is populated (4 GB > IntProperty range).
        four_gb = 4 * 1024 ** 3
        wm.filelink_profiled_ram_b = str(four_gb)
        rr = dash().get("Render RAM")
        checks.append(("render RAM appears once profiled", rr is not None and rr[4] == four_gb))

        # Opening another file clears the baseline -> everything re-baselines.
        wm.filelink_metrics_baseline = ""
        wm.filelink_mat_removable = 2  # the newly-opened file's starting state
        dm = dash().get("Dup materials")
        checks.append(("after reset, dup mats re-baseline at 2",
                       dm is not None and dm[3] == 2 and dm[4] == 2))

        # Delta formatting uses a real minus sign; a reduction reads negative.
        checks.append(("count delta", metrics.delta_str("count", 14, 2) == "−12"))
        checks.append(("bytes delta negative on reduction",
                       metrics.delta_str("bytes", four_gb, 3 * 1024 ** 3).startswith("−")))
        loc, lnk = metrics.size_on_disk()
        checks.append(("size_on_disk returns (local, linked) ints",
                       isinstance(loc, int) and isinstance(lnk, int)))
        checks.append(("size_on_disk total is sum of local+linked",
                       dash().get("Size on disk", (None,) * 5)[4] == loc + lnk))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("METRICS_SMOKE_OK" if ok else "METRICS_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("METRICS_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
