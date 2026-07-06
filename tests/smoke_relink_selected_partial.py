"""Relink Selected partial-failure handling, end-to-end in Blender:

    blender --background --factory-startup --python tests/smoke_relink_selected_partial.py

Reproduces the user-reported bug: one ticked texture's target file went missing
(a network-drive sync lag, in the real report) between staging and Relink
Selected. The old behaviour aborted the WHOLE batch — even textures with a
perfectly good target went unrelinked — and dumped every absent name into one
ERROR. Checks the fix: the good ones relink, the bad one is reported and left
ticked (so a retry picks it up once the file reappears), not silently dropped.
"""

import os
import pathlib
import sys
import tempfile
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
PKG = REPO_ROOT.name


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()

    checks = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bpy.ops.wm.save_as_mainfile(filepath=str(root / "scene.blend"))

            good_path = root / "good.png"
            good_path.write_bytes(b"x")
            missing_path = root / "missing.png"  # never created — simulates the race

            img_good = bpy.data.images.new("good.png", 2, 2)
            img_good.filepath = "//missing_good.png"
            img_good.source = 'FILE'
            img_bad = bpy.data.images.new("bad.png", 2, 2)
            img_bad.filepath = "//missing_bad.png"
            img_bad.source = 'FILE'

            wm = bpy.context.window_manager
            coll = wm.filelink_broken_imgs
            coll.clear()
            row_good = coll.add()
            row_good.name = "good.png"
            row_good.stored = "//missing_good.png"
            row_good.target = str(good_path)
            row_good.selected = True
            row_bad = coll.add()
            row_bad.name = "bad.png"
            row_bad.stored = "//missing_bad.png"
            row_bad.target = str(missing_path)
            row_bad.selected = True

            res = bpy.ops.filelink.relink_textures_selected("EXEC_DEFAULT")
            checks.append(("operator FINISHED (not CANCELLED)", res == {"FINISHED"}))

            checks.append(("good texture actually got relinked",
                           os.path.normpath(bpy.path.abspath(img_good.filepath))
                           == os.path.normpath(str(good_path))))
            # _populate_broken_images (called at the end of the operator) rebuilds
            # the whole collection via coll.clear() — the pre-call row references
            # are now stale/dangling, so re-fetch by name, same as the existing
            # smoke_folder_search_diagnostics.py pattern.
            rows = {r.name: r for r in wm.filelink_broken_imgs}
            row_bad_after = rows.get("bad.png")
            checks.append(("bad texture's row still present", row_bad_after is not None))
            checks.append(("bad texture's row still ticked for retry",
                           row_bad_after is not None and row_bad_after.selected))
            checks.append(("bad texture's row target preserved (not wiped/re-guessed)",
                           row_bad_after is not None
                           and os.path.normpath(row_bad_after.target) == os.path.normpath(str(missing_path))))
            checks.append(("bad texture's image untouched (still points at old path)",
                           img_bad.filepath == "//missing_bad.png"))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("RELINK_PARTIAL_SMOKE_OK" if ok else "RELINK_PARTIAL_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("RELINK_PARTIAL_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
