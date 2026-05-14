"""
Thin wrapper around the USB-CDC line protocol exposed by
firmware/gs_frontend.

Used by both the operator app and the attacker tooling. Keeps a
background reader thread so the caller can iterate `link.rx_packets()`
without blocking on the serial port.
"""

import queue
import re
import threading
import time

import serial


_RX_RE = re.compile(r"^RX\s+([0-9a-fA-F]+)\s+RSSI=(-?\d+)\s+LQI=(\d+)\s*$")


class Link:
    def __init__(self, port, baud=115200):
        self.ser = serial.Serial(port, baud, timeout=0.05)
        self._rx_q = queue.Queue()
        self._evt_q = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):
        buf = b""
        while not self._stop.is_set():
            chunk = self.ser.read(256)
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode("ascii", "replace").strip()
                if not line:
                    continue
                m = _RX_RE.match(line)
                if m:
                    self._rx_q.put({
                        "frame": bytes.fromhex(m.group(1)),
                        "rssi":  int(m.group(2)),
                        "lqi":   int(m.group(3)),
                        "ts":    time.time(),
                    })
                else:
                    self._evt_q.put(line)

    def send_tx(self, frame_bytes):
        self.ser.write(b"TX " + frame_bytes.hex().encode() + b"\n")

    def send_cfg(self, freq_hz, sync_word, bitrate):
        line = "CFG %d %04x %d\n" % (freq_hz, sync_word, bitrate)
        self.ser.write(line.encode())

    def rx_packets(self):
        """Yields one queued RX dict each call, or None if empty."""
        try:
            return self._rx_q.get_nowait()
        except queue.Empty:
            return None

    def events(self):
        try:
            return self._evt_q.get_nowait()
        except queue.Empty:
            return None

    def close(self):
        self._stop.set()
        self.ser.close()
