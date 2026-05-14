"""
Electrical Power Subsystem.

INA219 measures bus voltage and shunt current. We use those values
plus a toy "battery" model: SoC drifts ±1 % per minute around 60 %,
biased by current draw, with daylight/eclipse simulated as a sine
wave on a slow timer. Lessons L05 and L06 trigger EPS-related events.

EPS_TLM layout (12 bytes):
    u16 vbat_mv
    i16 ibat_ma
    u16 vbus_mv
    u16 ibus_ma
    u8  soc_pct
    u8  daylight_flag
    u16 reserved
"""

import struct
import math
from .compat import ticks_ms, ticks_diff


def _s16(x):
    v = int(x)
    if v >  32767: return  32767
    if v < -32768: return -32768
    return v


class EPS:
    def __init__(self, ina):
        self.ina = ina
        self._t0 = ticks_ms()
        self.soc = 60.0

    def encode(self):
        try:
            vbus_v = self.ina.bus_voltage()
            ibus_ma = self.ina.current_ma()
        except Exception:
            vbus_v, ibus_ma = 3.7, 50
        # Simulated daylight: 90 min orbit, 60 % illuminated.
        t_min = ticks_diff(ticks_ms(), self._t0) / 60000.0
        phase = math.sin(2 * math.pi * t_min / 90.0)
        daylight = phase > -0.2
        # SoC drift
        drift = 0.05 if daylight else -0.10
        self.soc = max(5.0, min(100.0, self.soc + drift))
        return struct.pack(
            ">HhHHBBH",
            int(vbus_v * 1000) & 0xFFFF,   # using bus as "battery" stand-in
            _s16(ibus_ma),
            int(vbus_v * 1000) & 0xFFFF,
            int(abs(ibus_ma)) & 0xFFFF,
            int(self.soc) & 0xFF,
            1 if daylight else 0,
            0,
        )
