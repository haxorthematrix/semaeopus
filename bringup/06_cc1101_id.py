"""
Bring-up 06 — CC1101 identification.

The CC1101 has two read-only status registers that act as a
"fingerprint": PARTNUM (0x30) and VERSION (0x31). On a working
through-hole module they read:

    PARTNUM  = 0x00     (always)
    VERSION  = 0x04 or 0x14 (chip revision — both fine)

PASS iff PARTNUM matches AND VERSION is non-zero / non-0xFF. The
all-ones case is the classic "no chip present, MISO floating".
"""

from machine import Pin, SPI
import time


PIN_SCK, PIN_MOSI, PIN_MISO = 18, 19, 12
PIN_CS = 13

# Strobe + register helpers (subset of firmware/satellite/lib/cc1101.py)
SRES = 0x30
PARTNUM_REG = 0x30
VERSION_REG = 0x31


spi = SPI(0, baudrate=1_000_000, polarity=0, phase=0,
          sck=Pin(PIN_SCK), mosi=Pin(PIN_MOSI), miso=Pin(PIN_MISO))
cs = Pin(PIN_CS, Pin.OUT, value=1)


def strobe(cmd):
    cs.value(0); spi.write(bytes([cmd])); cs.value(1)

def read_status(addr):
    cs.value(0)
    spi.write(bytes([addr | 0xC0]))
    out = spi.read(1)
    cs.value(1)
    return out[0]


# Reset sequence per TI datasheet section 19.1.2.
cs.value(1); time.sleep_us(40)
cs.value(0); time.sleep_us(40)
cs.value(1); time.sleep_us(40)
strobe(SRES)
time.sleep_ms(5)

partnum = read_status(PARTNUM_REG)
version = read_status(VERSION_REG)
print(f"PARTNUM = 0x{partnum:02X}    (expect 0x00)")
print(f"VERSION = 0x{version:02X}    (expect 0x04, 0x14, etc — chip rev)")

if partnum == 0x00 and version not in (0x00, 0xFF):
    print("PASS: CC1101 responding on SPI")
elif partnum == 0xFF and version == 0xFF:
    print("FAIL: all-ones from CC1101")
    print("  - check VCC=3V3 (NOT 5V — CC1101 is 3V3 only)")
    print("  - check CSN wiring to GP13")
    print("  - check MISO wiring to GP12")
elif partnum == 0x00 and version == 0x00:
    print("FAIL: all-zeros from CC1101")
    print("  - is GND connected?")
    print("  - is CSN actually toggling (try LED in series with GP13)?")
else:
    print(f"FAIL: unexpected partnum/version 0x{partnum:02X}/0x{version:02X}")
    print("  Could be: counterfeit chip, wrong SPI mode, or a different RF module variant")
