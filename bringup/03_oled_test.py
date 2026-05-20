"""
Bring-up 03 — OLED display test.

Initializes the SSD1306, draws a frame, a checkerboard pattern, and a
banner. If the display lights up and shows recognizable patterns, PASS.
If the display stays dark, see the troubleshooting tree.

Requires `bringup/lib/ssd1306.py` (a copy of the satellite driver) OR
the upstream `micropython-ssd1306` package installed via mip:

    mpremote mip install ssd1306
"""

from machine import Pin, I2C
import time

try:
    import ssd1306                    # upstream micropython-ssd1306
except ImportError:
    try:
        from lib import ssd1306       # bringup/lib/ssd1306.py copy
    except ImportError:
        print("FAIL: no ssd1306 module. Either:")
        print("  - mpremote mip install ssd1306")
        print("  - or cp firmware/satellite/lib/ssd1306.py bringup/lib/ssd1306.py")
        raise SystemExit


bus = I2C(0, sda=Pin(4), scl=Pin(5), freq=400_000)
if 0x3C not in bus.scan() and 0x3D not in bus.scan():
    print("FAIL: SSD1306 not on bus 0 (scan returned ", bus.scan(), ")")
    raise SystemExit

addr = 0x3C if 0x3C in bus.scan() else 0x3D
oled = ssd1306.SSD1306_I2C(128, 64, bus, addr=addr)

oled.fill(0)
# Outer frame
oled.rect(0, 0, 128, 64, 1)
# Checkerboard in the lower half
for y in range(32, 64, 8):
    for x in range(0, 128, 8):
        if ((x // 8) + (y // 8)) & 1:
            oled.fill_rect(x, y, 8, 8, 1)
# Banner
oled.text("SEMAEOPUS BRINGUP", 0, 6)
oled.text("OLED  03", 0, 20)
oled.show()

time.sleep(1)
print("PASS: SSD1306 reachable at 0x%02X, frame + checkerboard drawn" % addr)
print("      (visually confirm the panel actually shows the pattern)")
