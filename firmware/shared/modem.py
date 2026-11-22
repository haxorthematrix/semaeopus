"""
CC1101 USB modem shared by the operator ground station (CYD) and the
attacker radio (Pico). Speaks the same ASCII line protocol as the
original firmware/gs_frontend, so groundstation/shared/link.py and every
operator and attacker tool work unchanged.

Host -> modem (one command per line)
  PING                              -> PONG <ticks_ms>
  TX  <hex>                         -> push a complete frame (LEN byte first)
  CFG <freq_hz> <sync_hex> <bps>    -> retune (bit rate is fixed at 9600)
  BW  <hz>                          -> receive filter bandwidth (lesson L10)
  PWR <dbm>                         -> transmit power, -30 .. +10 dBm

Modem -> host
  RX  <hex> RSSI=<dbm> LQI=<n>
  EVT <text>
  ERR <text>
"""

import sys
import select
import time

from lib import cc1101

DEFAULT_SYNC = 0xD391
DEFAULT_BPS = 9600


class Modem:
    def __init__(self, radio, freq_hz, tx_power_dbm=0, name="modem",
                 on_rx=None, on_tx=None, on_event=None):
        self.radio = radio
        self.name = name
        self.freq_hz = freq_hz
        self.sync = DEFAULT_SYNC
        self.bps = DEFAULT_BPS
        self.power_dbm = tx_power_dbm
        self.bw_hz = 58_000
        self.on_rx = on_rx
        self.on_tx = on_tx
        self.on_event = on_event
        self.rx_count = 0
        self.tx_count = 0
        radio.reset()
        radio.configure_default(
            freq_hz=freq_hz, sync_word=self.sync, bitrate_bps=self.bps,
            deviation_hz=4800, rx_bw_hz=self.bw_hz, tx_power_dbm=tx_power_dbm,
        )
        radio.listen()
        self._poll = select.poll()
        self._poll.register(sys.stdin, select.POLLIN)
        self._line = bytearray()

    # ---- host side -------------------------------------------------------------

    def send(self, line):
        sys.stdout.write(line + "\n")

    def event(self, text):
        self.send("EVT " + text)
        if self.on_event:
            self.on_event(text)

    def error(self, text):
        self.send("ERR " + text)
        if self.on_event:
            self.on_event("ERR " + text)

    def handle_line(self, line):
        parts = line.strip().split()
        if not parts:
            return
        cmd = parts[0].upper()
        if cmd == "PING":
            self.send("PONG %d" % time.ticks_ms())
        elif cmd == "TX":
            if len(parts) < 2:
                return self.error("tx: missing hex")
            try:
                frame = bytes.fromhex(parts[1])
            except ValueError:
                return self.error("tx: bad hex")
            if not frame or frame[0] != len(frame) - 1:
                return self.error("tx: first byte must be the frame length")
            if len(frame) > 62:     # receiver's 64-byte FIFO also holds 2 status bytes
                return self.error("tx: %d bytes is too long; max 62 (CC1101 FIFO)" % len(frame))
            self._forward_rx()          # listen() after TX flushes the RX FIFO
            self.radio.transmit(frame)
            self.radio.listen()
            self.tx_count += 1
            self.send("EVT tx ok %d" % len(frame))
            if self.on_tx:
                self.on_tx(frame)
        elif cmd == "CFG":
            if len(parts) != 4:
                return self.error("cfg: need <freq> <sync> <bitrate>")
            try:
                f = int(parts[1])
                s = int(parts[2], 16)
                b = int(parts[3])
            except ValueError:
                return self.error("cfg: parse")
            if not 902_000_000 <= f <= 928_000_000 and not 433_050_000 <= f <= 434_790_000:
                return self.error("cfg: %d Hz is outside 902-928 / 433.05-434.79 MHz" % f)
            self.radio.idle()
            self.radio.set_frequency(f)
            self.radio.set_sync_word(s)
            self.radio.set_tx_power(self.power_dbm)   # PATABLE depends on band
            self.radio.listen()
            self.freq_hz, self.sync, self.bps = f, s, b
            self.event("cfg %d %04x %d" % (f, s, b))
        elif cmd == "BW":
            try:
                want = int(parts[1])
            except (IndexError, ValueError):
                return self.error("bw: need <hz>")
            self.radio.idle()
            self.bw_hz = self.radio.set_rx_bandwidth(want)
            self.radio.listen()
            self.event("bw %d" % self.bw_hz)
        elif cmd == "PWR":
            try:
                dbm = int(parts[1])
            except (IndexError, ValueError):
                return self.error("pwr: need <dbm>")
            self.power_dbm = max(-30, min(10, dbm))
            self.radio.idle()
            self.radio.set_tx_power(self.power_dbm)
            self.radio.listen()
            self.event("pwr %d" % self.power_dbm)
        else:
            self.error("unknown %s" % cmd)

    # ---- main loop -----------------------------------------------------------

    def poll_once(self):
        while self._poll.poll(0):
            ch = sys.stdin.read(1)
            if not ch:
                break
            if ch in ("\n", "\r"):
                if self._line:
                    try:
                        self.handle_line(self._line.decode())
                    except Exception as e:
                        self.error(str(e))
                    self._line = bytearray()
            elif len(self._line) < 300:
                self._line += ch.encode()
        self._forward_rx()

    def _forward_rx(self):
        if self.radio.packet_available():
            frame, rssi, lqi = self.radio.read_packet()
            if frame is not None:
                self.rx_count += 1
                self.send("RX %s RSSI=%d LQI=%d" % (frame.hex(), rssi, lqi))
                if self.on_rx:
                    self.on_rx(frame, rssi, lqi)

    def run(self, idle_hook=None, hook_period_ms=500):
        self.event("semaeopus-%s ready %d" % (self.name, self.freq_hz))
        last = time.ticks_ms()
        while True:
            self.poll_once()
            if idle_hook and time.ticks_diff(time.ticks_ms(), last) >= hook_period_ms:
                last = time.ticks_ms()
                idle_hook()
            time.sleep_ms(2)
