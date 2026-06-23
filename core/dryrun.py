"""Batch D — headless dry-run render for warnings (bpy-free).

F5's "Profile Render" renders IN-PROCESS (the live file, the live UI) to measure
real RAM. This is a different job: catch render-TIME problems that don't show up
in any of AssetDoctor's static scans (missing textures only Blender's image loader
notices, driver exceptions, etc.) — without touching the user's open session at
all. That means a SEPARATE headless Blender, launched as a subprocess against the
file on disk, rendering one throwaway low-res frame; its console output is the
only signal we get, so this module's job is building that subprocess's argv +
script, and parsing whatever it printed into a Report.

Kept bpy-free and unit-tested like every other ``core`` module: the script text
and command list are just strings/lists; the actual ``bpy.ops.render.render()``
call only ever runs inside the spawned subprocess, never here.
"""

from __future__ import annotations

import re

from .report import Finding, Report

DEFAULT_RESOLUTION_PERCENTAGE = 10
DEFAULT_SAMPLES = 1


def build_dryrun_script(resolution_percentage: int = DEFAULT_RESOLUTION_PERCENTAGE,
                         samples: int = DEFAULT_SAMPLES) -> str:
    """Python source for the subprocess: shrink the render then render ONE frame
    to memory (``write_still=False`` — never writes an output file). Whatever
    Blender prints (errors, missing-image warnings, driver tracebacks) is the
    signal; we don't need the pixels."""
    return (
        "import bpy\n"
        "scene = bpy.context.scene\n"
        f"scene.render.resolution_percentage = {int(resolution_percentage)}\n"
        "engine = scene.render.engine\n"
        "if engine == 'CYCLES':\n"
        f"    scene.cycles.samples = {int(samples)}\n"
        "elif engine in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):\n"
        f"    scene.eevee.taa_render_samples = {int(samples)}\n"
        "bpy.ops.render.render(write_still=False)\n"
    )


def build_dryrun_command(blender_exe: str, blend_path: str, script_path: str) -> list[str]:
    """Argv to launch the dry-run subprocess.

    ``--factory-startup`` is deliberate: this feature hunts for render-time
    problems in the FILE (missing textures, broken drivers), and a normal launch
    would mix in unrelated startup noise from the user's other add-ons (license
    banners, etc.), which the parser can't tell apart from a real warning. The
    file's own data (materials, drivers, node trees) is unaffected — add-ons are
    only needed to AUTHOR that content, not to render it.
    """
    return [blender_exe, "--background", "--factory-startup", blend_path,
            "--python", script_path]


# --- log parsing -------------------------------------------------------------

_IMAGE_PATTERN = re.compile(
    r"(unable to open|cannot read|could not (?:open|load)|failed to (?:read|load)|"
    r"couldn'?t (?:open|load)).{0,80}\bimage\b"
    r"|\bimage\b.{0,40}(not found|missing|failed to load)",
    re.IGNORECASE,
)
_DRIVER_PATTERN = re.compile(r"\bdriver\b", re.IGNORECASE)
_ERROR_PATTERN = re.compile(r"\berror\b", re.IGNORECASE)
_WARNING_PATTERN = re.compile(r"\bwarning\b", re.IGNORECASE)
_TRACEBACK_PATTERN = re.compile(r"\btraceback\b", re.IGNORECASE)

_SEVERITY_BY_CATEGORY = {
    "missing_image": "error",
    "driver_error": "error",
    "render_error": "error",
    "render_warning": "warning",
}


def classify_line(line: str) -> str | None:
    """Category for one noteworthy console line, or ``None`` to ignore it."""
    if _IMAGE_PATTERN.search(line):
        return "missing_image"
    if _DRIVER_PATTERN.search(line) and (_ERROR_PATTERN.search(line) or _TRACEBACK_PATTERN.search(line)):
        return "driver_error"
    if _ERROR_PATTERN.search(line):
        return "render_error"
    if _WARNING_PATTERN.search(line):
        return "render_warning"
    return None


def parse_render_log(log_text: str) -> Report:
    """Parse a dry-run subprocess's combined stdout/stderr into a Report.

    Identical lines (e.g. the same missing texture warned once per tile) are
    deduplicated with an "(xN)" count rather than repeated."""
    counts: dict[str, dict[str, int]] = {}
    for raw_line in log_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        category = classify_line(line)
        if category is None:
            continue
        bucket = counts.setdefault(category, {})
        bucket[line] = bucket.get(line, 0) + 1

    report = Report(title="Dry-Run Render Warnings", feature="f9")
    if not counts:
        report.add(Finding(category="clean", severity="info",
                           message="No render warnings or errors found"))
        return report

    for category, lines in counts.items():
        severity = _SEVERITY_BY_CATEGORY.get(category, "warning")
        for line, n in lines.items():
            message = line if n == 1 else f"{line} (x{n})"
            report.add(Finding(category=category, message=message, severity=severity))
    return report


__all__ = [
    "DEFAULT_RESOLUTION_PERCENTAGE", "DEFAULT_SAMPLES",
    "build_dryrun_script", "build_dryrun_command",
    "classify_line", "parse_render_log",
]
