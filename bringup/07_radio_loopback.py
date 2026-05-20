"""
Bring-up 07 — Two-radio loopback.

Run this on TWO Picos+CC1101 at the same time (one with role=TX, one
with role=RX). Each side configures the radio to the Semaeopus default
parameters and either:

  - TX side: transmits a known 16-byte payload every 500 ms for 30
    seconds, then PASSes regardless. (Receiver is the judge.)
  - RX side: listens, prints every received frame with RSSI. PASSes
    iff at least 10 of the expected 60 transmissions arrive cleanly
    in 30 seconds (16 % delivery — generous because preamble timing
    and antenna pose vary on a bare bench).

Usage:

    # On Pico A
    mpremote connect /dev/ttyACM0 run bringup/07_radio_loopback.py tx

    # On Pico B (in another terminal)
    mpremote connect /dev/ttyACM1 run bringup/07_radio_loopback.py rx
"""

import sys
import time

# This script needs cc1101.py on the device — easiest is to copy the
# firmware lib into /lib first:
#     mpremote cp -r firmware/satellite/lib :/lib
sys.path.insert(0, "/lib")

try:
    import cc1101
except ImportError:
    print("FAIL: /lib/cc1101.py not found on device.")
    print("Run:  mpremote cp -r firmware/satellite/lib :/lib")
    raise SystemExit


class _Cfg:
    PIN_SPI_SCK   = 18
    PIN_SPI_MOSI  = 19
    PIN_SPI_MISO  = 12
    PIN_CC1101_CS = 13
    PIN_CC1101_GDO0 = 10
    RF_FREQ_HZ      = 433_920_000
    RF_BITRATE_BPS  = 9600
    RF_DEVIATION_HZ = 4800
    RF_RX_BW_HZ     = 58_000
    RF_SYNC_WORD    = 0xD391
    RF_TX_POWER_DBM = 0


radio = cc1101.make_default(_Cfg)

ROLE_TX = "tx"
ROLE_RX = "rx"

# Find the role argument — mpremote run passes argv via the
# `sys.argv` of the running script.
role = sys.argv[1].lower() if len(sys.argv) > 1 else None
if role not in (ROLE_TX, ROLE_RX):
    print("FAIL: usage:  ... 07_radio_loopback.py {tx|rx}")
    raise SystemExit


PROBE = b"SEMAEOPUS-PING01"        # 16 bytes
# Variable-length packet expects [LEN][payload]
FRAME = bytes([len(PROBE)]) + PROBE

if role == ROLE_TX:
    print("TX role — sending 60 frames over 30 seconds")
    for i in range(60):
        radio.transmit(FRAME)
        print(f"  tx #{i+1}")
        time.sleep(0.5)
    print("PASS: TX complete; check RX side for delivery count")
else:
    print("RX role — listening for 30 seconds")
    radio.listen()
    got = 0
    bad = 0
    deadline = time.ticks_add(time.ticks_ms(), 30_000)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        if radio.packet_available():
            frame, rssi, lqi = radio.read_packet()
            if frame is None:
                continue
            if frame[1:] == PROBE:
                got += 1
                print(f"  rx #{got}  RSSI={rssi} dBm  LQI={lqi}")
            else:
                bad += 1
                print(f"  rx ??? len={frame[0]} body={frame[1:].hex()} RSSI={rssi}")
        time.sleep_ms(10)
    print(f"Received {got} valid + {bad} junk in 30 s")
    if got >= 10:
        print("PASS: link delivers expected payload")
    else:
        print("FAIL: <10 frames received in 30 s")
        print("  - confirm the OTHER Pico printed 'TX complete'")
        print("  - same antenna length on both sides?  17 cm for 433.92 MHz")
        print("  - try moving the radios 30 cm apart, NOT touching each other")
        print("  - both CC1101s on the same sync word, freq, bitrate? (this script's defaults match)")
