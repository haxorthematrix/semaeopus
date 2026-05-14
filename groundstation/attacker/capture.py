"""
Passive capture: sit on the downlink, log every demodulated frame to
disk in a pcap-like JSONL format. The operator's session can later be
"replayed" against the satellite by `replay.py`.

Doesn't decode security headers — the attacker doesn't necessarily have
the key. The raw frame is logged so the attacker can re-transmit it
byte-identically.

Usage:
    python -m groundstation.attacker.capture --port /dev/ttyACM1 \
        --out captures/session.jsonl
"""

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from groundstation.shared.decoder import decode_rx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--sim",  action="store_true")
    ap.add_argument("--node-id", default="ATKR")
    ap.add_argument("--out",  required=True)
    ap.add_argument("--freq", type=int, default=433_920_000)
    ap.add_argument("--sync", default="d391")
    ap.add_argument("--bitrate", type=int, default=9600)
    args = ap.parse_args()

    if not args.sim and not args.port:
        ap.error("--port is required unless --sim is given")
    from sim.sim_link import make_link
    link = make_link(args, default_node_id=args.node_id)
    time.sleep(0.5)
    link.send_cfg(args.freq, int(args.sync, 16), args.bitrate)

    n = 0
    with open(args.out, "a") as fp:
        print("Capturing to", args.out)
        while True:
            rx = link.rx_packets()
            if rx is None:
                time.sleep(0.02)
                continue
            d = decode_rx(rx)
            record = {
                "ts":    rx["ts"],
                "rssi":  rx["rssi"],
                "lqi":   rx["lqi"],
                "frame": rx["frame"].hex(),
                "decoded": {k: v for k, v in d.items() if k != "raw"},
            }
            fp.write(json.dumps(record) + "\n")
            fp.flush()
            n += 1
            print("[%4d] %s RSSI=%d %s" % (
                n,
                d.get("apid_name", "?"),
                rx["rssi"],
                d.get("pretty", "")[:60]))


if __name__ == "__main__":
    main()
