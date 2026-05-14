"""Tests for the satellite TC dispatcher in firmware/satellite/comms/handlers.py."""

import types

import pytest

from obc.modes import ModeState
from comms.handlers import dispatch
from protocol import space_packet as sp


def _state():
    s = types.SimpleNamespace()
    s.boot_count = 1
    s.mode = ModeState(ModeState.NOMINAL)
    s.session_key = b"\x00" * 16
    s.tx_seq = 0
    # Stub the sensor objects — only used by REQ_TLM, which we test
    # separately with a tailored fake.
    s.housekeeping = types.SimpleNamespace(encode=lambda: b"hk")
    s.adcs         = types.SimpleNamespace(encode=lambda: b"adcs")
    s.eps          = types.SimpleNamespace(encode=lambda: b"eps")
    s.rtc          = types.SimpleNamespace(set_epoch=lambda e: None)
    return s


def test_ping_echoes_first_8_bytes():
    s = _state()
    apid, body = dispatch(s, sp.APID_PING, b"abcdefghIGNORED")
    assert apid == sp.APID_PONG
    assert body == b"abcdefgh"


def test_force_safe_drops_to_safe_mode():
    s = _state()
    apid, body = dispatch(s, sp.APID_FORCE_SAFE, b"")
    assert apid == sp.APID_EVENT
    assert body == b"\x00OK"
    assert s.mode.current == ModeState.SAFE


def test_arm_then_fire_succeeds_in_nominal():
    s = _state()
    apid, body = dispatch(s, sp.APID_ARM_PAYLOAD, b"")
    assert body == b"\x00OK"
    apid, body = dispatch(s, sp.APID_FIRE_PAYLOAD, b"")
    assert apid == sp.APID_PAYLOAD_DATA
    assert body.startswith(b"IMG")


def test_fire_without_arm_fails():
    s = _state()
    apid, body = dispatch(s, sp.APID_FIRE_PAYLOAD, b"")
    assert apid == sp.APID_EVENT
    assert body.startswith(b"\x01")     # error byte


def test_set_mode_illegal_transition():
    s = _state()
    s.mode = ModeState(ModeState.SAFE)
    # SAFE → PAYLOAD is not in the legal set.
    apid, body = dispatch(s, sp.APID_SET_MODE, bytes([ModeState.PAYLOAD]))
    assert apid == sp.APID_EVENT
    assert body.startswith(b"\x01")


def test_set_mode_legal_transition():
    s = _state()
    apid, body = dispatch(s, sp.APID_SET_MODE, bytes([ModeState.SAFE]))
    assert body == b"\x00OK"
    assert s.mode.current == ModeState.SAFE


def test_unknown_apid_returns_error():
    s = _state()
    apid, body = dispatch(s, 0x123, b"")
    assert apid == sp.APID_EVENT
    assert body.startswith(b"\x01")


def test_key_rotate_requires_16_bytes():
    s = _state()
    # short
    apid, body = dispatch(s, sp.APID_KEY_ROTATE, b"\x00" * 15)
    assert body.startswith(b"\x01")
    # correct
    apid, body = dispatch(s, sp.APID_KEY_ROTATE, b"\xAA" * 16)
    assert body == b"\x00OK"
    assert s.session_key == b"\xAA" * 16
