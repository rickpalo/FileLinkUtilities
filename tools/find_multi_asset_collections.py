"""Scan every Models/*.blend under a library root for asset-marking data-
quality issues on COLLECTIONS -- the models-side equivalent of
find_multi_asset_materials.py. One Blender session for the whole scan
(open_mainfile per file, not a relaunch).

Flags three issue kinds:
  * multi_asset   -- more than one collection in the file is asset-marked
                     (usually the real model plus a leftover rig/lighting/
                     staging collection, e.g. "Camera and lights", "misc",
                     a "*_rig" armature-only collection) -- this is the
                     likely cause of several "render came out empty" skips
                     in the thumbnail batch: the picker grabbed the helper
                     collection instead of the real model.
  * no_asset      -- zero collections in the file are asset-marked -- the
                     file won't show up in the Asset Browser at all.
  * name_mismatch -- exactly one asset-marked collection, but its name
                     doesn't match the file's own basename (informational
                     only -- some are intentionally different).

Read-only: never modifies or saves any file.

Usage:
    blender -b --python tools/find_multi_asset_collections.py -- \\
        --library "D:\\BlenderLibraries\\LocalLibrary" \\
        [--csv "D:\\BlenderReorg_Audit\\multi_asset_collections.csv"]
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import sys

import bpy


def _parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--library", required=True)
    p.add_argument("--csv", default=None)
    return p.parse_args(argv)


def main():
    args = _parse_args()
    csv_path = args.csv or os.path.join(args.library, "multi_asset_collections.csv")

    files = sorted(glob.glob(os.path.join(args.library, "Models", "**", "*.blend"), recursive=True))

    rows = []
    print(f"Scanning {len(files)} model files...")
    for i, path in enumerate(files, 1):
        try:
            bpy.ops.wm.open_mainfile(filepath=path)
        except Exception as exc:
            rows.append((path, "open_failed", str(exc)))
            continue

        marked = [c for c in bpy.data.collections if getattr(c, "asset_data", None) is not None]
        basename = os.path.splitext(os.path.basename(path))[0].strip().lower()

        if len(marked) == 0:
            rows.append((path, "no_asset", ""))
        elif len(marked) > 1:
            names = [c.name for c in marked]
            rows.append((path, "multi_asset", "; ".join(names)))
        else:
            name = marked[0].name
            if name.strip().lower() != basename:
                rows.append((path, "name_mismatch", name))

        if i % 50 == 0:
            print(f"  ...{i}/{len(files)}")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "issue", "detail"])
        w.writerows(rows)

    by_issue = {}
    for _, issue, _ in rows:
        by_issue[issue] = by_issue.get(issue, 0) + 1
    print(f"\nCSV written: {csv_path}")
    print(f"Scanned {len(files)} files, {len(rows)} flagged:")
    for issue, count in sorted(by_issue.items()):
        print(f"  {issue}: {count}")


main()
