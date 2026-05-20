"""
Bring-up 01 — MicroPython sanity.

Blinks the Pico's onboard LED ten times and prints PASS. If you don't
see the LED blink AND don't see the PASS line, MicroPython isn't running
properly. Re-flash the .uf2.

On the Pico W the onboard LED is wired to the WL_GPIO0 pin of the wifi
chip, not GP25; this script handles both.
"""

import time
from machine import Pin

try:
    led = Pin("LED", Pin.OUT)         # Pico W / Pico 2 W
    where = "Pin('LED')"
except (TypeError, ValueError):
    led = Pin(25, Pin.OUT)            # Pico / Pico 2
    where = "Pin(25)"

print("blinking via", where)
for i in range(10):
    led.toggle()
    time.sleep(0.15)
led.value(0)

print("PASS: pico alive, MicroPython responsive")
