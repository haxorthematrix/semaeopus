"""
Synthesize a complex baseband recording of one or more CC1101-style
frames as a `.cu8` IQ file. The output is byte-compatible with what
`rtl_sdr` writes — interleaved unsigned-8-bit I and Q samples — so the
file can be opened in inspectrum, gqrx (Raw I/Q file source), or GNU
Radio's File Source block.

Modulation: 2-GFSK matching Semaeopus defaults
    - bit rate  = 9600 bps
    - deviation = ±4.8 kHz (h = 1, "FSK with index 1")
    - Gaussian shaping, BT = 0.5
    - centre offset = 0 Hz baseband (replay through SDR if you want a
      different RF centre, or use the SDR's tune offset)

Usage:
    python -m tools.generate_iq \
        --out captures/baseline.iq \
        --sample-rate 1000000 \
        --duration 12 \
        --gap-ms 500 \
        --seed 42

This dumps a sequence of synthetic Semaeopus frames (beacon, HK,
ADCS, EPS), each preceded by 32-bit preamble + 16-bit sync. The
companion file `captures/baseline.jsonl` is what the frames decode
to — useful as an oracle for L03 / L04.
"""

import argparse
import json
import math
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from protocol import space_packet as sp


# ---------------------------------------------------------------------------
# Bitstream construction
# ---------------------------------------------------------------------------

PREAMBLE = b"\xAA\xAA\xAA\xAA"
SYNC     = b"\xD3\x91"


def bytes_to_bits(buf):
    out = []
    for b in buf:
        for i in range(7, -1, -1):
            out.append((b >> i) & 1)
    return out


def make_frame_bits(space_packet_frame):
    """The CC1101 hardware sends preamble + sync + payload bits over
    the air. `space_packet_frame` already has the length byte and CRC,
    so we just prepend preamble + sync."""
    return bytes_to_bits(PREAMBLE + SYNC + space_packet_frame)


# ---------------------------------------------------------------------------
# Gaussian filter
# ---------------------------------------------------------------------------

def gaussian_filter(bt, sps, span=4):
    """Return a Gaussian pulse, normalised to unit area, sampled at
    ``sps`` samples-per-symbol, total length = ``span * sps + 1``."""
    n = span * sps + 1
    t = [(i - n / 2) / sps for i in range(n)]
    alpha = math.sqrt(math.log(2) / 2) / bt
    h = [math.exp(-(ti * ti) / (2 * alpha * alpha)) for ti in t]
    s = sum(h)
    return [x / s for x in h]


def convolve(signal, kernel):
    klen = len(kernel)
    out = [0.0] * (len(signal) + klen - 1)
    for i, x in enumerate(signal):
        for k, hk in enumerate(kernel):
            out[i + k] += x * hk
    return out


# ---------------------------------------------------------------------------
# 2-GFSK modulator
# ---------------------------------------------------------------------------

def modulate_gfsk(bits, sample_rate, bit_rate, deviation, bt=0.5):
    """Return interleaved (I, Q) as a list of floats in [-1, 1]."""
    sps = sample_rate / bit_rate
    sps_int = int(round(sps))
    # Step 1: NRZ symbols (±1) upsampled to sps samples per bit.
    nrz = []
    for b in bits:
        s = 1.0 if b else -1.0
        nrz.extend([s] * sps_int)
    # Step 2: convolve with Gaussian filter.
    g = gaussian_filter(bt, sps_int, span=4)
    shaped = convolve(nrz, g)
    # Step 3: integrate to get phase, with frequency = deviation * shaped.
    phase = 0.0
    dt = 1.0 / sample_rate
    iq = []
    for x in shaped:
        phase += 2 * math.pi * deviation * x * dt
        iq.append(math.cos(phase))
        iq.append(math.sin(phase))
    return iq


def write_cu8(path, iq, gain=0.7):
    """Write interleaved I,Q as unsigned 8-bit (rtl_sdr compatible)."""
    buf = bytearray(len(iq))
    for i, v in enumerate(iq):
        s = max(-1.0, min(1.0, v * gain))
        buf[i] = max(0, min(255, int(round(127.5 + s * 127.5))))
    with open(path, "wb") as fp:
        fp.write(buf)


