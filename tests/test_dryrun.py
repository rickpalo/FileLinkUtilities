"""Unit tests for Batch D: core.dryrun (headless dry-run render warnings)."""

from core import dryrun


def test_build_dryrun_script_sets_resolution_and_samples():
    script = dryrun.build_dryrun_script(resolution_percentage=5, samples=2)
    assert "resolution_percentage = 5" in script
    assert "scene.cycles.samples = 2" in script
    assert "scene.eevee.taa_render_samples = 2" in script
    assert "write_still=False" in script


def test_build_dryrun_script_defaults():
    script = dryrun.build_dryrun_script()
    assert f"resolution_percentage = {dryrun.DEFAULT_RESOLUTION_PERCENTAGE}" in script
    assert f"samples = {dryrun.DEFAULT_SAMPLES}" in script


def test_build_dryrun_script_simplify_on_by_default():
    script = dryrun.build_dryrun_script()
    assert "scene.render.use_simplify = True" in script
    assert "simplify_child_particles_render = 0.0" in script
    assert "texture_limit_render" in script
    # Best-effort: a property-name mismatch on some Blender version should
    # no-op, not blow up the dry-run itself.
    assert script.count("except Exception:\n    pass") >= 2


def test_build_dryrun_script_simplify_off():
    script = dryrun.build_dryrun_script(simplify=False)
    assert "use_simplify" not in script
    assert "texture_limit_render" not in script


def test_format_elapsed_seconds_only():
    assert dryrun.format_elapsed(7) == "7s"
    assert dryrun.format_elapsed(59.9) == "60s"


def test_format_elapsed_minutes():
    assert dryrun.format_elapsed(67) == "1m07s"
    assert dryrun.format_elapsed(1800) == "30m00s"


def test_build_dryrun_command_order():
    cmd = dryrun.build_dryrun_command("blender.exe", "C:/scene.blend", "C:/script.py")
    assert cmd == [
        "blender.exe", "--background", "--factory-startup", "C:/scene.blend",
        "--python", "C:/script.py",
    ]


def test_classify_missing_image_phrasing_unable_to_open():
    assert dryrun.classify_line("Error: Unable to open image '/p/tex.png'") == "missing_image"


def test_classify_missing_image_phrasing_not_found():
    assert dryrun.classify_line("Image '/p/tex.png' not found") == "missing_image"


def test_classify_driver_error_needs_error_or_traceback():
    assert dryrun.classify_line("Error: Driver evaluation failed for 'influence'") == "driver_error"
    assert dryrun.classify_line("Driver expression raised a Traceback") == "driver_error"
    assert dryrun.classify_line("Driver target points at a deleted bone") is None  # no error/traceback


def test_classify_generic_error_and_warning():
    assert dryrun.classify_line("Error: No camera") == "render_error"
    assert dryrun.classify_line("Warning: deprecated node socket") == "render_warning"


def test_classify_ignores_plain_lines():
    assert dryrun.classify_line("Fra:1 Mem:12.34M (Peak 20.00M)") is None
    assert dryrun.classify_line("") is None


def test_parse_render_log_empty_is_clean():
    report = dryrun.parse_render_log("Fra:1 Mem:12.34M\nSaved: nothing\n")
    assert report.feature == "f9"
    assert [f.category for f in report.findings] == ["clean"]
    assert report.findings[0].severity == "info"


def test_parse_render_log_dedupes_repeated_lines():
    log = "\n".join(["Error: Unable to open image '/p/tex.png'"] * 3)
    report = dryrun.parse_render_log(log)
    assert len(report.findings) == 1
    assert report.findings[0].category == "missing_image"
    assert report.findings[0].message.endswith("(x3)")


def test_parse_render_log_mixed_severities():
    log = "\n".join([
        "Warning: deprecated node socket",
        "Error: Driver evaluation failed for 'influence'",
        "Image '/p/tex.png' not found",
    ])
    report = dryrun.parse_render_log(log)
    cats = {f.category for f in report.findings}
    assert cats == {"render_warning", "driver_error", "missing_image"}
    assert report.max_severity == "error"


def test_parse_render_log_crash_returncode_flagged_even_with_no_matching_lines():
    # A real Blender crash (e.g. EXCEPTION_ACCESS_VIOLATION) doesn't necessarily
    # print anything matching the error/warning/missing-image patterns — the
    # nonzero exit code is the only signal. Must NOT report "no warnings found".
    report = dryrun.parse_render_log("Fra:1 Mem:12.34M\n", returncode=-1073741819)
    assert report.max_severity == "error"
    assert any(f.category == "process_crash" for f in report.findings)
    assert not any(f.category == "clean" for f in report.findings)


def test_parse_render_log_clean_exit_zero_is_still_clean():
    report = dryrun.parse_render_log("Fra:1 Mem:12.34M\n", returncode=0)
    assert [f.category for f in report.findings] == ["clean"]


def test_parse_render_log_no_returncode_passed_is_unaffected():
    report = dryrun.parse_render_log("Fra:1 Mem:12.34M\n")
    assert [f.category for f in report.findings] == ["clean"]


def test_parse_render_log_crash_with_other_findings_keeps_both():
    log = "Image '/p/tex.png' not found\n"
    report = dryrun.parse_render_log(log, returncode=1)
    cats = {f.category for f in report.findings}
    assert cats == {"process_crash", "missing_image"}
