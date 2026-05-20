"""
Light-touch fuzzer for the satellite TC handler.

Sweeps APID, payload length, and content. Useful for finding handlers
that crash on malformed input, or fault-handler flaws (e.g. UPLOAD_TLE
with a non-numeric body).

By default this fuzzes at L0 (no auth). Bring `--key` to fuzz a signed
link — useful once a key has been exfiltrated in a later lesson.

Usage:
    python -m groundstation.attacker.fuzz --port /dev/ttyACM1 \
        --duration 60      # 60 seconds of fuzzing
"""

import argparse
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from protocol import space_packet as sp


# A list of APIDs we'll target — known + a few random unknowns.
TARGET_APIDS = [
    sp.APID_PING, sp.APID_REQ_TLM, sp.APID_SET_MODE, sp.APID_ARM_PAYLOAD,
    sp.APID_FIRE_PAYLOAD, sp.APID_UPLOAD_TLE, sp.APID_TIME_SET,
    sp.APID_KEY_ROTATE, sp.APID_FORCE_SAFE,
    0x100, 0x123, 0x7FE,    # nonsense APIDs to test error handling
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--sim",  action="store_true")
    ap.add_argument("--node-id", default="ATKR")
    ap.add_argument("--duration", type=float, default=30.0)
    ap.add_argument("--rate", type=float, default=5.0,
                    help="frames per second")
    ap.add_argument("--freq", type=int, default=433_920_000)
    ap.add_argument("--sync", default="d391")
    ap.add_argument("--bitrate", type=int, default=9600)
    ap.add_argument("--security", type=int, default=0, choices=[0, 1, 2, 3])
    ap.add_argument("--key", default=None, help="16-byte hex (sec>=1)")
    args = ap.parse_args()

    key = None
    if args.security > 0:
        if not args.key:
            ap.error("--key is required when --security >= 1")
        key = bytes.fromhex(args.key)
        if len(key) != 16:
            ap.error("--key must be 16 bytes hex")

    if not args.sim and not args.port:
        ap.error("--port is required unless --sim is given")
    from sim.sim_link import make_link
    link = make_link(args, default_node_id=args.node_id)
    time.sleep(0.5)
    link.send_cfg(args.freq, int(args.sync, 16), args.bitrate)

    period = 1.0 / args.rate
    deadline = time.time() + args.duration
    n = 0
    seq = 1
    base_nonce = int(time.time() * 1000)
    while time.time() < deadline:
        apid = random.choice(TARGET_APIDS)
        length = random.choice([0, 1, 4, 8, 16, 32, 64, 128])
        body = bytes(random.randrange(256) for _ in range(length))
        nonce = ((base_nonce + n) & ((1 << 64) - 1)).to_bytes(8, "big") if key else None
        try:
            frame = sp.encode(sp.TYPE_TC, apid, seq, body,
                              security_level=args.security,
                              key=key, nonce=nonce)
        except Exception as e:
            print("encode failed:", e)
            continue
        link.send_tx(frame)
        n += 1
        seq = (seq + 1) & 0x3FFF
        time.sleep(period)
    print("fuzzed %d frames in %.1fs" % (n, args.duration))


if __name__ == "__main__":
    main()
