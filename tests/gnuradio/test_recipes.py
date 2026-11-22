"""
Run the GNU Radio recipes in groundstation/attacker/gnuradio as scripts,
with the same blocks and parameters the recipes give. Skipped unless
GNU Radio's Python bindings import (they come with the distro package,
for the distro's Python: e.g. `python3.12 -m pytest tests/gnuradio`).
"""
import importlib.util
import math
import os
import sys

import pytest

gr_mod = pytest.importorskip("gnuradio.gr")
np = pytest.importorskip("numpy")
from gnuradio import analog, blocks, digital, filter, gr   # noqa: E402
from gnuradio.filter import firdes                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from protocol import space_packet as sp                   # noqa: E402
from tools import air_frame as af                         # noqa: E402

GR_DIR = os.path.join(ROOT, "groundstation", "attacker", "gnuradio")
SYNC32 = "11010011100100011101001110010001"


def _deframer(**kw):
    spec = importlib.util.spec_from_file_location(
        "semaeopus_deframer", os.path.join(GR_DIR, "semaeopus_deframer.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.blk(**kw)


def _frames():
    import struct
    out = [sp.encode(sp.TYPE_TM, sp.APID_BEACON, i, b"SEMAEOPUS-1 M0 B1 U%d SOC60" % i)
           for i in range(1, 4)]
    out.append(sp.encode(sp.TYPE_TM, sp.APID_HK_TLM, 4,
                         struct.pack(">IHhHHBBH", 0, 1, 5708, 1013, 10496, 0, 0, 0)))
    out.append(sp.encode(sp.TYPE_TC, sp.APID_FORCE_SAFE, 5, b""))
    return out


def _capture(path, fs, lo_offset, cfo, snr_db, seed=1):
    """What an SDR tuned lo_offset below 915 MHz records from a CC1101
    whose crystal puts it cfo Hz off frequency."""
    rng = np.random.default_rng(seed)
    gap = np.zeros(int(0.05 * fs), complex)
    parts = [gap]
    for fr in _frames():
        iq = np.array(af.gfsk_iq(af.bits_of(af.air_bytes(fr, preamble_bytes=4, pad_bytes=0)), fs))
        parts += [iq[0::2] + 1j * iq[1::2], gap]
    x = np.concatenate(parts)
    x = x * np.exp(2j * np.pi * (lo_offset + cfo) * np.arange(len(x)) / fs)
    x = x + 10 ** (-snr_db / 20) / math.sqrt(2) * (
        rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))
    x.astype(np.complex64).tofile(path)


def _rx(path, samp_rate, lo_offset, cfo, deviation, bit_rate, decim, access_code,
        threshold, radio_crc):
    """gfsk_rx_recipe.md, blocks 1-8."""
    tb = gr.top_block()
    src = blocks.file_source(gr.sizeof_gr_complex, path, False)
    chan = samp_rate / decim
    xlat = filter.freq_xlating_fir_filter_ccc(
        decim, firdes.low_pass(1, samp_rate, 40e3, 10e3), lo_offset + cfo, samp_rate)
    qd = analog.quadrature_demod_cf(chan / (2 * math.pi * deviation))
    ss = digital.symbol_sync_ff(digital.TED_ZERO_CROSSING, chan / bit_rate, 0.02, 1.0, 1.0,
                                1.5, 1, digital.constellation_bpsk().base(),
                                digital.IR_MMSE_8TAP, 128, [])
    sl = digital.binary_slicer_fb()
    cac = digital.correlate_access_code_tag_bb(access_code, threshold, "sync")
    d = _deframer(tag_name="sync", radio_crc=radio_crc)
    tb.connect(src, xlat, qd, ss, sl, cac, d)
    tb.run()
    return d.frames_ok


def test_rx_recipe_live_915(tmp_path):
    p = str(tmp_path / "live.cfile")
    fs, lo, cfo = 2e6, 200e3, -9e3
    _capture(p, fs, lo, cfo, snr_db=10)
    ok = _rx(p, fs, lo, cfo, deviation=20630, bit_rate=9600, decim=20,
             access_code=SYNC32, threshold=3, radio_crc=True)
    assert ok >= len(_frames()) - 1


def test_rx_recipe_synthetic_baseline(tmp_path):
    import subprocess
    iq, jl, cf = tmp_path / "b.iq", tmp_path / "b.jsonl", tmp_path / "b.cfile"
    subprocess.run([sys.executable, "-m", "tools.generate_iq", "--out", str(iq),
                    "--jsonl-out", str(jl)], cwd=ROOT, check=True, capture_output=True)
    subprocess.run([sys.executable, "-m", "tools.cu8_to_cfile", str(iq), str(cf)],
                   cwd=ROOT, check=True, capture_output=True)
    ok = _rx(str(cf), 1e6, 0, 0, deviation=4800, bit_rate=1e6 / 104, decim=10,
             access_code="1101001110010001", threshold=2, radio_crc=False)
    assert ok >= 10                                 # of 11


def test_tx_recipe_produces_what_the_rx_recipe_and_a_cc1101_expect(tmp_path):
    """gfsk_tx_recipe.md with a File Sink in place of the HackRF."""
    frame = sp.encode(sp.TYPE_TC, sp.APID_FORCE_SAFE, 1, b"")
    air = af.air_bytes(frame) * 2
    src_path, out_path = str(tmp_path / "tc_air.bin"), str(tmp_path / "tx.cfile")
    open(src_path, "wb").write(air)
    samp_rate, bit_rate, deviation = 2.016e6, 9600, 20630
    tb = gr.top_block()
    tb.connect(blocks.file_source(gr.sizeof_char, src_path, False),
               digital.gfsk_mod(int(samp_rate / bit_rate),
                                2 * math.pi * deviation / samp_rate, 0.5, False, False, True),
               blocks.multiply_const_cc(0.7),
               blocks.file_sink(gr.sizeof_gr_complex, out_path))
    tb.run()
    x = np.fromfile(out_path, np.complex64)
    f = np.angle(x[1:] * np.conj(x[:-1])) * samp_rate / (2 * np.pi)
    want = np.unpackbits(np.frombuffer(air, np.uint8))
    best = min(int(np.sum((f[ph::210][lag:lag + len(want) - 8] > 0) != want[:len(want) - 8]))
               for ph in range(0, 210, 15) for lag in range(4))
    assert best == 0
    assert abs(np.percentile(np.abs(f), 99) - deviation) < 500

    # and the RX recipe decodes it
    lo = 200e3
    y = np.concatenate([np.zeros(100000), x, np.zeros(100000)])
    y = y * np.exp(2j * np.pi * lo * np.arange(len(y)) / samp_rate)
    rx_path = str(tmp_path / "rx.cfile")
    y.astype(np.complex64).tofile(rx_path)
    ok = _rx(rx_path, samp_rate, lo, 0, deviation=20630, bit_rate=9600, decim=20,
             access_code=SYNC32, threshold=3, radio_crc=True)
    assert ok == 2
