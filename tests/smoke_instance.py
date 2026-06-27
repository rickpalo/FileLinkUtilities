"""End-to-end geometry-instancing check in Blender:

    blender --background --factory-startup --python tests/smoke_instance.py

Two objects with identical but SEPARATE meshes should be detected as one
instanceable group; after Apply they share a single mesh datablock and the
duplicate is removed.
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

TRI = ([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()
    gather = __import__(f"{PKG}.ops.instance_dedup", fromlist=["_gather"])._gather
    build = __import__(f"{PKG}.core.geometry_dedup", fromlist=["build_instance_plan"]).build_instance_plan

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)

        def obj_with_own_mesh(name, shape=TRI):
            me = bpy.data.meshes.new(name + "_mesh")
            me.from_pydata(*shape)
            me.update()
            o = bpy.data.objects.new(name, me)
            bpy.context.scene.collection.objects.link(o)
            return o

        a = obj_with_own_mesh("A")
        b = obj_with_own_mesh("B")  # identical geometry, separate datablock
        sphere = bpy.data.meshes.new("Sphere")
        sphere.from_pydata([(0, 0, 0), (2, 0, 0), (0, 2, 0)], [], [(0, 1, 2)])
        c = bpy.data.objects.new("C", sphere)  # different geometry
        bpy.context.scene.collection.objects.link(c)

        checks.append(("starts with distinct meshes", a.data != b.data))

        items, _ = gather(bpy.context)
        report, plan = build(items)
        checks.append(("one instanceable group", len(plan) == 1))
        if plan:
            grp = plan[0]
            checks.append(("group covers A and B",
                           {grp["canonical"], *grp["victims"]} == {a.data.name, b.data.name}))

        res = bpy.ops.assetdoctor.instance_geometry("EXEC_DEFAULT", apply=True)
        checks.append(("apply FINISHED", res == {"FINISHED"}))
        checks.append(("A and B now share one mesh", a.data == b.data))
        checks.append(("duplicate mesh removed", len(bpy.data.meshes) == 2))  # shared + sphere
        checks.append(("sphere untouched", c.data.name == "Sphere"))

        # Group 11 #44, 2026-06-26: the new SELECTIVE apply path
        # (assetdoctor.instance_geometry_selected) — a fresh duplicate pair (a
        # DIFFERENT shape than A/B's, so this group is isolated from the
        # already-merged shared mesh above), scan via the report-only path
        # (populates assetdoctor_geo_families), untick the row, confirm
        # Instance Selected does NOTHING (proves "selective" is real, not just
        # a relabeled apply-everything), then re-tick and confirm it DOES.
        quad = ([(0, 0, 0), (3, 0, 0), (3, 3, 0), (0, 3, 0)], [], [(0, 1, 2, 3)])
        d = obj_with_own_mesh("D", quad)
        e = obj_with_own_mesh("E", quad)
        res2 = bpy.ops.assetdoctor.instance_geometry("EXEC_DEFAULT", apply=False)
        wm = bpy.context.window_manager
        checks.append(("scan FINISHED", res2 == {"FINISHED"}))
        checks.append(("one geo family populated", len(wm.assetdoctor_geo_families) == 1))
        checks.append(("group covers only D and E", set(wm.assetdoctor_geo_families[0].victims.split("\n"))
                       | {wm.assetdoctor_geo_families[0].name} == {d.data.name, e.data.name}))

        wm.assetdoctor_geo_families[0].selected = False
        res3 = bpy.ops.assetdoctor.instance_geometry_selected("EXEC_DEFAULT")
        checks.append(("unselected: CANCELLED (nothing ticked)", res3 == {"CANCELLED"}))
        checks.append(("unselected: D and E still distinct", d.data != e.data))
        checks.append(("unselected: row NOT cleared (CANCELLED is a no-op)",
                       len(wm.assetdoctor_geo_families) == 1))

        wm.assetdoctor_geo_families[0].selected = True
        res4 = bpy.ops.assetdoctor.instance_geometry_selected("EXEC_DEFAULT")
        checks.append(("selected: FINISHED", res4 == {"FINISHED"}))
        checks.append(("selected: D and E now share one mesh", d.data == e.data))
        checks.append(("selected: rows cleared after apply", len(wm.assetdoctor_geo_families) == 0))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("INSTANCE_SMOKE_OK" if ok else "INSTANCE_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("INSTANCE_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
