"""
Timing side-channel oracle for lesson L09.

Runs a localhost TCP server that:
  - Loads the codec with SEMAEOPUS_LEAKY_HMAC=1 (short-circuit
    byte-by-byte HMAC compare with 1.5 ms per-byte delay).
  - Accepts hex-encoded frames over the socket.
  - Verifies them against a fixed key + nonce.
  - Returns "ACCEPT\\n" or "REJECT\\n" — nothing else, no error
    detail, no timing field. The attacker times the round-trip
    externally.

This intentionally mirrors a real authenticated-link receiver:
the only legitimate bit of information the attacker should be able
to obtain is the boolean "did this frame pass?" — but timing leaks
turn that one bit into a per-byte oracle.

Usage:
    python -m tools.timing_oracle --port 9009

Then in lesson L09 you'll launch tools.timing_attack against it.
"""

import argparse
import os
import socketserver
import sys
import time

os.environ["SEMAEOPUS_LEAKY_HMAC"] = "1"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from protocol import space_packet as sp     # noqa: E402  (sets up env first)


# Demo key + a fixed nonce — the attacker doesn't know either. The
# attacker DOES know: (a) the structure of the frame, (b) the body
# they want to send, (c) how to retry with varying tag bytes.
KEY   = bytes.fromhex("53656d61656f7075734b65795f763031")
NONCE = bytes.fromhex("00000000000000aa")


class OracleHandler(socketserver.StreamRequestHandler):
    def handle(self):
        # Disable Nagle so timing-sensitive ACCEPT/REJECT bytes go on
        # the wire immediately.
        import socket as _s
        self.request.setsockopt(_s.IPPROTO_TCP, _s.TCP_NODELAY, 1)
        # Multiple queries per connection — speeds up the attack.
        while True:
            line = self.rfile.readline()
            if not line:
                return
            try:
                frame = bytes.fromhex(line.decode().strip())
            except ValueError:
                self.wfile.write(b"REJECT\n")
                continue
            try:
                d = sp.decode(frame, security_level=sp.SEC_L1_HMAC, key=KEY)
                accept = d["auth_ok"] is True
            except sp.DecodeError:
                accept = False
            self.wfile.write(b"ACCEPT\n" if accept else b"REJECT\n")
            self.wfile.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9009)
    ap.add_argument("--target-body", default="00",
                    help="hex bytes that the attacker wants to send (TC body)")
    args = ap.parse_args()

    # Print the target frame structure so the attacker can build candidates.
    target_body = bytes.fromhex(args.target_body)
    target_apid = sp.APID_FORCE_SAFE
    target_seq  = 1
    correct_frame = sp.encode(
        sp.TYPE_TC, target_apid, target_seq, target_body,
        security_level=sp.SEC_L1_HMAC, key=KEY, nonce=NONCE,
    )
    correct_tag = correct_frame[1 + 6 + sp.NONCE_LEN: 1 + 6 + sp.NONCE_LEN + sp.TAG_LEN]
    print("=== ORACLE STARTING (DEMO MODE) ===")
    print(f"Body the attacker wants to send : {target_body.hex()}")
    print(f"APID                            : 0x{target_apid:03x}")
    print(f"Seq                             : {target_seq}")
    print(f"Nonce (publicly visible)        : {NONCE.hex()}")
    print(f"Tag (NOT revealed to attacker)  : {correct_tag.hex()}")
    print(f"Frame (NOT revealed)            : {correct_frame.hex()}")
    print()
    print(f"Listening on {args.host}:{args.port} — one ACCEPT/REJECT per hex frame.")

    class _Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
    with _Server((args.host, args.port), OracleHandler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\noracle stopped")


if __name__ == "__main__":
    main()
