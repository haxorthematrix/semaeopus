"""
Ground-station radio front-end.

A Pi Pico + CC1101 acting as a "modem" between the host laptop (over
USB-CDC) and the ISM-band link. Speaks a tiny ASCII protocol so it can
be driven from any language with a serial library — and so the learner
can see exactly what they're sending.

Host → Pico
-----------
  CFG <freq_hz> <sync_hex> <bitrate>  — reconfigure radio
  TX  <hex_bytes>                     — push raw frame bytes to radio TX
  PING                                — health-check; replies "PONG <ms>"

Pico → host
-----------
  RX  <hex_bytes>  RSSI=<dbm>  LQI=<n>
  EVT <text>
  ERR <text>

Note: the bytes pushed via `TX` should be a complete frame including the
length byte that the CC1101 variable-length packet engine expects. The
operator and attacker code in `groundstation/` calls
`protocol.space_packet.encode` to build that.
"""

import sys
import select
import time
from machine import Pin, SPI

# Pinout — match firmware/satellite/config.py (same wiring).
PIN_SPI_SCK   = 18
PIN_SPI_MOSI  = 19
PIN_SPI_MISO  = 12
PIN_CC1101_CS = 13
PIN_GDO0      = 10

# Default radio params (override via CFG)
FREQ_HZ   = 433_920_000
SYNC_WORD = 0xD391
BITRATE   = 9600

from lib import cc1101


spi = SPI(0, baudrate=5_000_000, polarity=0, phase=0,
          sck=Pin(PIN_SPI_SCK), mosi=Pin(PIN_SPI_MOSI), miso=Pin(PIN_SPI_MISO))
radio = cc1101.CC1101(spi, PIN_CC1101_CS, PIN_GDO0)
radio.reset()


class _Cfg:
    pass

cfg = _Cfg()
cfg.PIN_SPI_SCK = PIN_SPI_SCK
cfg.PIN_SPI_MOSI = PIN_SPI_MOSI
cfg.PIN_SPI_MISO = PIN_SPI_MISO
cfg.PIN_CC1101_CS = PIN_CC1101_CS
cfg.PIN_CC1101_GDO0 = PIN_GDO0
cfg.RF_FREQ_HZ = FREQ_HZ
cfg.RF_BITRATE_BPS = BITRATE
cfg.RF_DEVIATION_HZ = 4800
cfg.RF_RX_BW_HZ = 58_000
cfg.RF_SYNC_WORD = SYNC_WORD
cfg.RF_TX_POWER_DBM = 0

radio.configure_default(
    freq_hz=FREQ_HZ, sync_word=SYNC_WORD, bitrate_bps=BITRATE,
    deviation_hz=4800, rx_bw_hz=58_000, tx_power_dbm=0,
)
radio.listen()


poll = select.poll()
poll.register(sys.stdin, select.POLLIN)
line_buf = bytearray()


def send(line):
    sys.stdout.write(line + "\n")


def handle_line(line):
    parts = line.strip().split()
    if not parts:
        return
    cmd = parts[0].upper()
    if cmd == "PING":
        send("PONG %d" % time.ticks_ms())
    elif cmd == "TX":
        if len(parts) < 2:
            send("ERR tx: missing hex")
            return
        try:
            payload = bytes.fromhex(parts[1])
        except ValueError:
            send("ERR tx: bad hex")
            return
        radio.transmit(payload)
        radio.listen()
        send("EVT tx ok %d" % len(payload))
    elif cmd == "CFG":
        if len(parts) != 4:
            send("ERR cfg: need <freq> <sync> <bitrate>")
            return
        try:
            f = int(parts[1])
            s = int(parts[2], 16)
            b = int(parts[3])
        except ValueError:
            send("ERR cfg: parse")
            return
        radio.set_frequency(f)
        radio.set_sync_word(s)
        radio.listen()
        send("EVT cfg %d %04x %d" % (f, s, b))
    else:
        send("ERR unknown %s" % cmd)


send("EVT semaeopus-gs-frontend ready")

while True:
    # USB-CDC line input (non-blocking)
    if poll.poll(0):
        ch = sys.stdin.read(1)
        if ch in ("\n", "\r"):
            if line_buf:
                try:
                    handle_line(line_buf.decode())
                except Exception as e:
                    send("ERR " + str(e))
                line_buf = bytearray()
        else:
            line_buf += ch.encode()

    # Radio RX poll
    if radio.packet_available():
        frame, rssi, lqi = radio.read_packet()
        if frame is not None:
            send("RX %s RSSI=%d LQI=%d" % (frame.hex(), rssi, lqi))

    time.sleep_ms(2)
