"""
Bring-up 05 — SPI loopback.

Verifies SPI0 by jumpering MOSI (GP19) directly to MISO (GP12) with a
single Dupont wire (no CC1101 in circuit yet). The Pico writes a byte
and reads it back. PASS iff the bytes match.

If this fails the rest of the radio bring-up will never work, because
SPI is the only way the Pico talks to the CC1101.

   ┌─ remove CC1101 from breadboard
   └─ jumper GP19 (MOSI) ←→ GP12 (MISO) with a single wire
"""

from machine import Pin, SPI
import os

spi = SPI(0,
          baudrate=1_000_000,
          polarity=0, phase=0,
          sck=Pin(18), mosi=Pin(19), miso=Pin(12))

probe = os.urandom(8) if hasattr(os, "urandom") else bytes(range(8))
rx = bytearray(len(probe))
spi.write_readinto(probe, rx)

print(f"TX: {probe.hex()}")
print(f"RX: {bytes(rx).hex()}")
if bytes(rx) == probe:
    print("PASS: SPI0 MOSI↔MISO loopback intact")
else:
    print("FAIL: SPI loopback bytes do not match")
    print("  - is the jumper actually between GP19 and GP12?")
    print("  - any other device on the SPI bus is muting MISO? Remove it.")
