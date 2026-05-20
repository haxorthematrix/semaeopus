"""
Convert an rtl_sdr-style `.cu8` file (interleaved unsigned 8-bit I/Q)
into a GNU-Radio-native `.cfile` (interleaved 32-bit float complex).

Usage:
    python -m tools.cu8_to_cfile captures/baseline.iq captures/baseline.cfile

The output is what GNU Radio's `blocks_file_source` reads natively
with `Type: complex`, `Vector Length: 1`.
"""

import argparse
import os
import struct
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    args = ap.parse_args()

    with open(args.input, "rb") as fin, open(args.output, "wb") as fout:
        # Process in 64 KiB blocks
        while True:
            raw = fin.read(65536)
            if not raw:
                break
            n = len(raw) - (len(raw) & 1)
            if n == 0:
                break
            # interleaved uchar → float complex
            buf = bytearray(n * 4)  # each uchar → 4-byte float (I), then (Q)
            for i in range(0, n, 2):
                I = (raw[i]     - 127.5) / 127.5
                Q = (raw[i + 1] - 127.5) / 127.5
                struct.pack_into("<ff", buf, i * 4, I, Q)
            fout.write(buf)

    fin_size  = os.path.getsize(args.input)
    fout_size = os.path.getsize(args.output)
    print(f"converted {fin_size} bytes uchar → {fout_size} bytes float-complex")
    print(f"sample count: {fin_size // 2}")


if __name__ == "__main__":
    sys.exit(main())
