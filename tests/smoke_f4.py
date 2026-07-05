"""End-to-end F4 check in Blender:

    blender --background --factory-startup --python tests/smoke_f4.py

Builds a scene with an orphan material, a fake-user-only material, and an
identical pair (one in-use, one orphan); asserts the report classifies them
correctly; then runs the operator's purge path and asserts orphans are removed
while fake-user and in-use data survive.
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


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()
    gather = __import__(f"{PKG}.ops.orphans", fromlist=["_gather"])._gather
    build = __import__(f"{PKG}.core.f4_orphans", fromlist=["build_orphan_report"]).build_orphan_report

    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)

        def mat(name, metallic=None):
            m = bpy.data.materials.new(name)
            m.use_nodes = True
            if metallic is not None:
                m.node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = metallic
            return m

        orphan = mat("OrphanMat", metallic=0.3)        # users == 0
        kept = mat("KeptMat", metallic=0.7)            # fake-user only
        kept.use_fake_user = True
        wood_a = mat("WoodA")                          # identical default graph
        wood_b = mat("WoodB")                          # identical to WoodA, orphan
        obj = bpy.data.objects.new("O", bpy.data.meshes.new("ME"))
        obj.data.materials.append(wood_a)              # WoodA in use
        bpy.context.scene.collection.objects.link(obj)

        report = build(gather(bpy.context))
        checks = []
        orphan_f = next((f for f in report.findings if f.category == "orphan"), None)
        fake_f = next((f for f in report.findings if f.category == "fake_only"), None)
        ident = [f for f in report.findings if f.category == "identical"]

        checks.append(("OrphanMat reported orphan",
                       orphan_f and "Material/OrphanMat" in orphan_f.items))
        checks.append(("KeptMat reported fake-only",
                       fake_f and "Material/KeptMat" in fake_f.items))
        wood_cluster = next((f for f in ident
                             if {"Material/WoodA", "Material/WoodB"} <= set(f.items)), None)
        checks.append(("WoodA/WoodB clustered identical", wood_cluster is not None))
        if wood_cluster:
            cls = {m["id"]: m["cls"] for m in wood_cluster.data["members"]}
            checks.append(("cluster classes correct",
                           cls.get("Material/WoodA") == "in_use"
                           and cls.get("Material/WoodB") == "orphan"))

        # Purge path
        res = bpy.ops.filelink.scan_orphans("EXEC_DEFAULT", purge_orphans=True)
        names = set(bpy.data.materials.keys())
        checks.append(("purge returned FINISHED", res == {"FINISHED"}))
        checks.append(("OrphanMat purged", "OrphanMat" not in names))
        checks.append(("WoodB purged", "WoodB" not in names))
        checks.append(("KeptMat survived (fake user)", "KeptMat" in names))
        checks.append(("WoodA survived (in use)", "WoodA" in names))

        # Group 11 #45, 2026-06-26: the new SELECTIVE purge path
        # (filelink.purge_orphans_selected) — two fresh orphans, untick one,
        # confirm Purge Selected removes ONLY the ticked one (proves real
        # per-row selectivity, not a relabeled purge-everything).
        mat("OrphanX")
        mat("OrphanY")
        wm = bpy.context.window_manager
        bpy.ops.filelink.scan_orphans("EXEC_DEFAULT", purge_orphans=False)
        checks.append(("two orphan rows populated", len(wm.filelink_orphan_rows) == 2))
        for row in wm.filelink_orphan_rows:
            if row.name == "Material/OrphanX":
                row.selected = False

        res2 = bpy.ops.filelink.purge_orphans_selected("EXEC_DEFAULT")
        names2 = set(bpy.data.materials.keys())
        checks.append(("selective purge FINISHED", res2 == {"FINISHED"}))
        checks.append(("OrphanY (ticked) purged", "OrphanY" not in names2))
        checks.append(("OrphanX (unticked) survived", "OrphanX" in names2))
        checks.append(("rows cleared after selective purge", len(wm.filelink_orphan_rows) == 0))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("F4_SMOKE_OK" if ok else "F4_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("F4_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
