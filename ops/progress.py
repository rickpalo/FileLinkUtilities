"""Shared live-progress plumbing for AssetDoctor's modal operators.

One set of WindowManager props (`assetdoctor_op_active/_progress/_status`,
registered in the package ``register()``) backs a single progress bar drawn at
the top of the N-panel. Any modal operator (F1 folder scan, F2 make-local, …)
calls :func:`set_progress` per timer tick to drive it, and :func:`clear_progress`
when it finishes or cancels.
"""

from __future__ import annotations


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
    if context.area is not None:
        context.area.tag_redraw()
