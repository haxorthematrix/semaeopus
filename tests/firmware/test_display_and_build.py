"""CYD display driver output, and MicroPython compilation of every firmware file."""
import glob
import os
import sys

import pytest

from . import mpsim
from .mpsim import Board

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_display_driver(staged, monkeypatch):
    b = Board(radio_spi=2, cs=5, gdo0=27)
    mpsim.BOARD = b
    saved = {k: sys.modules.get(k) for k in ("machine", "framebuf")}
    sys.modules["machine"], sys.modules["framebuf"] = mpsim.machine, mpsim.framebuf
    sys.path.insert(0, staged["cyd-ground"])
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("cyd_display_t", staged["cyd-ground"] + "/lib/cyd_display.py")
        d = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(d)
        writes = []

        class RecSPI(mpsim.SPI):
            def write(self, buf):
                writes.append(bytes(buf))

        d.SPI = RecSPI
        monkeypatch.setattr(d.time, "sleep_ms", lambda ms: None, raising=False)
        scr = d.Display()
        assert [w[0] for w in writes if len(w) == 1][:8] == [0x01, 0x11, 0x3A, 0x55, 0x36, 0x28, 0x20, 0x29]
        writes.clear()
        scr.text("AB", 16, 40, d.WHITE, d.BLACK, scale=2)
        assert writes[writes.index(b"\x2a") + 1] == bytes([0, 16, 0, 47])
        assert writes[writes.index(b"\x2b") + 1] == bytes([0, 40, 0, 55])
        pix = b"".join(writes[writes.index(b"\x2c") + 1:])
        exp = bytearray()
        for r in range(8):
            row = bytearray()
            for ch in "AB":
                byte = (ord(ch) * 7 + r * 13) & 0xFF
                for k in range(8):
                    c = d.WHITE if byte & (0x80 >> k) else d.BLACK
                    row += bytes([c >> 8, c & 0xFF]) * 2
            exp += row * 2
        assert pix == bytes(exp)
        writes.clear()
        scr.text("AB", 16, 40, d.WHITE, d.BLACK, scale=2)
        assert writes == []                                     # unchanged text is not redrawn
        writes.clear()
        scr.fill_rect(300, 230, 50, 50, d.RED)
        assert writes[writes.index(b"\x2a") + 1] == bytes([1, 44, 1, 63])
        assert writes[writes.index(b"\x2b") + 1] == bytes([0, 230, 0, 239])
    finally:
        sys.path.remove(staged["cyd-ground"])
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def test_all_firmware_compiles_with_micropython(staged):
    mpy_cross = pytest.importorskip("mpy_cross")
    files = sorted({f for d in staged.values() for f in glob.glob(d + "/**/*.py", recursive=True)}
                   | set(glob.glob(ROOT + "/bringup/**/*.py", recursive=True)))
    for f in files:
        proc = mpy_cross.run("-o", os.devnull, f)
        assert proc.wait() == 0, f
