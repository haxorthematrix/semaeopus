"""CYD ground station and Pico modem: line protocol, retune, BW/PWR, error handling, RX path."""
import re

import pytest

from .mpsim import Board, run_board

RX_RE = re.compile(r"^RX\s+([0-9a-fA-F]+)\s+RSSI=(-?\d+)\s+LQI=(\d+)\s*$")   # as in groundstation/shared/link.py
BOARDS = {"cyd-ground": dict(radio_spi=2, cs=5, gdo0=27, pins=(18, 23, 19)),
          "pico-modem": dict(radio_spi=0, cs=13, gdo0=10, pins=(18, 19, 16))}


def _feed(board, line):
    board.stdin.extend(list(line + "\n"))


@pytest.mark.parametrize("target", sorted(BOARDS))
def test_modem_protocol(staged, sp, target):
    cfg = BOARDS[target]
    b = Board(cfg["radio_spi"], cfg["cs"], cfg["gdo0"])
    beacon = sp.encode(sp.TYPE_TM, sp.APID_BEACON, 7, b"SEMAEOPUS-1 M0 B3 U42 SOC60")
    safe = sp.encode(sp.TYPE_TC, sp.APID_FORCE_SAFE, 1, b"")
    plan = {
        5: [lambda: _feed(b, "PING")],
        20: [lambda: b.chip.inject(beacon, rssi_dbm=-48, lqi=22)],
        40: [lambda: _feed(b, "CFG 915000000 d391 9600")],
        60: [lambda: _feed(b, "BW 100000")],
        80: [lambda: _feed(b, "PWR -10")],
        100: [lambda: _feed(b, "TX " + safe.hex())],
        104: [lambda: b.chip.inject(beacon)],
        130: [lambda: _feed(b, "TX " + safe.hex())],
        140: [lambda: _feed(b, "TX 0501020304")],
        160: [lambda: _feed(b, "TX " + bytes([69] + [0] * 69).hex())],
        180: [lambda: _feed(b, "CFG 433920000 d391 9600")],
        200: [lambda: _feed(b, "CFG 2400000000 d391 9600")],
        220: [lambda: _feed(b, "NOPE")],
    }
    g = run_board(staged[target], b, loop_ms=2, max_steps=260,
                  hook=lambda s: [f() for f in plan.get(s, [])])
    out = b.stdout.getvalue().splitlines()
    rx = [m for m in (RX_RE.match(l) for l in out) if m]
    assert b.radio_pins == cfg["pins"]
    assert out[0].startswith("EVT semaeopus-") and "ready 915000000" in out[0]
    assert any(l.startswith("PONG ") for l in out)
    assert len(rx) == 2 and bytes.fromhex(rx[0].group(1)) == beacon and rx[0].group(2) == "-48"
    assert b.chip.sent == [safe, safe]
    assert (b.chip.regs[0x10] >> 4) != 0xF                      # BW changed CHANBW
    assert b.chip.patable == 0x34                               # PWR -10 on the 433 MHz table
    assert sum(l.startswith("ERR tx:") for l in out) == 2
    assert any("outside 902-928" in l for l in out) and "ERR unknown NOPE" in out
    if target == "cyd-ground":
        shown = [v[0] for v in g["screen"]._cache.values()]
        assert any("TM BEACON" in s for s in shown)
        assert any(s.startswith("SEMAEOPUS-1 M0") for s in shown)


@pytest.mark.parametrize("target", sorted(BOARDS))
def test_modem_keeps_listening_between_packets(staged, sp, target):
    """Regression: the old driver read packets before they had fully arrived
    (bad CRC) and never re-entered RX afterwards, so it went deaf."""
    cfg = BOARDS[target]
    b = Board(cfg["radio_spi"], cfg["cs"], cfg["gdo0"])
    beacons = [sp.encode(sp.TYPE_TM, sp.APID_BEACON, i, b"SEMAEOPUS-1 M0 B1 U%d SOC60" % i) for i in range(8)]
    plan = {40 + 50 * i: f for i, f in enumerate(beacons)}
    run_board(staged[target], b, loop_ms=2, max_steps=500,
              hook=lambda s: b.chip.inject(plan[s]) if s in plan else None)
    got = [bytes.fromhex(m.group(1)) for m in (RX_RE.match(l) for l in b.stdout.getvalue().splitlines()) if m]
    assert got == beacons
