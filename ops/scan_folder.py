"""F1 - recursively map the link graph across a folder of .blend files.

The interactive path (panel button / folder browser) runs as a **modal**
operator: it processes a time-bounded batch of files per timer tick, updates a
progress bar (WindowManager props shown in the panel + the wait cursor + the
status bar), and can be cancelled with ESC. ``execute`` keeps a synchronous path
for scripting/EXEC_DEFAULT (and the headless tests).
"""

import datetime
import pathlib
import time

import bpy


def _emit(operator, context, scan, root, open_graph=True):
    """Build the report from a finished scan, write exports + the interactive
    graph, open the graph in the browser, log + report."""
    import webbrowser

    from ..core.f1_linkmap import report_from_scan
    from ..core.linkmap_html import build_link_map_html
    from ..log import get_logger

    log = get_logger()
    report = report_from_scan(scan, root)

    from .report_store import stash_report
    stash_report(context, report, "f1")

    out_dir = root / ".filelink"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = out_dir / f"linkmap_{stamp}"
    base.with_suffix(".json").write_text(report.to_json(), encoding="utf-8")
    base.with_suffix(".csv").write_text(report.to_csv(), encoding="utf-8")
    base.with_suffix(".dot").write_text(scan.graph.to_dot(), encoding="utf-8")

    # The graphical output: a self-contained interactive HTML link map, opened in
    # the browser. This is the headline result of a folder scan.
    html_path = base.with_suffix(".html")
    html_path.write_text(
        build_link_map_html(scan, root, title=f"Link map: {root.name or root}"),
        encoding="utf-8",
    )
    if open_graph:
        try:
            webbrowser.open(html_path.as_uri())
        except Exception as exc:  # headless / no browser - the file is still written
            log.warning("Could not open link-map graph: %s", exc)

    log.debug("F1 scan root=%s exports=%s", root, out_dir)
    for f in report.findings:
        log.info("F1 [%s] %s: %s", f.severity, f.category, f.message)

    errors = report.count("error")
    warnings = report.count("warning")
    level = "ERROR" if errors else ("WARNING" if warnings else "INFO")
    operator.report(
        {level},
        f"Mapped {len(scan.graph.nodes)} files ({errors} error(s), "
        f"{warnings} warning(s)). Graph: {html_path.name} in {out_dir}",
    )


class FILELINK_OT_scan_folder(bpy.types.Operator):
    bl_idname = "filelink.scan_folder"
    bl_label = "Scan Folder → Link Graph"
    bl_description = (
        "Recursively map which .blend files in a folder link which (backups "
        "skipped), then open an interactive graph in your browser. Also writes "
        "JSON/CSV/DOT exports beside it. Offline — does not open the files in Blender"
    )
    bl_options = {"REGISTER"}

    directory: bpy.props.StringProperty(subtype="DIR_PATH")  # type: ignore[valid-type]

    # ---- modal state ----
    _timer = None
    _files: list = []
    _index: int = 0
    _result = None
    _root = None

    def _resolve_root(self):
        if not self.directory:
            return None
        root = pathlib.Path(bpy.path.abspath(self.directory))
        return root if root.is_dir() else None

    # Synchronous path (scripting / EXEC_DEFAULT / tests / browser fallback).
    def execute(self, context):
        from ..core.blendscan import bat_available, map_folder

        root = self._resolve_root()
        if root is None:
            self.report({"ERROR"}, "Pick a folder to scan")
            return {"CANCELLED"}
        if not bat_available():
            self.report({"ERROR"}, "Blender Asset Tracer unavailable; reinstall the extension")
            return {"CANCELLED"}
        _emit(self, context, map_folder(root), root)
        return {"FINISHED"}

    def invoke(self, context, event):
        from ..core.blendscan import bat_available, iter_blend_files, new_scan_result

        root = self._resolve_root()
        if root is None:
            context.window_manager.fileselect_add(self)  # let the user pick, then execute()
            return {"RUNNING_MODAL"}
        if not bat_available():
            self.report({"ERROR"}, "Blender Asset Tracer unavailable; reinstall the extension")
            return {"CANCELLED"}

        self._files = list(iter_blend_files(root))
        if not self._files:
            self.report({"INFO"}, "No .blend files found in that folder")
            return {"CANCELLED"}
        self._index = 0
        self._result = new_scan_result()
        self._root = root

        from .progress import set_progress

        wm = context.window_manager
        wm.progress_begin(0, len(self._files))
        set_progress(context, 0.0, f"0 / {len(self._files)} files")
        context.workspace.status_text_set("FileLink: scanning… (ESC to cancel)")
        self._timer = wm.event_timer_add(0.01, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"ESC"}:
            return self._finish(context, cancelled=True)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        from ..core.blendscan import scan_into

        total = len(self._files)
        start = time.perf_counter()
        # Process a time-bounded batch so each tick stays short and the UI breathes.
        while self._index < total and (time.perf_counter() - start) < 0.05:
            scan_into(self._result, self._files[self._index])
            self._index += 1

        from .progress import set_progress

        context.window_manager.progress_update(self._index)
        set_progress(context, self._index / total, f"{self._index} / {total} files")

        if self._index >= total:
            return self._finish(context, cancelled=False)
        return {"RUNNING_MODAL"}

    def _finish(self, context, cancelled):
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        from .progress import clear_progress

        wm.progress_end()
        clear_progress(context)
        context.workspace.status_text_set(None)

        if cancelled:
            self.report({"WARNING"}, f"Scan cancelled at {self._index}/{len(self._files)} files")
            return {"CANCELLED"}
        _emit(self, context, self._result, self._root)
        return {"FINISHED"}
