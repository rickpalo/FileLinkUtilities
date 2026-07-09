"""End-to-end Check Armature Deformation smoke test in Blender:

    blender --background --factory-startup --python tests/smoke_deform_check.py

Builds a two-bone armature ("Bone" at rest, "Bad" posed 1000 units away from
its rest position) and a two-vertex mesh whose single edge has one vertex in
each vertex group, deformed via an Armature modifier. Also builds a second,
untouched clean mesh+armature pair posed only slightly (ordinary variance)
to confirm it is NOT flagged. Runs the real ``filelink.scan_deform_issues``
operator and asserts the stashed report and ``wm.filelink_deform_rows`` flag
only the exploded object.
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


def _build_rig(bpy, name, bad_offset):
    """One armature (bones "Bone" + "Bad") + one two-vertex/one-edge mesh
    deformed by it. ``bad_offset`` is the pose-space translation applied to
    the "Bad" bone (a small offset makes a healthy control case)."""
    arm_data = bpy.data.armatures.new(f"{name}RigData")
    arm_obj = bpy.data.objects.new(f"{name}Rig", arm_data)
    bpy.context.scene.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    b1 = eb.new("Bone")
    b1.head = (0, 0, 0)
    b1.tail = (0, 0, 1)
    b2 = eb.new("Bad")
    b2.head = (0, 0, 0)
    b2.tail = (0, 0, 1)
    bpy.ops.object.mode_set(mode="OBJECT")

    mesh = bpy.data.meshes.new(f"{name}MeshData")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0)], [(0, 1)], [])
    mesh.update()
    obj = bpy.data.objects.new(f"{name}Mesh", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.vertex_groups.new(name="Bone").add([0], 1.0, "REPLACE")
    obj.vertex_groups.new(name="Bad").add([1], 1.0, "REPLACE")
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm_obj
    mod.use_vertex_groups = True
    mod.show_viewport = True

    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="POSE")
    arm_obj.pose.bones["Bad"].location = bad_offset
    bpy.ops.object.mode_set(mode="OBJECT")

    return arm_obj, obj


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)

        _build_rig(bpy, "Exploded", bad_offset=(1000.0, 0.0, 0.0))
        _build_rig(bpy, "Healthy", bad_offset=(0.05, 0.0, 0.0))

        bpy.context.view_layer.objects.active = None
        res = bpy.ops.filelink.scan_deform_issues("EXEC_DEFAULT")
        checks.append(("operator FINISHED", res == {"FINISHED"}))

        wm = bpy.context.window_manager
        checks.append(("filelink_deform_scanned is True", wm.filelink_deform_scanned))

        rows = {r.name: r for r in wm.filelink_deform_rows}
        checks.append(("ExplodedMesh flagged", "ExplodedMesh" in rows))
        checks.append(("HealthyMesh NOT flagged", "HealthyMesh" not in rows))

        if "ExplodedMesh" in rows:
            row = rows["ExplodedMesh"]
            checks.append(("ExplodedMesh worst_ratio is large", row.worst_ratio > 100.0))
            checks.append(("ExplodedMesh vertex_count == 2", row.vertex_count == 2))
            checks.append(("ExplodedMesh is_locally_fixable (local data)",
                           row.is_locally_fixable))
            checks.append(("ExplodedMesh armature_name is its Rig",
                           row.armature_name == "ExplodedRig"))

        Report = __import__(f"{PKG}.core.report", fromlist=["Report"]).Report
        report = Report.from_json(wm.filelink_rep_deformcheck)
        checks.append(("report has exactly 1 finding",
                       len(report.findings) == 1))
        checks.append(("report finding names ExplodedMesh",
                       report.findings and report.findings[0].message.startswith("ExplodedMesh")))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("DEFORMCHECK_SMOKE_OK" if ok else "DEFORMCHECK_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("DEFORMCHECK_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
