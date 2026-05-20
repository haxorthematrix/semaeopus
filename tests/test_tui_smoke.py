"""Smoke test for the textual operator TUI — verify it imports and the
app class wires up without errors."""

import pytest


def test_tui_imports():
    try:
        from groundstation.operator import tui   # noqa: F401
    except ImportError as e:
        pytest.skip(f"textual/rich not installed: {e}")
    assert hasattr(tui, "OperatorApp")
    assert hasattr(tui, "OperatorState")


def test_operator_state_nonce_monotonic():
    try:
        from groundstation.operator.tui import OperatorState
    except ImportError:
        pytest.skip("textual/rich not installed")
    s = OperatorState()
    a = s.next_nonce()
    s.last_nonce = a
    b = s.next_nonce()
    assert b > a
    assert len(a) == 8 and len(b) == 8
