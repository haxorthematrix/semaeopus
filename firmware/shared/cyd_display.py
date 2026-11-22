"""
Minimal display driver for the CYD's 2.8" 320 x 240 panel.

Works with the ILI9341 on the classic ESP32-2432S028R and the ST7789 on
the USB-C "CYD2USB" revision, using only commands both chips share.
No external library: text uses MicroPython's built-in 8 x 8 framebuf
font, drawn in scale 1, 2 or 3 and streamed to the panel row by row, so
no full-screen buffer is needed (the ESP32 has too little RAM for one).

If the picture is upside down, mirrored or colour-inverted, change
DISPLAY_MADCTL / DISPLAY_INVERT in config.py (see notes there).
"""

from machine import Pin, SPI
import framebuf
import time


def rgb(r, g, b):
    """24-bit colour to RGB565."""
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


BLACK  = rgb(0, 0, 0)
WHITE  = rgb(255, 255, 255)
GREY   = rgb(140, 140, 140)
DIM    = rgb(70, 70, 70)
GREEN  = rgb(40, 220, 90)
AMBER  = rgb(255, 180, 0)
RED    = rgb(255, 60, 60)
CYAN   = rgb(0, 200, 255)
BLUE   = rgb(60, 120, 255)

WIDTH, HEIGHT = 320, 240


class Display:
    def __init__(self, spi_id=1, sck=14, mosi=13, miso=12, cs=15, dc=2, bl=21,
                 baud=27_000_000, madctl=0x28, invert=False):
        self.spi = SPI(spi_id, baudrate=baud, polarity=0, phase=0,
                       sck=Pin(sck), mosi=Pin(mosi), miso=Pin(miso))
        self.cs = Pin(cs, Pin.OUT, value=1)
        self.dc = Pin(dc, Pin.OUT, value=1)
        self.bl = Pin(bl, Pin.OUT, value=0)
        self._tables = {}
        self._cache = {}
        self._init(madctl, invert)
        self.fill(BLACK)
        self.bl.value(1)

    # ---- low level -----------------------------------------------------------

    def _cmd(self, c, data=None):
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(bytes([c]))
        if data:
            self.dc.value(1)
            self.spi.write(data)
        self.cs.value(1)

    def _init(self, madctl, invert):
        self._cmd(0x01)                     # software reset (panel RST is tied to EN)
        time.sleep_ms(150)
        self._cmd(0x11)                     # sleep out
        time.sleep_ms(120)
        self._cmd(0x3A, b"\x55")            # 16-bit RGB565
        self._cmd(0x36, bytes([madctl]))    # orientation + colour order
        self._cmd(0x21 if invert else 0x20) # inversion on / off
        self._cmd(0x29)                     # display on
        time.sleep_ms(20)

    def _window(self, x0, y0, x1, y1):
        self._cmd(0x2A, bytes([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF]))
        self._cmd(0x2B, bytes([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF]))
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(b"\x2C")             # memory write
        self.dc.value(1)                    # stays selected for pixel data

    # ---- drawing -------------------------------------------------------------

    def fill_rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0:
            return
        x1 = min(WIDTH - 1, x + w - 1)
        y1 = min(HEIGHT - 1, y + h - 1)
        w = x1 - x + 1
        row = bytes([color >> 8, color & 0xFF]) * w
        self._window(x, y, x1, y1)
        for _ in range(y1 - y + 1):
            self.spi.write(row)
        self.cs.value(1)

    def fill(self, color):
        self.fill_rect(0, 0, WIDTH, HEIGHT, color)

    def _lut(self, fg, bg, scale):
        """Per-colour cache: font byte (8 pixels) -> 8 * scale RGB565 pixels.
        Filled lazily, so it only holds the byte patterns actually drawn."""
        key = (fg, bg, scale)
        lut = self._tables.get(key)
        if lut is None:
            if len(self._tables) >= 6:      # keep RAM use bounded
                self._tables = {}
            lut = self._tables[key] = {}
        return lut

    def text(self, s, x, y, fg=WHITE, bg=BLACK, scale=1, width=None):
        """Draw s at (x, y). width (in characters) pads with spaces so a
        shorter string fully overwrites a longer one drawn earlier.
        Skips the redraw if the same text is already there."""
        if width is not None:
            s = (s + " " * width)[:width]
        max_chars = (WIDTH - x) // (8 * scale)
        s = s[:max_chars]
        if not s:
            return
        key = (x, y)
        state = (s, fg, bg, scale)
        if self._cache.get(key) == state:
            return
        self._cache[key] = state
        n = len(s)
        mono = bytearray(n * 8)
        fb = framebuf.FrameBuffer(mono, n * 8, 8, framebuf.MONO_HLSB)
        fb.text(s, 0, 0, 1)
        lut = self._lut(fg, bg, scale)
        on = bytes([fg >> 8, fg & 0xFF]) * scale
        off = bytes([bg >> 8, bg & 0xFF]) * scale
        self._window(x, y, x + n * 8 * scale - 1, y + 8 * scale - 1)
        for r in range(8):
            parts = []
            for i in range(n):
                b = mono[r * n + i]
                px = lut.get(b)
                if px is None:
                    px = b"".join(on if b & (0x80 >> k) else off for k in range(8))
                    lut[b] = px
                parts.append(px)
            row = b"".join(parts)
            for _ in range(scale):
                self.spi.write(row)
        self.cs.value(1)

    def bar(self, x, y, w, h, frac, fg, bg=DIM):
        """Horizontal bar gauge, frac in 0..1."""
        frac = max(0.0, min(1.0, frac))
        filled = int(w * frac)
        key = (x, y, "bar")
        state = (filled, fg, bg)
        if self._cache.get(key) == state:
            return
        self._cache[key] = state
        self.fill_rect(x, y, filled, h, fg)
        self.fill_rect(x + filled, y, w - filled, h, bg)
