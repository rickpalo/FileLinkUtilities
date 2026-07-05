"""Headless registration smoke test, run by Blender (not pytest):

    blender --background --factory-startup --python tests/smoke_register.py

Imports the addon package and calls register()/unregister() to prove the
classes register cleanly in the target Blender. Exits non-zero on failure so it
can gate CI. Also probes whether blender-asset-tracer is importable under
Blender's bundled Python (informational; TODO #2).
"""

import os
import sys
import traceback

# Make the repo root's PARENT importable so `import filelink` works, mapping
# this dev folder (whatever its case) to the extension's package name.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(REPO_ROOT))

PKG = os.path.basename(REPO_ROOT)  # dev folder name; case-insensitive on Windows


def main() -> int:
    try:
        addon = __import__(PKG)
        addon.register()
        print("REGISTER_OK")
        addon.unregister()
        print("UNREGISTER_OK")
    except Exception:
        traceback.print_exc()
        print("REGISTER_FAIL")
        return 1

    try:
        import blender_asset_tracer  # noqa: F401

        print("BAT_IMPORT_OK")
    except Exception as exc:  # pragma: no cover - informational only
        print(f"BAT_IMPORT_MISSING: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
