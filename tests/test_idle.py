"""Unit tests for Batch E: core.idle (idle-scan feasibility prototype)."""

import sys

from core import idle


def test_is_idle_true_once_threshold_reached():
    assert idle.is_idle(120.0, 120.0) is True
    assert idle.is_idle(121.0, 120.0) is True


def test_is_idle_false_below_threshold():
    assert idle.is_idle(119.9, 120.0) is False


def test_is_idle_false_when_unknown():
    # None ("we don't know") must never be treated as idle.
    assert idle.is_idle(None, 0.0) is False


def test_seconds_since_input_non_windows_returns_none(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert idle.seconds_since_input() is None


def test_seconds_since_input_on_this_machine():
    # This dev machine is Windows — the real ctypes call should succeed and
    # report a small non-negative number of seconds (not assert idle/not-idle,
    # since that depends on whoever is at the keyboard right now).
    secs = idle.seconds_since_input()
    if sys.platform == "win32":
        assert secs is not None
        assert secs >= 0.0
    else:
        assert secs is None
