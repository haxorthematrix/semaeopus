"""
End-to-end simulator test.

Spawns the virtual satellite as a subprocess, attaches a SimLink as
"attacker", injects a FORCE_SAFE TC, and verifies:
  - The satellite acknowledged with EVENT 00 OK
  - The next beacon shows mode = SAFE (M1)

Uses a non-default multicast port so the test doesn't collide with a
real `sim/virtual_satellite` the developer might have running locally.
"""

import os
import signal
import subprocess
import sys
import time

import pytest

from protocol import space_packet as sp
from sim.sim_link import SimLink


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def isolated_bus(monkeypatch):
    """Pick a random-ish multicast port so concurrent test runs don't
    cross-contaminate."""
    port = 53400 + (os.getpid() % 50)
    monkeypatch.setenv("SEMAEOPUS_PORT", str(port))
    return port


@pytest.fixture
def virtual_sat(isolated_bus):
    env = os.environ.copy()
    env["SEMAEOPUS_PORT"] = str(isolated_bus)
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "sim.virtual_satellite",
         "--node-id", "TSAT", "--security", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        cwd=ROOT, env=env,
    )
    time.sleep(1.5)
    yield proc
    proc.send_signal(signal.SIGTERM)
    try:
        proc.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()


def _collect_for(link, seconds):
    """Drain SimLink for ``seconds``, return decoded packet dicts."""
    out = []
    deadline = time.time() + seconds
    while time.time() < deadline:
        rx = link.rx_packets()
        if rx is None:
            time.sleep(0.02)
            continue
        try:
            d = sp.decode(rx["frame"])
        except sp.DecodeError:
            continue
        d["rssi"] = rx["rssi"]
        out.append(d)
    return out


def test_telemetry_is_transmitted(virtual_sat):
    # ADCS cadence is 2 s, so we should always see at least one frame
    # of any kind within 4 s of attaching.
    link = SimLink(node_id="TGS0")
    try:
        seen = _collect_for(link, 4.0)
        assert seen, "no frames received in 4 s — sim radio not transmitting?"
        # At minimum we expect ADCS_TLM (2 s cadence) within the window.
        apids = {p["apid"] for p in seen}
        assert sp.APID_ADCS_TLM in apids, \
            "expected ADCS_TLM frames; got %r" % apids
    finally:
        link.close()


def test_force_safe_injection_changes_mode(virtual_sat):
    link = SimLink(node_id="TATK")
    try:
        # Wait long enough to be sure the sim is alive — see at least
        # one ADCS frame.
        seen = _collect_for(link, 3.0)
        assert seen, "sim not transmitting before injection"

        # Inject FORCE_SAFE
        frame = sp.encode(sp.TYPE_TC, sp.APID_FORCE_SAFE, 1, b"")
        link.send_tx(frame)

        # Wait for the EVENT response + the next beacon (every 10 s).
        seen = _collect_for(link, 12.0)
        events = [p for p in seen if p["apid"] == sp.APID_EVENT]
        assert any(p["user_data"].startswith(b"\x00OK") for p in events), \
            "satellite should ACK with EVENT 00 OK"
        beacons = [p for p in seen if p["apid"] == sp.APID_BEACON]
        assert beacons, "no beacons after injection (waited 12 s)"
        assert b" M1 " in beacons[-1]["user_data"], \
            "satellite should be in SAFE mode after FORCE_SAFE; saw %r" \
            % beacons[-1]["user_data"]
    finally:
        link.close()
