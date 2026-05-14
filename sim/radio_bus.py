"""
UDP "ether" for the simulator.

Every virtual node (satellite, operator GS, attacker GS) joins a UDP
multicast group. A transmit is a `sendto` of a length-prefixed
[LEN][space packet][CRC] frame; a receive is a `recvfrom` of the same.

Loopback is suppressed (a node never sees its own transmissions) so
the model behaves like a real half-duplex RF link.

Each datagram carries a tiny synthetic header:
    [4 B  src_id ASCII][1 B tx_power_dbm signed][N B frame]

The receiver decodes a *fake* RSSI from that, biased by `noise_floor`.
This lets attacker tooling see something sensible in the `RSSI=` field
without us having to actually model the channel.
"""

import os
import random
import socket
import struct
import threading
import time


DEFAULT_GROUP = "239.10.6.7"
DEFAULT_PORT  = 53433
HEADER_FMT    = ">4sb"
HEADER_LEN    = struct.calcsize(HEADER_FMT)


class RadioNode:
    """One virtual radio. Same shape as CC1101 driver — `transmit`,
    `listen`, `packet_available`, `read_packet` — so the satellite and
    GS code can use it identically."""

    def __init__(self, node_id, group=None, port=None, tx_power_dbm=0,
                 noise_floor_dbm=-95):
        if len(node_id) > 4:
            raise ValueError("node_id <= 4 chars")
        self.node_id = node_id.ljust(4)[:4].encode("ascii")
        self.tx_power = tx_power_dbm
        self.noise_floor = noise_floor_dbm
        self.group = group or os.environ.get("SEMAEOPUS_GROUP", DEFAULT_GROUP)
        self.port  = int(port or os.environ.get("SEMAEOPUS_PORT", DEFAULT_PORT))

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        self.sock.bind(("", self.port))
        mreq = socket.inet_aton(self.group) + socket.inet_aton("0.0.0.0")
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        # Loopback stays on so multiple nodes on the same host see each
        # other; we filter out our own frames in software via node_id.
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        self.sock.settimeout(0.0)

        self._listening = False
        self._rx_q = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    # CC1101-compatible API -----------------------------------------------------

    def listen(self):
        self._listening = True

    def transmit(self, frame_bytes):
        hdr = struct.pack(HEADER_FMT, self.node_id, self.tx_power & 0xFF)
        try:
            self.sock.sendto(hdr + bytes(frame_bytes), (self.group, self.port))
        except OSError as e:
            print("[radio_bus] tx error:", e)

    def packet_available(self):
        with self._lock:
            return bool(self._rx_q) and self._listening

    def read_packet(self):
        with self._lock:
            if not self._rx_q or not self._listening:
                return None, None, None
            frame, rssi, lqi = self._rx_q.pop(0)
        return frame, rssi, lqi

    # ------------------------------------------------------------------------

    def close(self):
        self._stop.set()
        try:
            self.sock.close()
        except Exception:
            pass

    def _reader(self):
        while not self._stop.is_set():
            try:
                data, _addr = self.sock.recvfrom(2048)
            except (BlockingIOError, socket.timeout, OSError):
                time.sleep(0.005)
                continue
            if len(data) < HEADER_LEN + 1:
                continue
            src, tx_power = struct.unpack(HEADER_FMT, data[:HEADER_LEN])
            frame = data[HEADER_LEN:]
            if src == self.node_id:
                continue
            # Synthesize RSSI: tx_power + Gaussian-ish noise around -45 dBm.
            rssi = tx_power - 45 + int(random.gauss(0, 3))
            lqi = max(0, min(127, 110 - (self.noise_floor - rssi)))
            with self._lock:
                self._rx_q.append((bytes(frame), rssi, lqi))
