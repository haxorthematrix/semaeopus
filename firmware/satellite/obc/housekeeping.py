"""
Housekeeping telemetry: temp/pressure/humidity from BME280, plus a
boot-counter and uptime. Encoded as a compact fixed-layout struct so
the packet fits comfortably in a CC1101 frame.

HK_TLM payload layout (16 bytes, big-endian):

    u32  uptime_ms
    u16  boot_count
    i16  temp_c_q8     # temperature in °C * 256
    u16  pressure_hpa  # hPa
    u16  humidity_pct_q8
    u8   mode
    u8   flags         # bit0 = payload armed, bit1 = safe-latched
    u16  reserved
"""

import struct
from .compat import ticks_ms, ticks_diff


def _s16(x):
    v = int(x)
    if v >  32767: return  32767
    if v < -32768: return -32768
    return v


class Housekeeping:
    def __init__(self, bme280, mode_state, boot_count):
        self.bme = bme280
        self.mode = mode_state
        self.boot_count = boot_count
        self._t0 = ticks_ms()

    def encode(self):
        try:
            t_c, p_hpa, h_pct = self.bme.read_compensated()
        except Exception:
            t_c, p_hpa, h_pct = 22.0, 1013.25, 40.0
        uptime = ticks_diff(ticks_ms(), self._t0) & 0xFFFFFFFF
        return struct.pack(
            ">IHhHHBBH",
            uptime,
            self.boot_count & 0xFFFF,
            _s16(t_c * 256),
            int(p_hpa) & 0xFFFF,
            int(h_pct * 256) & 0xFFFF,
            self.mode.current & 0xFF,
            self.mode.flags & 0xFF,
            0,
        )