# ---------------------------------------------------------------------------
# Synthetic Semaeopus frame sequence
# ---------------------------------------------------------------------------

def synth_session(seed=42):
    """Produce a plausible 12 s session: beacon, HK, ADCS, EPS — much
    like what virtual_satellite.py emits — but deterministic so the
    `.iq` file is reproducible."""
    import random
    rng = random.Random(seed)
    frames = []      # list of (label, on_wire_bytes, decoded_dict)
    seq = 0

    def tm(apid, payload, label):
        nonlocal seq
        seq = (seq + 1) & 0x3FFF
        frame = sp.encode(sp.TYPE_TM, apid, seq, payload)
        frames.append((label, frame, {
            "apid": apid,
            "seq":  seq,
            "user_data": payload.hex(),
        }))

    # t = 0: beacon
    tm(sp.APID_BEACON, b"SEMAEOPUS-1 M0 B1 U0 SOC60", "BEACON")
    # t = 0: HK / ADCS / EPS
    tm(sp.APID_HK_TLM, struct.pack(">IHhHHBBH", 0, 1, int(22.3 * 256), 1013, int(41.0 * 256), 0, 0, 0), "HK")
    tm(sp.APID_ADCS_TLM, struct.pack(">hhhhhhHBB", 30, -10, 5, 30, 10, 1010, 0, 0, 0), "ADCS")
    tm(sp.APID_EPS_TLM, struct.pack(">HhHHBBH", 3700, 35, 3700, 35, 60, 1, 0), "EPS")
    # t ≈ 2 s, 4 s, 6 s, 8 s: ADCS
    for k in range(4):
        gx = int(rng.uniform(-50, 50))
        gy = int(rng.uniform(-50, 50))
        gz = int(rng.uniform(-50, 50))
        tm(sp.APID_ADCS_TLM,
           struct.pack(">hhhhhhHBB", gx, gy, gz, 30, 10, 1010, 0, 0, 0),
           "ADCS")
    # t ≈ 5 s: HK + EPS
    tm(sp.APID_HK_TLM, struct.pack(">IHhHHBBH", 5000, 1, int(22.4 * 256), 1013, int(41.2 * 256), 0, 0, 0), "HK")
    tm(sp.APID_EPS_TLM, struct.pack(">HhHHBBH", 3705, 33, 3705, 33, 60, 1, 0), "EPS")
    # t = 10 s: beacon
    tm(sp.APID_BEACON, b"SEMAEOPUS-1 M0 B1 U10 SOC60", "BEACON")
    return frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="captures/baseline.iq")
    ap.add_argument("--jsonl-out", default="captures/baseline.jsonl")
    ap.add_argument("--sample-rate", type=int, default=1_000_000)
    ap.add_argument("--bit-rate", type=int, default=9600)
    ap.add_argument("--deviation", type=int, default=4800)
    ap.add_argument("--bt", type=float, default=0.5)
    ap.add_argument("--gap-ms", type=int, default=200,
                    help="silence between consecutive frames")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    frames = synth_session(args.seed)
    print("synth_session: %d frames" % len(frames))

    samples_per_gap = int(args.sample_rate * args.gap_ms / 1000)
    silence = [0.0] * (samples_per_gap * 2)

    iq = list(silence)
    for label, on_wire, _ in frames:
        bits = make_frame_bits(on_wire)
        iq.extend(modulate_gfsk(bits,
                                args.sample_rate, args.bit_rate,
                                args.deviation, args.bt))
        iq.extend(silence)

    write_cu8(args.out, iq)
    print("wrote %s : %.1f MB IQ, %.2f s" % (
        args.out, os.path.getsize(args.out) / 1e6,
        len(iq) / 2 / args.sample_rate))

    with open(args.jsonl_out, "w") as fp:
        ts0 = time.time()
        for i, (label, on_wire, dec) in enumerate(frames):
            rec = {
                "ts":    ts0 + i * 0.2,
                "rssi":  -45,
                "lqi":   120,
                "frame": on_wire.hex(),
                "label": label,
                "decoded": dec,
            }
            fp.write(json.dumps(rec) + "\n")
    print("wrote %s" % args.jsonl_out)


if __name__ == "__main__":
    main()
