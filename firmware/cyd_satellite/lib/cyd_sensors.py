"""
Sensor stand-ins for the CYD satellite.

The original FlatSat used a BME280, MPU6050, INA219 and DS3231 on I2C.
The CYD has none of those, so each is replaced by an object with the same
methods the OBC modules already call:

  LightSensor     the CYD's own LDR (GPIO34): the satellite's sun sensor
  PowerSensor     INA219 stand-in; solar charge current follows the LDR,
                  so shining a light on the board changes EPS telemetry
  EnvSensor       BME280 stand-in; slow, plausible drift
  ImuSensor       MPU6050 stand-in; press the BOOT button to tumble the
                  satellite for 10 s (detumble telemetry)
  SoftRtc         DS3231 stand-in for the TIME_SET command
"""

import math
import random
import time
from machine import ADC, Pin


def _u(a, b):
    """Uniform random in [a, b] using only getrandbits (always present)."""
    return a + (b - a) * random.getrandbits(16) / 65535


def _secs():
    return time.ticks_ms() / 1000


class LightSensor:
    """CYD LDR on GPIO34. Bright light gives a LOW reading on this board.

    The raw range varies between boards, so the sensor auto-ranges: it
    tracks the darkest and brightest readings it has seen and reports
    0..1 between them. Cover the LDR and shine a light on it once after
    boot to calibrate. Set LDR_BRIGHT_IS_LOW = False in config.py if your
    board reads the other way round."""

    def __init__(self, pin=34, bright_is_low=True):
        self.adc = ADC(Pin(pin))
        try:
            self.adc.atten(ADC.ATTN_0DB)    # the LDR swing is small; max sensitivity
        except Exception:
            pass
        self.bright_is_low = bright_is_low
        self.lo = None
        self.hi = None

    def raw(self):
        return self.adc.read_u16()

    def level(self):
        v = self.raw()
        if self.lo is None:
            self.lo = self.hi = v
        self.lo = min(self.lo, v)
        self.hi = max(self.hi, v)
        span = self.hi - self.lo
        if span < 2000:                     # not calibrated yet: assume half sun
            return 0.5
        f = (v - self.lo) / span
        return 1.0 - f if self.bright_is_low else f


class PowerSensor:
    """INA219 stand-in. Positive current = charging from the 'solar array'."""

    def __init__(self, light):
        self.light = light

    def bus_voltage(self):
        return 3.6 + 0.5 * self.light.level() + _u(-0.01, 0.01)

    def current_ma(self):
        return int(-60 + 260 * self.light.level() + _u(-3, 3))


class EnvSensor:
    """BME280 stand-in: about 22 C, 1013 hPa, 40 % RH with slow drift."""

    def read_compensated(self):
        t = _secs()
        return (22.0 + 0.3 * math.sin(t / 60) + _u(-0.05, 0.05),
                1013.25 + 0.5 * math.sin(t / 90) + _u(-0.1, 0.1),
                40.0 + 5 * math.sin(t / 30) + _u(-0.2, 0.2))


class ImuSensor:
    """MPU6050 stand-in. The BOOT button (GPIO0) starts a 10 s tumble."""

    def __init__(self, button_pin=0):
        self.button = Pin(button_pin, Pin.IN, Pin.PULL_UP)
        self._tumble_until = 0
        self.button.irq(trigger=Pin.IRQ_FALLING, handler=self._pressed)

    def _pressed(self, _pin):
        self._tumble_until = time.ticks_add(time.ticks_ms(), 10_000)

    def tumbling(self):
        return time.ticks_diff(self._tumble_until, time.ticks_ms()) > 0

    def read_gyro_dps(self):
        r = 30 if self.tumbling() else 0.5
        return (_u(-r, r), _u(-r, r), _u(-r, r))

    def read_accel_mg(self):
        return (int(_u(-20, 20)), int(_u(-20, 20)), int(1000 + _u(-10, 10)))


class SoftRtc:
    """DS3231 stand-in: keeps epoch time from the last TIME_SET command."""

    def __init__(self):
        self._epoch = 0
        self._set_at = time.ticks_ms()

    def set_epoch(self, epoch):
        self._epoch = epoch
        self._set_at = time.ticks_ms()

    def epoch(self):
        return self._epoch + time.ticks_diff(time.ticks_ms(), self._set_at) // 1000
