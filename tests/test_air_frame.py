"""tools.air_frame builds frames the way a CC1101 sends them."""
import math
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from protocol import space_packet as sp        # noqa: E402
from tools import air_frame as af              # noqa: E402


def test_cc1101_crc_matches_crc16_cms_check_value():
    # Poly 0x8005, init 0xFFFF, unreflected: catalogued as CRC-16/CMS.
    assert af.crc16_cc1101(b"123456789") == 0xAEE7


def test_air_bytes_layout():
    frame = sp.encode(sp.TYPE_TC, sp.APID_FORCE_SAFE, 1, b"")
    air = af.air_bytes(frame, preamble_bytes=4, pad_bytes=0)
    assert air[:4] == b"\xAA" * 4
    assert air[4:8] == b"\xD3\x91\xD3\x91"
    assert air[8:-2] == frame
    crc = af.crc16_cc1101(frame)
    assert air[-2:] == bytes([crc >> 8, crc & 0xFF])


def test_rejects_frames_the_radio_cannot_send():
    for bad in (b"\x05abc", bytes([62]) + bytes(62)):
        try:
            af.air_bytes(bad)
        except ValueError:
            continue
        raise AssertionError("accepted %r" % bad[:4])


def test_deviation_matches_deviatn_register():
    assert af.DEVIATION_HZ == 20630


def test_gfsk_iq_carries_the_bits():
    bits = af.bits_of(af.air_bytes(sp.encode(sp.TYPE_TC, sp.APID_PING, 3, b"")))
    fs = 96_000                                     # 10 samples per bit
    iq = af.gfsk_iq(bits, fs)
    assert all(abs(math.hypot(iq[k], iq[k + 1]) - 1) < 1e-9 for k in range(0, len(iq), 2))
    phase = [math.atan2(iq[k + 1], iq[k]) for k in range(0, len(iq), 2)]
    got = []
    for b in range(len(bits)):
        i = b * 10 + 5
        d = (phase[i] - phase[i - 1] + math.pi) % (2 * math.pi) - math.pi
        got.append(1 if d > 0 else 0)
    assert got == bits


def test_cli_writes_bytes_and_iq(tmp_path):
    out, iq = tmp_path / "tc.bin", tmp_path / "tc.cs8"
    r = subprocess.run([sys.executable, "-m", "tools.air_frame", "--apid", "FORCE_SAFE",
                        "--out", str(out), "--iq", str(iq), "--repeat", "2"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    data = out.read_bytes()
    assert len(data) == 2 * (8 + 4 + 9 + 2 + 2)
    assert iq.stat().st_size > 0 and iq.stat().st_size % 2 == 0
