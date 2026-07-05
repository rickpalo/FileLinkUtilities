"""Batch D — headless dry-run render for warnings.

Launches a SEPARATE background Blender process against the file on disk to
render one throwaway low-res frame, so render-time problems (missing textures,
driver exceptions, etc.) surface without touching this session's UI, scene, or
undo stack. Distinct from F5's in-process "Profile Render" (``ops/resource.py``),
which measures real RAM by rendering the live file in this process.

Modal so the panel stays responsive while the subprocess runs; the heavy lifting
(building the command, parsing the output) is all in ``core.dryrun`` and unit
tested there — this file only owns the subprocess lifecycle.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time

import bpy

from .progress import ModalProgressMixin
from .report_store import stash_report

# Bounded — guards against a genuinely hung subprocess (e.g. a driver stuck in an
# infinite loop) — but generous: user-reported 300s timing out on real multi-GB,
# multi-library files (2026-06-24) — most of that time is loading/resolving the
# linked libraries and decoding thousands of textures on first access (a low-res
# single-sample render of an ALREADY-loaded scene is fast; getting the scene
# loaded on a Synology-synced multi-GB file tree is what's slow, and this
# subprocess's wall-clock covers both, not just the render call). 30 minutes,
# matching this project's own documented real load times for single libraries
# this size (People1 at 15GB ~10+ min just to open+walk its block table).
_TIMEOUT_SECONDS = 1800
_POLL_SLEEP = 0.2  # avoid busy-spinning when execute() drains the generator directly


def _popen_kwargs() -> dict:
    """Suppress the console window a background blender.exe would otherwise
    flash on Windows; harmless elsewhere."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


class FILELINK_OT_dryrun_render(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "filelink.dryrun_render"
    bl_label = "Dry-Run Render"
    bl_description = (
        "Render one low-res frame in a SEPARATE background Blender process to "
        "surface render-time warnings (missing textures, driver errors) without "
        "touching this session. Reads the file from disk — save first"
    )
    bl_options = {"REGISTER"}

    def cancel_message(self) -> str:
        return "Dry-run render cancelled"

    def run_steps(self, context):
        from ..core import dryrun

        blend_path = bpy.data.filepath
        if not blend_path:
            self.report({"ERROR"}, "Save the file before running a dry-run render")
            return
        if bpy.data.is_dirty:
            self.report({"ERROR"},
                        "Unsaved changes — save before a dry-run render (it reads from disk)")
            return

        script_path = None
        log_path = None
        try:
            fd, script_path = tempfile.mkstemp(suffix=".py", prefix="filelink_dryrun_")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(dryrun.build_dryrun_script())
            log_path = script_path[:-3] + ".log"

            cmd = dryrun.build_dryrun_command(bpy.app.binary_path, blend_path, script_path)
            yield (0.05, "Starting headless Blender…")
            with open(log_path, "w", encoding="utf-8") as log_fh:
                proc = subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT,
                                        **_popen_kwargs())
                start = time.monotonic()
                while proc.poll() is None:
                    elapsed = time.monotonic() - start
                    if elapsed > _TIMEOUT_SECONDS:
                        proc.kill()
                        self.report({"ERROR"},
                                   f"Dry-run render timed out after {dryrun.format_elapsed(_TIMEOUT_SECONDS)}")
                        return
                    time.sleep(_POLL_SLEEP)
                    fraction = min(0.9, 0.1 + elapsed / _TIMEOUT_SECONDS)
                    yield (fraction, f"Rendering… ({dryrun.format_elapsed(elapsed)})")

            returncode = proc.returncode
            with open(log_path, "r", encoding="utf-8", errors="replace") as log_fh:
                log_text = log_fh.read()
        finally:
            for p in (script_path, log_path):
                if p:
                    try:
                        os.remove(p)
                    except OSError:
                        pass

        report = dryrun.parse_render_log(log_text, returncode=returncode)
        stash_report(context, report, "f9")

        yield (1.0, "Done")
        if returncode != 0:
            self.report({"ERROR"},
                       f"Dry-run render's background Blender process crashed (exit "
                       f"code {returncode}) — see the report for details")
        elif report.max_severity == "error":
            self.report({"WARNING"},
                       f"Dry-run render found {report.count('error')} error(s)")
        elif report.max_severity == "warning":
            self.report({"WARNING"},
                       f"Dry-run render found {report.count('warning')} warning(s)")
        else:
            self.report({"INFO"}, "✓ Dry-run render found no warnings")
