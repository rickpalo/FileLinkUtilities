"""Shared live-progress plumbing for AssetDoctor's modal operators.

One set of WindowManager props (`assetdoctor_op_active/_progress/_status`,
registered in the package ``register()``) backs a single progress bar drawn at
the top of the N-panel. Any modal operator (F1 folder scan, F2 make-local, …)
calls :func:`set_progress` per timer tick to drive it, and :func:`clear_progress`
when it finishes or cancels.

:class:`ModalProgressMixin` packages the whole pattern: a subclass provides a
``run_steps(context)`` generator that yields ``(fraction, status)`` as it works;
the mixin runs it modally (progress bar + ESC) or synchronously via ``execute``.
"""

from __future__ import annotations

import time


def set_progress(context, fraction: float = 0.0, status: str = "") -> None:
    """Show/update the shared progress bar and repaint the sidebar."""
    wm = context.window_manager
    wm.assetdoctor_op_active = True
    wm.assetdoctor_op_progress = max(0.0, min(1.0, fraction))
    wm.assetdoctor_op_status = status
    if context.area is not None:
        context.area.tag_redraw()


def clear_progress(context) -> None:
    """Hide the shared progress bar."""
    wm = context.window_manager
    wm.assetdoctor_op_active = False
    wm.assetdoctor_op_progress = 0.0
    wm.assetdoctor_op_status = ""
    wm.assetdoctor_op_paused = False
    wm.assetdoctor_op_cancel = False
    if context.area is not None:
        context.area.tag_redraw()


class ModalProgressMixin:
    """Run ``self.run_steps(context)`` as a modal operator with the shared
    progress bar + ESC cancel, or synchronously via ``execute``.

    Subclasses implement ``run_steps(context)`` as a generator that yields
    ``(fraction, status)`` while it works and performs all side effects itself
    (build/stash the report, apply mutations, and the final ``self.report(...)``).

    The modal pulls as many steps as fit in a per-tick **time budget**, so fast
    per-item work (e.g. fingerprinting) still finishes near-instantly while the UI
    stays responsive and ESC stays live; a single slow step (e.g. one make-local)
    naturally becomes one step per tick. ``execute`` just drains the generator,
    which keeps the EXEC_DEFAULT / scripting / headless-test path synchronous.
    """

    # Seconds of work to do per timer tick before yielding back to Blender.
    _PROGRESS_BUDGET = 0.04

    _timer = None
    _gen = None
    _last = (0.0, "")  # most recent (fraction, status), shown while paused
    _was_paused = False  # true for one tick after resume, to clear the paused text

    def run_steps(self, context):  # pragma: no cover - subclass responsibility
        raise NotImplementedError
        yield  # noqa: F811 - marks this as a generator for subclasses

    def cancel_message(self) -> str:
        return f"{self.bl_label} cancelled"

    def execute(self, context):
        for _ in self.run_steps(context):
            pass
        return {"FINISHED"}

    def invoke(self, context, event):
        self._gen = self.run_steps(context)
        self._last = (0.0, "Starting…")
        self._was_paused = False
        wm = context.window_manager
        wm.assetdoctor_op_paused = False
        wm.assetdoctor_op_cancel = False
        wm.progress_begin(0, 100)
        set_progress(context, 0.0, "Starting…")
        context.workspace.status_text_set(f"AssetDoctor: {self.bl_label}… (ESC to cancel)")
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            self._teardown(context)
            self.report({"WARNING"}, self.cancel_message())
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        # Cancel requested from the panel's Cancel button (works even while paused).
        if context.window_manager.assetdoctor_op_cancel:
            self._teardown(context)
            self.report({"WARNING"}, self.cancel_message())
            return {"CANCELLED"}

        # Paused: hold here without advancing the generator (ESC still cancels).
        if context.window_manager.assetdoctor_op_paused:
            frac, status = self._last
            set_progress(context, frac, f"⏸ Paused — {status}")
            self._was_paused = True
            return {"RUNNING_MODAL"}

        # Just resumed: repaint the clean status this tick BEFORE the next step,
        # which may block (a multi-GB read), so "Paused…" doesn't linger.
        if self._was_paused:
            self._was_paused = False
            frac, status = self._last
            set_progress(context, frac, status)
            return {"RUNNING_MODAL"}

        latest = None
        start = time.perf_counter()
        try:
            while True:
                latest = next(self._gen)
                if time.perf_counter() - start >= self._PROGRESS_BUDGET:
                    break
        except StopIteration:
            self._teardown(context)
            return {"FINISHED"}

        fraction, status = latest
        self._last = latest
        context.window_manager.progress_update(int(fraction * 100))
        set_progress(context, fraction, status)
        return {"RUNNING_MODAL"}

    def _teardown(self, context):
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        wm.progress_end()
        clear_progress(context)
        context.workspace.status_text_set(None)


import bpy  # noqa: E402 - operators below need bpy; helpers above stay bpy-light


class ASSETDOCTOR_OT_toggle_pause(bpy.types.Operator):
    """Pause or resume the running AssetDoctor operation (it holds between steps;
    ESC still cancels). Useful for long recursive scans over multi-GB files."""

    bl_idname = "assetdoctor.toggle_pause"
    bl_label = "Pause/Resume"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        wm = context.window_manager
        wm.assetdoctor_op_paused = not wm.assetdoctor_op_paused
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ASSETDOCTOR_OT_request_cancel(bpy.types.Operator):
    """Cancel the running AssetDoctor operation (same as pressing ESC). The modal
    stops at the next step boundary — a step already in progress (e.g. reading a
    large file) finishes first."""

    bl_idname = "assetdoctor.request_cancel"
    bl_label = "Cancel"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        context.window_manager.assetdoctor_op_cancel = True
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}
