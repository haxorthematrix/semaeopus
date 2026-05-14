"""
Operator ground station.

Connects to a Pico+CC1101 over USB-serial, decodes incoming telemetry,
and offers an interactive command prompt for the operator. Built on
`rich` for the UI — fall back to plain stdout if not installed.

Usage:
    python -m groundstation.operator.gs --port /dev/ttyACM0 \
        [--freq 433920000] [--security 0] [--key <16-byte-hex>]

Commands at the prompt:
    ping                              → APID_PING
    safe                              → APID_FORCE_SAFE
    mode <0..3>                       → APID_SET_MODE
    arm | fire                        → ARM_PAYLOAD / FIRE_PAYLOAD
    req <apid_hex>                    → REQ_TLM (e.g. req 010)
    raw <apid_hex> <hex>              → send an arbitrary TC
    key <16-byte-hex>                 → rotate session key
    quit
"""

import argparse
import os
import sys
import threading
import time

# Make project root importable
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from groundstation.shared.decoder import decode_rx
from protocol import space_packet as sp


try:
    from rich.console import Console
    from rich.live import Live
    from rich.table import Table
    console = Console()
except ImportError:
    console = None


class State:
    def __init__(self):
        self.tc_seq = 0
        self.last_nonce = None
        self.security = 0
        self.key = None
        self.history = []   # latest 12 rows

    def next_nonce(self):
        # 8-byte monotonic
        if self.last_nonce is None:
            n = 1
        else:
            n = int.from_bytes(self.last_nonce, "big") + 1
        nonce = n.to_bytes(8, "big")
        return nonce


def build_tc(state, apid, user_data):
    state.tc_seq = (state.tc_seq + 1) & 0x3FFF
    nonce = state.next_nonce() if state.security > 0 else None
    frame = sp.encode(
        sp.TYPE_TC, apid, state.tc_seq, user_data,
        security_level=state.security, key=state.key, nonce=nonce,
    )
    if nonce is not None:
        state.last_nonce = nonce
    return frame


def parse_command(state, line):
    parts = line.strip().split()
    if not parts:
        return None
    cmd = parts[0].lower()
    if cmd == "quit":
        sys.exit(0)
    if cmd == "ping":
        return build_tc(state, sp.APID_PING, b"\x00\x01\x02\x03")
    if cmd == "safe":
        return build_tc(state, sp.APID_FORCE_SAFE, b"")
    if cmd == "arm":
        return build_tc(state, sp.APID_ARM_PAYLOAD, b"")
    if cmd == "fire":
        return build_tc(state, sp.APID_FIRE_PAYLOAD, b"")
    if cmd == "mode" and len(parts) == 2:
        return build_tc(state, sp.APID_SET_MODE, bytes([int(parts[1])]))
    if cmd == "req" and len(parts) == 2:
        return build_tc(state, sp.APID_REQ_TLM, bytes([int(parts[1], 16)]))
    if cmd == "raw" and len(parts) == 3:
        apid = int(parts[1], 16)
        body = bytes.fromhex(parts[2])
        return build_tc(state, apid, body)
    if cmd == "key" and len(parts) == 2:
        body = bytes.fromhex(parts[1])
        if len(body) != 16:
            print("key must be 16 bytes hex")
            return None
        return build_tc(state, sp.APID_KEY_ROTATE, body)
    print("unknown command")
    return None


def reader_thread(state, link):
    while True:
        rx = link.rx_packets()
        if rx is None:
            evt = link.events()
            if evt:
                print("[front-end]", evt)
            time.sleep(0.02)
            continue
        d = decode_rx(rx, security_level=state.security, key=state.key,
                      last_nonce=state.last_nonce if state.security >= 2 else None)
        state.history.append(d)
        state.history = state.history[-12:]
        # Quick console line
        if "error" in d:
            print("RX (bad): %s  RSSI=%d" % (d["error"], d["rssi"]))
        else:
            print("[%5d %s] %s  RSSI=%d  %s" % (
                d["seq"], d["apid_name"], d["type"], d["rssi"], d["pretty"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="serial port, e.g. /dev/ttyACM0")
    ap.add_argument("--sim",  action="store_true",
                    help="use the UDP simulator instead of a serial Pico front-end")
    ap.add_argument("--node-id", default="OPGS",
                    help="virtual node id when --sim (4 chars max)")
    ap.add_argument("--freq", type=int, default=433_920_000)
    ap.add_argument("--sync", default="d391")
    ap.add_argument("--bitrate", type=int, default=9600)
    ap.add_argument("--security", type=int, default=0, choices=[0, 1, 2, 3])
    ap.add_argument("--key", default=None, help="16-byte hex key for sec>=1")
    args = ap.parse_args()

    state = State()
    state.security = args.security
    if args.security > 0:
        if not args.key:
            print("--key required for security >= 1")
            sys.exit(1)
        state.key = bytes.fromhex(args.key)
        if len(state.key) != 16:
            print("key must be 16 bytes")
            sys.exit(1)

    if not args.sim and not args.port:
        ap.error("--port is required unless --sim is given")
    from sim.sim_link import make_link
    link = make_link(args, default_node_id=args.node_id)
    time.sleep(0.5)
    link.send_cfg(args.freq, int(args.sync, 16), args.bitrate)

    threading.Thread(target=reader_thread, args=(state, link), daemon=True).start()

    print("Semaeopus operator GS — type 'quit' to exit.")
    while True:
        try:
            line = input("op> ")
        except (EOFError, KeyboardInterrupt):
            break
        frame = parse_command(state, line)
        if frame:
            link.send_tx(frame)


if __name__ == "__main__":
    main()
