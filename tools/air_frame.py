"""
Build a Semaeopus frame exactly as a CC1101 puts it on the air, for
transmitting from an SDR (GNU Radio or hackrf_transfer).

With the register settings in firmware/satellite/lib/cc1101.py the
radio sends:

    preamble  AA AA AA AA            (MDMCFG1 NUM_PREAMBLE = 4 bytes)
    sync      D3 91 D3 91            (MDMCFG2 SYNC_MODE = 30/32: the
                                      16-bit sync word is sent twice)
    LEN       1 byte                 (number of bytes that follow, not
                                      counting the radio CRC)
    packet    CCSDS space packet + its CRC-16-CCITT
    radio CRC CRC-16, poly 0x8005, init 0xFFFF, over LEN + packet
                                     (PKTCTRL0 CRC_EN; the receiving
                                      CC1101 drops frames that fail it)

at 9600 bit/s, 2-GFSK, BT = 0.5, ~20.6 kHz deviation (DEVIATN 0x35),
no whitening.

Usage:
    # FORCE_SAFE telecommand -> raw on-air bytes for a GNU Radio File Source
    python -m tools.air_frame --type tc --apid FORCE_SAFE --out /tmp/tc_air.bin

    # any captured frame (hex of LEN..CRC, as the modem prints it)
    python -m tools.air_frame --frame 0810ffc0... --out /tmp/replay_air.bin

    # also write IQ for hackrf_transfer (signed 8-bit, 2.016 Msps)
    python -m tools.air_frame --type tc --apid FORCE_SAFE \\
        --out /tmp/tc_air.bin --iq /tmp/tc.cs8
    hackrf_transfer -t /tmp/tc.cs8 -f 915000000 -s 2016000 -x 20
"""

import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from protocol import space_packet as sp  # noqa: E402

FXOSC_HZ = 26_000_000
DEVIATION_HZ = round(FXOSC_HZ / 2**17 * (8 + 5) * 2**3)     # DEVIATN 0x35 -> 20630
BIT_RATE = 9600
SYNC = b"\xD3\x91"
PREAMBLE_BYTE = 0xAA


def crc16_cc1101(data):
    """CC1101 hardware CRC: poly 0x8005, init 0xFFFF, MSB first, no xorout."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x8005) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def air_bytes(frame, preamble_bytes=4, pad_bytes=2):
    """Wrap `frame` ([LEN][space packet][CRC], as sp.encode returns it)
    in what the CC1101 transmits. Extra preamble is harmless and gives an
    SDR's transmitter time to settle; the trailing pad keeps the end of
    the radio CRC from being cut off when the flowgraph stops."""
    if len(frame) < 2 or frame[0] != len(frame) - 1:
        raise ValueError("frame must start with its length byte (len-1)")
    if len(frame) > 62:
        raise ValueError("frame longer than the CC1101's 62-byte limit")
    crc = crc16_cc1101(frame)
    return (bytes([PREAMBLE_BYTE]) * preamble_bytes + SYNC + SYNC + frame
            + bytes([crc >> 8, crc & 0xFF]) + bytes(pad_bytes))


def _apid(value):
    try:
        return int(value, 0)
    except ValueError:
        return getattr(sp, "APID_" + value.upper())


def gfsk_iq(bits, sample_rate, bit_rate=BIT_RATE, deviation=DEVIATION_HZ, bt=0.5):
    """2-GFSK baseband, interleaved I,Q floats. Each bit's frequency pulse
    is a rectangle convolved with a Gaussian whose standard deviation is
    sqrt(ln 2) / (2 pi BT) bit periods, the usual GFSK definition."""
    sigma = math.sqrt(math.log(2)) / (2 * math.pi * bt)          # in bits
    k = 1 / (sigma * math.sqrt(2))

    def pulse(t):                                               # t in bits
        return 0.5 * (math.erf((t + 0.5) * k) - math.erf((t - 0.5) * k))

    nrz = [1.0 if b else -1.0 for b in bits]
    n = int(len(bits) * sample_rate / bit_rate)
    phase, step = 0.0, 2 * math.pi * deviation / sample_rate
    iq = []
    for i in range(n):
        t = i * bit_rate / sample_rate                          # in bits
        c = int(t)
        f = 0.0
        for j in range(max(0, c - 3), min(len(nrz), c + 4)):
            f += nrz[j] * pulse(t - j - 0.5)
        phase += step * f
        iq.append(math.cos(phase))
        iq.append(math.sin(phase))
    return iq


def bits_of(buf):
    return [(b >> i) & 1 for b in buf for i in range(7, -1, -1)]


def write_cs8(path, iq, gain=0.7):
    """Interleaved I,Q as signed 8-bit (hackrf_transfer -t format)."""
    buf = bytearray(len(iq))
    for i, v in enumerate(iq):
        s = max(-1.0, min(1.0, v * gain))
        buf[i] = int(round(s * 127)) & 0xFF
    with open(path, "wb") as fp:
        fp.write(buf)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--frame", help="hex of a complete frame (LEN..CRC)")
    src.add_argument("--apid", help="APID number or name, e.g. FORCE_SAFE, PING")
    ap.add_argument("--type", choices=["tc", "tm"], default="tc")
    ap.add_argument("--seq", type=int, default=1)
    ap.add_argument("--data", default="", help="user data, hex")
    ap.add_argument("--preamble-bytes", type=int, default=8)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--gap-ms", type=int, default=100,
                    help="silence between repeats (IQ output only)")
    ap.add_argument("--out", required=True, help="raw on-air bytes")
    ap.add_argument("--iq", help="also write signed 8-bit IQ for hackrf_transfer")
    ap.add_argument("--sample-rate", type=int, default=2_016_000,
                    help="IQ sample rate; a multiple of 9600 keeps the bit rate exact")
    ap.add_argument("--deviation", type=int, default=DEVIATION_HZ)
    ap.add_argument("--bt", type=float, default=0.5)
    args = ap.parse_args(argv)

    if args.frame:
        frame = bytes.fromhex(args.frame)
    else:
        ptype = sp.TYPE_TC if args.type == "tc" else sp.TYPE_TM
        frame = sp.encode(ptype, _apid(args.apid), args.seq, bytes.fromhex(args.data))

    air = air_bytes(frame, args.preamble_bytes)
    with open(args.out, "wb") as fp:
        fp.write(air * args.repeat)
    print("frame   :", frame.hex())
    print("on air  :", air.hex())
    print("wrote %s (%d bytes x %d)" % (args.out, len(air), args.repeat))

    if args.iq:
        burst = gfsk_iq(bits_of(air), args.sample_rate, BIT_RATE,
                        args.deviation, args.bt)
        gap = [0.0] * (2 * int(args.sample_rate * args.gap_ms / 1000))
        iq = list(gap)
        for _ in range(args.repeat):
            iq += burst + gap
        write_cs8(args.iq, iq)
        print("wrote %s (%.0f ms at %d S/s, cs8)" % (
            args.iq, 1000 * len(iq) / 2 / args.sample_rate, args.sample_rate))


if __name__ == "__main__":
    main()
