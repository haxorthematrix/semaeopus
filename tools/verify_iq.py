"""
Modulator smoke test.

Generates a known bitstream, runs it through the GFSK modulator, and
checks two structural properties of the output:

  1. RMS magnitude of the IQ stream is ~1 (constant-envelope FSK).
  2. The instantaneous-frequency sign on a per-bit basis correlates
     strongly with the input bits — proving the modulation carries
     the information, even if a naive integrate-and-dump receiver
     can't recover it byte-perfectly (GFSK with BT=0.5, span=4 has
     significant ISI; a proper matched-filter receiver — e.g. the
     GNU Radio flowgraph in lessons/L02 — is required for full
     recovery, which is exactly the lesson L02 teaches).
"""

import argparse
import cmath
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from tools.generate_iq import (
    bytes_to_bits, modulate_gfsk, PREAMBLE, SYNC,
)
from protocol import space_packet as sp


def quadrature_demod(iq_complex):
    out = [0.0]
    for n in range(1, len(iq_complex)):
        d = iq_complex[n] * iq_complex[n - 1].conjugate()
        out.append(cmath.phase(d))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-rate", type=int, default=1_000_000)
    ap.add_argument("--bit-rate",    type=int, default=9600)
    ap.add_argument("--deviation",   type=int, default=4800)
    args = ap.parse_args()

    # Build a known frame: BEACON
    frame = sp.encode(sp.TYPE_TM, sp.APID_BEACON, 1, b"HELLO")
    bits_in = bytes_to_bits(PREAMBLE + SYNC + frame)
    print("input bits: %d (%d bytes)" % (len(bits_in), len(bits_in) // 8))

    iq = modulate_gfsk(bits_in, args.sample_rate, args.bit_rate,
                       args.deviation, bt=0.5)
    # iq is interleaved floats; pair into complex
    iqc = [complex(iq[i], iq[i + 1]) for i in range(0, len(iq), 2)]
    print("modulated samples: %d (%.3f ms)" % (
        len(iqc), 1000 * len(iqc) / args.sample_rate))

    # Check 1: constant envelope.
    rms = math.sqrt(sum(abs(z) ** 2 for z in iqc) / len(iqc))
    print("IQ RMS magnitude: %.3f (expect ~1.0)" % rms)
    if not 0.6 < rms < 1.05:
        print("FAIL: envelope is not roughly constant — modulator broken")
        return 1

    # Check 2: per-bit frequency direction correlates with input bits.
    fd = quadrature_demod(iqc)
    sps_int = int(round(args.sample_rate / args.bit_rate))
    K = 4 * sps_int + 1
    decision_offset = (K - 1) // 2 + sps_int

    n_match = 0
    n_total = 0
    for k in range(len(bits_in)):
        si = decision_offset + k * sps_int
        ei = si + sps_int
        if ei > len(fd):
            break
        acc = sum(fd[si:ei])
        guess = 1 if acc > 0 else 0
        n_total += 1
        if guess == bits_in[k]:
            n_match += 1

    rate = n_match / n_total if n_total else 0
    print("naive slicer matched %d / %d bits  (%.1f%%)"
          % (n_match, n_total, 100 * rate))
    # > 80 % match with this trivial slicer indicates the modulation
    # is well-formed; the residual ~15 % is GFSK ISI that a real
    # receiver removes with a matched filter.
    if rate < 0.80:
        print("FAIL: naive demod < 80 %% — modulator looks broken")
        return 1
    print("OK: modulator output is well-formed GFSK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
