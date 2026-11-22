"""
Ground-station radio front-end: Raspberry Pi Pico + CC1101 as a USB modem.

Used for the attacker radio (and for an operator ground station if you
build it from a Pico instead of a CYD). The modem logic lives in
firmware/shared/modem.py, shared with the CYD ground station, and speaks
the line protocol described in README.md, so every tool in
groundstation/ works with it.

Wiring (Pico pin numbers):
    CC1101 SCK  -> GP18 (pin 24)     CC1101 CSN  -> GP13 (pin 17)
    CC1101 MOSI -> GP19 (pin 25)     CC1101 GDO0 -> GP10 (pin 14)
    CC1101 MISO -> GP16 (pin 21)     CC1101 VCC  -> 3V3 OUT (pin 36), GND -> pin 38

MISO is on GP16 because SPI0 cannot use GP12. The on-board LED flashes
on every packet received or sent.

Deploy with:  tools/deploy.sh pico-modem /dev/ttyACM0
"""

from machine import Pin, SPI

from lib import cc1101
from lib.modem import Modem

CC1101_SPI_ID = 0
SPI_BAUD = 5_000_000
PIN_SPI_SCK = 18
PIN_SPI_MOSI = 19
PIN_SPI_MISO = 16
PIN_CC1101_CS = 13
PIN_CC1101_GDO0 = 10

RF_FREQ_HZ = 915_000_000          # power-on frequency; hosts can retune with CFG

try:
    led = Pin("LED", Pin.OUT)        # Pico, Pico W and Pico 2
except (TypeError, ValueError):
    led = Pin(25, Pin.OUT)


def blink(*_):
    led.toggle()


spi = SPI(CC1101_SPI_ID, baudrate=SPI_BAUD, polarity=0, phase=0,
          sck=Pin(PIN_SPI_SCK), mosi=Pin(PIN_SPI_MOSI), miso=Pin(PIN_SPI_MISO))
radio = cc1101.CC1101(spi, PIN_CC1101_CS, PIN_CC1101_GDO0)

modem = Modem(radio, RF_FREQ_HZ, name="gs-frontend", on_rx=blink, on_tx=blink)
modem.run(idle_hook=lambda: led.value(0), hook_period_ms=300)
