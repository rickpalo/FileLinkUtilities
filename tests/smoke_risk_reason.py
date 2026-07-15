"""datablock_risk_reason regression smoke test:

    blender --background --factory-startup --python tests/smoke_risk_reason.py

Locks the "linked from a missing library" guard (PSM_Stage crashes v0.3.4/5):
a datablock flagged neither is_missing nor override, but linked from a library
whose file is missing, must be reported risky so no geometry-reading path
(shape keys, Find Duplicate Geometry, Orphans) ever reads its dangling data.
The function is all getattr, so duck-typed mocks exercise every branch.
"""

import glob
import pathlib
import sys
import traceback
from types import SimpleNamespace

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
_bat = glob.glob(str(REPO_ROOT / "wheels" / "blender_asset_tracer-*.whl"))
if _bat:
    sys.path.insert(0, _bat[0])
PKG = REPO_ROOT.name


def _block(**kw):
    kw.setdefault("name", "X")
    kw.setdefault("is_missing", False)
    kw.setdefault("override_library", None)
    kw.setdefault("library", None)
    return SimpleNamespace(**kw)


def main():
    import bpy  # noqa: F401
    from importlib import import_module

    addon = __import__(PKG)
    addon.register()
    rr = import_module(f"{PKG}.ops.extract").datablock_risk_reason

    checks = []
    try:
        checks.append(("plain local block is safe", rr(_block()) == ""))
        checks.append(("missing placeholder flagged",
                       "missing placeholder" in rr(_block(is_missing=True))))
        checks.append(("override flagged",
                       "Override" in rr(_block(override_library=object()))))
        checks.append(("linked from PRESENT library is safe",
                       rr(_block(library=SimpleNamespace(is_missing=False))) == ""))
        checks.append(("linked from MISSING library flagged (the fix)",
                       "missing library" in rr(_block(library=SimpleNamespace(is_missing=True)))))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("RISK_REASON_SMOKE_OK" if ok else "RISK_REASON_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("RISK_REASON_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
