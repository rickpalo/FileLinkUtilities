"""docs/TODO.md #22 — Automated Cleanup: Scan -> Review (tick/untick) ->
Apply Selected. Both operators here are thin sequencers over the SAME 4
real functions (Make Local / Duplicate Materials / Duplicate Geometry /
Orphans) — Scan runs each one's own report-only step unchanged (populating
its own report AND its own checkbox rows, exactly as if clicked directly);
Apply Selected runs each one's own ticked-respecting apply step unchanged,
bracketed by a single backup and a before/after resource snapshot for the
savings summary. Nothing here reimplements any of the 4 functions' own
logic — see ops.analyze_all's module docstring for why real ``bpy.ops``
dispatch (not direct Python calls) is this project's house style for a
sequencer.
"""

from __future__ import annotations

import bpy

from ..core.analyze_steps import CLEANUP_APPLY_STEPS, CLEANUP_SCAN_STEPS
from ..core.report import Finding, Report
from .analyze_all import _AnalyzeSequencerMixin, _call
from .progress import ModalProgressMixin


def _cleanup_include(scene) -> dict:
    return {
        "cleanup_make_local": scene.filelink_cleanup_include_makelocal,
        "cleanup_materials": scene.filelink_cleanup_include_materials,
        "cleanup_geometry": scene.filelink_cleanup_include_geometry,
        "cleanup_orphans": scene.filelink_cleanup_include_orphans,
    }


def _filtered_steps(steps, scene):
    include = _cleanup_include(scene)
    return tuple(s for s in steps if include.get(s.key))


class FILELINK_OT_cleanup_scan(_AnalyzeSequencerMixin, ModalProgressMixin, bpy.types.Operator):
    bl_idname = "filelink.cleanup_scan"
    bl_label = "Automated Cleanup: Scan"
    bl_description = ("Scan every INCLUDED cleanup function (Make Local / Duplicate Materials / "
                      "Duplicate Geometry / Orphans) in one click. Read-only — each one's own "
                      "report/checkbox list is filled in exactly as if you'd clicked it yourself")
    bl_options = {"REGISTER"}

    _run_label = "Automated Cleanup Scan"

    @classmethod
    def poll(cls, context):
        return bool(_filtered_steps(CLEANUP_SCAN_STEPS, context.scene))

    def invoke(self, context, event):
        self._steps = _filtered_steps(CLEANUP_SCAN_STEPS, context.scene)
        return super().invoke(context, event)

    def execute(self, context):
        self._steps = _filtered_steps(CLEANUP_SCAN_STEPS, context.scene)
        return super().execute(context)


def _snapshot_counts() -> dict:
    return {
        "materials": len(bpy.data.materials),
        "meshes": len(bpy.data.meshes),
        "images": len(bpy.data.images),
        "libraries": len(bpy.data.libraries),
    }


def _run_nested(gen, lo: float, hi: float):
    """Drain a nested ``(fraction, status)`` generator, rescaling its own
    0..1 progress into ``[lo, hi]`` of the OUTER generator's range — unlike
    ``ops.analyze_all``'s black-box ``bpy.ops`` dispatch (which can't rescale
    a sub-operator's progress, a known deferred gap per docs/TODO.md #41),
    this calls ``core.resource``'s gather generator directly in-process, so
    it can be rescaled properly."""
    while True:
        try:
            fraction, status = next(gen)
        except StopIteration as done:
            return done.value
        yield (lo + (hi - lo) * fraction, status)


def _build_savings_report(before_counts, before_totals, after_counts, after_totals,
                          backup: str | None) -> Report:
    from ..core.resource import human_bytes

    report = Report(title="Automated Cleanup — Savings Summary", feature="auto")
    ram_delta = before_totals["ram"] - after_totals["ram"]
    vram_delta = before_totals["vram"] - after_totals["vram"]
    deltas = {k: before_counts[k] - after_counts[k] for k in before_counts}

    labels = {"materials": "material(s)", "meshes": "mesh(es)", "images": "image(s)",
             "libraries": "librar(y/ies)"}
    bits = [f"{deltas[k]} {labels[k]}" for k in labels if deltas[k]]
    counts_msg = ("Removed " + ", ".join(bits)) if bits else "No datablock count changes"
    sign = "-" if ram_delta >= 0 else "+"
    vsign = "-" if vram_delta >= 0 else "+"
    ram_msg = f"est. RAM {sign}{human_bytes(abs(ram_delta))}"
    vram_msg = f"est. VRAM {vsign}{human_bytes(abs(vram_delta))}"
    backup_msg = f"Backup: {backup}" if backup else "(no backup written)"

    report.add(Finding(
        category="overview",
        message=f"{counts_msg}. {ram_msg}, {vram_msg}. {backup_msg}",
        severity="info",
        data={"ram_delta": ram_delta, "vram_delta": vram_delta, **{f"{k}_delta": v
                                                                    for k, v in deltas.items()}},
    ))
    return report


class FILELINK_OT_cleanup_apply_selected(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "filelink.cleanup_apply_selected"
    bl_label = "Automated Cleanup: Apply Selected"
    bl_description = ("Apply every ticked row across the INCLUDED cleanup functions (Make "
                      "Local / Duplicate Materials / Duplicate Geometry / Orphans). One backup "
                      "at the start; a before/after savings summary at the end")
    bl_options = {"REGISTER"}

    _backup = None

    def cancel_message(self) -> str:
        tail = f" Backup: {self._backup}" if self._backup else ""
        return f"Automated Cleanup Apply cancelled.{tail}"

    @classmethod
    def poll(cls, context):
        return bool(_filtered_steps(CLEANUP_APPLY_STEPS, context.scene))

    def run_steps(self, context):
        from ..log import get_logger
        from .report_store import stash_report
        from .resource import _gather_steps
        from .safety import auto_backup
        from ..core.resource_tree import build_resource_tree

        log = get_logger()
        scene = context.scene
        steps = _filtered_steps(CLEANUP_APPLY_STEPS, scene)
        if not steps:
            self.report({"WARNING"}, "Tick \"Include\" for at least one function above")
            return

        yield (0.0, "Backing up…")
        self._backup = backup = auto_backup(context)

        before_items = yield from _run_nested(_gather_steps(context), 0.02, 0.1)
        _, before_totals = build_resource_tree(before_items)
        before_counts = _snapshot_counts()

        n = len(steps)
        errors = 0
        for i, step in enumerate(steps):
            yield (0.1 + 0.65 * i / n, f"Running {step.label}…")
            try:
                _call(step.opname, step.kwargs)
            except Exception as exc:  # one bad step shouldn't stop the rest
                errors += 1
                log.warning("Automated Cleanup Apply: %s failed: %s", step.key, exc)
        yield (0.75, "Applied selected steps")

        after_items = yield from _run_nested(_gather_steps(context), 0.8, 0.9)
        _, after_totals = build_resource_tree(after_items)
        after_counts = _snapshot_counts()

        yield (0.95, "Building savings summary…")
        report = _build_savings_report(before_counts, before_totals, after_counts,
                                       after_totals, backup)
        stash_report(context, report, "auto")

        if scene.filelink_cleanup_save_after:
            if bpy.data.filepath:
                yield (0.98, "Saving…")
                bpy.ops.wm.save_mainfile()
            else:
                log.warning("Automated Cleanup: 'Save file after Apply' skipped — "
                           "file has never been saved")

        yield (1.0, "Done")
        msg = report.findings[0].message
        self.report({"WARNING"} if errors else {"INFO"}, msg)
