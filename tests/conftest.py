"""Pytest bootstrap (lives in tests/ so pytest never imports the bpy-dependent
top-level ``filelink`` package during collection).

Tests exercise the bpy-free ``core`` package only. We put the repo root on
sys.path so ``import core.report`` works WITHOUT importing the top-level
package. Core modules use *relative* imports among themselves, which resolve
both here (as top-level ``core``) and inside Blender (as ``filelink.core``).
"""

import glob
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Put the bundled BAT wheel (a zip) on sys.path so blendscan tests can import it
# outside Blender, exactly as Blender will at runtime.
_bat = glob.glob(str(REPO_ROOT / "wheels" / "blender_asset_tracer-*.whl"))
if _bat:
    sys.path.insert(0, _bat[0])

FIXTURES = REPO_ROOT / "tests" / "fixtures"
LINKPROJ = FIXTURES / "linkproj"
