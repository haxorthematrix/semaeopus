"""
ticks_ms / ticks_diff / ticks_add — cross-platform shim.

MicroPython exposes these directly on `time`. CPython doesn't. The OBC
modules import from this module so the same code runs on flight
hardware (MicroPython on RP2040) and inside the simulator (CPython on
the operator's laptop).

Semantics match MicroPython: a 30-bit unsigned millisecond counter that
wraps modulo 2**30. `ticks_diff(a, b)` returns a signed value in
(-2**29, 2**29).
"""

try:
    from time import ticks_ms, ticks_diff, ticks_add  # MicroPython
except ImportError:
    import time as _t

    _MASK = (1 << 30) - 1
    _HALF = 1 << 29

    def ticks_ms():
        return int(_t.monotonic() * 1000) & _MASK

    def ticks_diff(a, b):
        d = (a - b) & _MASK
        if d >= _HALF:
            d -= (1 << 30)
        return d

    def ticks_add(a, b):
        return (a + b) & _MASK
