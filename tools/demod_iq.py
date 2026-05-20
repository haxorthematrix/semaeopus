"""
Reference 2-GFSK demodulator for captures/baseline.iq.

Pure Python — no numpy, no GNU Radio. Reads a `.cu8` file, demodulates
each frame, prints the recovered hex bytes and CRC verdict. Compare
against `captures/baseline.jsonl` (the oracle) to grade your own
GNU Radio flowgraph in L02.

This is *not* a great receiver — no PFB matched filter, no AGC, no
proper symbol-timing recovery. It works at the bench-SNR levels of
the synthetic capture (essentially noise-free). The point is that
the bit stream comes out byte-perfect under good conditions, so
learners can verify their L02/L03 pipelines against a known-good
reference.

Usage:
    python -m tools.demod_iq            # reads captures/baseline.iq
    python -m tools.demod_iq --iq captures/your_capture.cu8

The demodulator chain:
    .cu8 IQ → quadrature demod → integrate-and-dump per symbol →
    sliding sync-word search → length-prefixed framing → CRC check
"""

import argparse
import cmath
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from protocol.space_packet import crc16_ccitt


SYNC_WORD = 0xD391
PREAMBLE  = 0xAA


def read_cu8_complex(path):
    raw = open(path, "rb").read()
    n = (len(raw) // 2) * 2
    iq = [complex((raw[i] - 127.5) / 127.5,
                  (raw[i + 1] - 127.5) / 127.5)
          for i in range(0, n, 2)]
    return iq


def quadrature_demod(iq):
    out = [0.0]
    for n in range(1, len(iq)):
        d = iq[n] * iq[n - 1].conjugate()
        out.append(cmath.phase(d))
    return out


def slice_bits(fd, sample_rate, bit_rate, span=4):
    """Integrate-and-dump per symbol with the GFSK group-delay offset
    from tools/generate_iq.py. Slices *per burst*: finds each
    transmission via an energy detector, then runs the symbol clock
    from the start of that burst until it goes silent again."""
    sps_int = int(round(sample_rate / bit_rate))
    K = span * sps_int + 1
    decision_offset = (K - 1) // 2 + sps_int

    # Energy detector — running magnitude with a low threshold.
    silence_thresh = 0.005   # rad/sample — well below GFSK deviation
    burst_min_gap  = sps_int * 8    # at least 8 silent symbols → new burst

    bursts = []          # list of (start_idx, end_idx) into fd
    in_burst = False
    burst_start = 0
    silent_since = 0
    for n in range(len(fd)):
        if abs(fd[n]) > silence_thresh:
            if not in_burst:
                in_burst = True
                burst_start = max(0, n - sps_int)   # back up half a symbol
            silent_since = 0
        else:
            silent_since += 1
            if in_burst and silent_since > burst_min_gap:
                bursts.append((burst_start, n - silent_since))
                in_burst = False
    if in_burst:
        bursts.append((burst_start, len(fd)))

    # Slice each burst into bits using the symbol clock anchored at
    # burst start + decision_offset.
    all_bits = []
    burst_bit_starts = []
    for (s, e) in bursts:
        burst_bit_starts.append(len(all_bits))
        k = 0
        while True:
            si = s + decision_offset + k * sps_int
            ei = si + sps_int
            if ei > e or ei > len(fd):
                break
            acc = sum(fd[si:ei])
            all_bits.append(1 if acc > 0 else 0)
            k += 1
    return all_bits, burst_bit_starts


def bits_to_bytes_at(bits, start):
    """Pack bits[start:] into a byte string until exhausted."""
    out = bytearray()
    for i in range(start, len(bits) - 7, 8):
        b = 0
        for j in range(8):
            b = (b << 1) | bits[i + j]
        out.append(b)
    return bytes(out)


def _popcount(x):
    c = 0
    while x:
        x &= x - 1
        c += 1
    return c


def search_sync(bits, sync_word=SYNC_WORD, span_bits=16, max_errors=2):
    """Yield bit-positions where `sync_word` appears (Hamming distance
    ≤ max_errors). GFSK ISI at the preamble→sync transition routinely
    flips 1–3 bits in a naive demod; the sync correlator absorbs this
    so we don't lose every frame."""
    target = sync_word & ((1 << span_bits) - 1)
    n = len(bits)
    word = 0
    mask = (1 << span_bits) - 1
    for i in range(span_bits):
        word = ((word << 1) | bits[i]) & mask
    if _popcount(word ^ target) <= max_errors:
        yield 0
    for i in range(span_bits, n):
        word = ((word << 1) | bits[i]) & mask
        if _popcount(word ^ target) <= max_errors:
            yield i - span_bits + 1


def deframe(bits, sync_at):
    """Read a [LEN][payload][CRC] frame starting just after the sync."""
    start = sync_at + 16
    tail = bits_to_bytes_at(bits, start)
    if not tail:
        return None
    length = tail[0]
    body = tail[1:1 + length]
    if len(body) != length:
        return None
    space = body[:-2]
    rxcrc = int.from_bytes(body[-2:], "big")
    crc_ok = crc16_ccitt(space) == rxcrc
    return {
        "len": length,
        "frame": bytes([length]) + body,
        "crc_ok": crc_ok,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iq", default="captures/baseline.iq")
    ap.add_argument("--oracle", default="captures/baseline.jsonl")
    ap.add_argument("--sample-rate", type=int, default=1_000_000)
    ap.add_argument("--bit-rate",    type=int, default=9600)
    args = ap.parse_args()

    print(f"loading {args.iq}")
    iq = read_cu8_complex(args.iq)
    print(f"  {len(iq)} samples ({len(iq) / args.sample_rate:.2f} s)")

    print("demodulating...")
    fd = quadrature_demod(iq)
    bits, burst_starts = slice_bits(fd, args.sample_rate, args.bit_rate)
    print(f"  {len(bits)} symbol decisions across {len(burst_starts)} bursts")

    # Recover frames
    found = []
    last_end = 0
    for sync_at in search_sync(bits):
        if sync_at < last_end:
            continue
        frame = deframe(bits, sync_at)
        if frame and frame["crc_ok"]:
            found.append(frame)
            last_end = sync_at + 16 + (frame["len"] + 1) * 8
            print(f"  @bit {sync_at:6d}  len={frame['len']:3d}  "
                  f"frame={frame['frame'].hex()}")

    print()
    print(f"recovered {len(found)} CRC-OK frames")

    if os.path.exists(args.oracle):
        oracle = [json.loads(l) for l in open(args.oracle) if l.strip()]
        oracle_set = {r["frame"] for r in oracle}
        rec_set    = {f["frame"].hex() for f in found}
        matched = rec_set & oracle_set
        print(f"oracle has {len(oracle_set)} frames; we matched {len(matched)}")
        missing = oracle_set - rec_set
        if missing:
            print("MISSING from recovery:")
            for h in sorted(missing):
                print(f"  {h}")
        extra = rec_set - oracle_set
        if extra:
            print("EXTRA (decoded but not in oracle):")
            for h in sorted(extra):
                print(f"  {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
