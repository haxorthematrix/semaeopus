"""
Fake sensor classes — same method signatures as the real drivers in
firmware/satellite/lib/, but generate plausible drifted values from a
simple state model. Used by the virtual satellite.

The "physics" is intentionally minimal — enough that learners see
non-static telemetry and can tell a real read from a stuck sensor, but
not so detailed that lesson outcomes depend on the sim model.
"""

import math
import random
import time


class FakeBME280:
    """Temp drifts ±0.3 °C around 22 °C with a slow sinusoid + noise.
    Pressure ~1013 hPa. Humidity ~40 % ± 5 %."""

    def __init__(self, t_base=22.0, p_base=1013.25, h_base=40.0):
        self.t_base = t_base
        self.p_base = p_base
        self.h_base = h_base
        self._t0 = time.monotonic()

    def read_compensated(self):
        dt = time.monotonic() - self._t0
        slow = math.sin(dt / 60.0)
        t = self.t_base + 0.3 * slow + random.uniform(-0.05, 0.05)
        p = self.p_base + 0.5 * math.sin(dt / 90.0) + random.uniform(-0.1, 0.1)
        h = self.h_base + 5 * math.sin(dt / 30.0) + random.uniform(-0.2, 0.2)
        return t, p, h


class FakeMPU6050:
    """Idle: ~1 g down, near-zero rates with small drift. Set
    ``disturb_for(seconds)`` to spike gyro rates for a "detumble"
    lesson scenario."""

    def __init__(self):
        self._disturb_until = 0.0
        self._t0 = time.monotonic()

    def disturb_for(self, seconds):
        self._disturb_until = time.monotonic() + seconds

    def read_gyro_dps(self):
        if time.monotonic() < self._disturb_until:
            return (random.uniform(-30, 30),
                    random.uniform(-30, 30),
                    random.uniform(-30, 30))
        return (random.uniform(-0.5, 0.5),
                random.uniform(-0.5, 0.5),
                random.uniform(-0.5, 0.5))

    def read_accel_mg(self):
        # ~1g on Z; small noise.
        return (int(random.uniform(-20, 20)),
                int(random.uniform(-20, 20)),
                int(1000 + random.uniform(-10, 10)))


class FakeINA219:
    """Bus voltage near 3.7 V, current swings ±20 mA around a 50 mA
    baseline. Daylight phase boosts the current a bit (solar input)."""

    def __init__(self):
        self._t0 = time.monotonic()

    def bus_voltage(self):
        return 3.7 + 0.05 * math.sin((time.monotonic() - self._t0) / 30.0)

    def current_ma(self):
        phase = math.sin(2 * math.pi * (time.monotonic() - self._t0) / 90.0)
        bias = 30 if phase > -0.2 else -10
        return bias + random.uniform(-5, 5)


class FakeDS3231:
    """Wall-clock RTC. Survives `set_epoch`. Read returns a
    broken-down tuple matching the real driver."""

    def __init__(self):
        self._epoch = int(time.time())
        self._t0 = time.monotonic()

    def _now(self):
        return self._epoch + (time.monotonic() - self._t0)

    def read_datetime(self):
        t = time.gmtime(self._now())
        return (t.tm_year, t.tm_mon, t.tm_mday,
                t.tm_hour, t.tm_min, t.tm_sec)

    def set_epoch(self, epoch):
        self._epoch = int(epoch)
        self._t0 = time.monotonic()


class FakeOLED:
    """No-op stand-in for SSD1306_I2C. Captures the last shown buffer
    as a list of text lines for inspection in tests."""

    def __init__(self):
        self.last = []
        self._draft = []

    def fill(self, c):
        self._draft = []

    def text(self, s, x, y):
        self._draft.append((y, s))

    def show(self):
        self.last = [s for _, s in sorted(self._draft)]
