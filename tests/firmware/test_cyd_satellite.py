"""CYD satellite firmware on a simulated CC1101: telemetry, commands, security levels."""
import struct

import pytest

from . import mpsim
from .mpsim import Board, run_board

KEY = b"SemaeopusKey_v01"


def _tc(sp, apid, data=b"", seq=1, level=0, nonce=None):
    return sp.encode(sp.TYPE_TC, apid, seq, data, security_level=level,
                     key=KEY if level else None, nonce=nonce)


def _run(staged, plan, steps, level=None):
    b = Board(radio_spi=2, cs=5, gdo0=27)

    def pre():
        if level is not None:
            import config
            config.SECURITY_LEVEL = level

    g = run_board(staged["cyd-satellite"], b, loop_ms=5, max_steps=steps,
                  hook=lambda s: plan[s](b) if s in plan else None, pre=pre)
    return b, g["state"], g


def test_l0_telemetry_commands_and_sensors(staged, sp, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                       # boot_count.txt lands here
    plan = {
        400: lambda b: b.chip.inject(_tc(sp, sp.APID_PING, b"hello")),
        800: lambda b: b.chip.inject(_tc(sp, sp.APID_REQ_TLM, bytes([sp.APID_EPS_TLM]))),
        1200: lambda b: b.chip.inject(_tc(sp, sp.APID_FORCE_SAFE)),
        1400: lambda b: b.chip.inject(b"\x05\x01\x02\x03\x04\x05"),
        1600: lambda b: b.chip.inject(_tc(sp, sp.APID_SET_MODE, bytes([2]))),   # SAFE -> PAYLOAD: illegal
        1700: lambda b: setattr(b, "adc", 2000),
        1750: lambda b: setattr(b, "adc", 60000),
        1800: lambda b: b.irqs[0](None),                                          # BOOT: tumble
    }
    b, st, g = _run(staged, plan, 2600)
    assert b.radio_pins == (18, 23, 19)
    assert abs(b.chip.freq_hz() - 915e6) < 100 and b.chip.patable == 0x8E
    dec = [sp.decode(f) for f in b.chip.sent]
    apids = {d["apid"] for d in dec}
    assert {sp.APID_BEACON, sp.APID_HK_TLM, sp.APID_ADCS_TLM, sp.APID_EPS_TLM, sp.APID_PONG} <= apids
    assert [d for d in dec if d["apid"] == sp.APID_PONG][0]["user_data"] == b"hello"
    beacons = [d["user_data"].decode() for d in dec if d["apid"] == sp.APID_BEACON]
    assert beacons[0].startswith("SEMAEOPUS-1 M0") and beacons[-1].startswith("SEMAEOPUS-1 M1")
    assert st.mode.current == 1 and st.tc_ok == 4 and st.tc_rejected == 1
    assert any("illegal transition" in e[0] for e in st.events)
    seqs = [d["seq_count"] for d in dec]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    eps = [struct.unpack(">HhHHBBH", d["user_data"])[1] for d in dec if d["apid"] == sp.APID_EPS_TLM]
    assert eps[-1] < 0 < eps[0], "covering the LDR should flip the battery current to discharge"
    adcs = [struct.unpack(">hhhhhhHBB", d["user_data"]) for d in dec if d["apid"] == sp.APID_ADCS_TLM]
    assert any(a[7] for a in adcs[-4:]), "BOOT press should report tumbling"
    assert any(v[0].startswith("SAFE") for v in g["screen"]._cache.values())


def test_l2_rejects_unauthenticated_and_replayed(staged, sp, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    good = _tc(sp, sp.APID_FORCE_SAFE, level=2, nonce=(1).to_bytes(8, "big"))
    plan = {
        300: lambda b: b.chip.inject(_tc(sp, sp.APID_PING, b"x")),
        500: lambda b: b.chip.inject(good),
        700: lambda b: b.chip.inject(good),
        900: lambda b: b.chip.inject(_tc(sp, sp.APID_PING, b"yo", level=2, nonce=(2).to_bytes(8, "big"))),
    }
    b, st, _ = _run(staged, plan, 1200, level=2)
    ev = [e[0] for e in st.events]
    assert st.mode.current == 1 and st.tc_ok == 2 and st.tc_rejected == 2
    assert any("bad HMAC" in e for e in ev) and any("replayed nonce" in e for e in ev)
    assert all(sp.decode(f, 2, KEY)["auth_ok"] for f in b.chip.sent)


def test_l3_encrypts_on_air(staged, sp, tmp_path, monkeypatch):
    pytest.importorskip("Crypto")
    monkeypatch.chdir(tmp_path)
    plan = {300: lambda b: b.chip.inject(_tc(sp, sp.APID_PING, b"sec", level=3, nonce=(9).to_bytes(8, "big")))}
    b, st, _ = _run(staged, plan, 600, level=3)
    tm = [sp.decode(f, 3, KEY) for f in b.chip.sent]
    pong = [d for d in tm if d["apid"] == sp.APID_PONG]
    assert pong and pong[0]["user_data"] == b"sec" and pong[0]["auth_ok"]
    beacon = [f for f, d in zip(b.chip.sent, tm) if d["apid"] == sp.APID_BEACON][0]
    assert b"SEMAEOPUS" not in beacon


def test_commands_arriving_during_telemetry_are_not_lost(staged, sp, tmp_path, monkeypatch):
    import random
    monkeypatch.chdir(tmp_path)
    rnd = random.Random(7)
    steps = sorted(rnd.sample(range(100, 3800), 25))
    frames = {s: _tc(sp, sp.APID_PING, b"p%02d" % i, seq=i) for i, s in enumerate(steps)}
    plan = {s: (lambda f: lambda b: b.chip.inject(f))(f) for s, f in frames.items()}
    b, st, _ = _run(staged, plan, 4000)
    pongs = sum(1 for f in b.chip.sent if sp.decode(f)["apid"] == sp.APID_PONG)
    assert st.tc_ok == len(steps) == pongs and st.tc_rejected == 0
