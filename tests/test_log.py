"""Unit tests for the logging module (bpy-free path)."""

import logging

import log as adlog  # repo root is on sys.path (see conftest)


def test_debug_log_path_next_to_blend():
    p = adlog.debug_log_path("/proj/scene.blend")
    assert p.replace("\\", "/").endswith("/proj/FileLinkDebugLog.txt")


def test_get_logger_is_singleton_with_console():
    a = adlog.get_logger()
    b = adlog.get_logger()
    assert a is b
    assert any(isinstance(h, logging.StreamHandler) for h in a.handlers)


def test_enable_disable_writes_file(tmp_path):
    blend = tmp_path / "scene.blend"
    path = adlog.set_debug_enabled(True, str(blend))
    try:
        assert path is not None
        adlog.get_logger().info("hello-debug")
        assert (tmp_path / "FileLinkDebugLog.txt").is_file()
        assert "Debug log enabled" in (tmp_path / "FileLinkDebugLog.txt").read_text(encoding="utf-8")
    finally:
        adlog.set_debug_enabled(False)
    # Disabling detaches the file handler.
    assert all(
        not isinstance(h, logging.FileHandler) for h in adlog.get_logger().handlers
    )
