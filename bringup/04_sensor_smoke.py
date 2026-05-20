"""
Bring-up 04 — Sensor smoke.

Reads each housekeeping sensor once and prints the value with a
plausibility check. PASS only if all four sensors return believable
readings.

  BME280     — temperature must be 0–50 °C, pressure 800–1100 hPa
  MPU6050    — gyro |x|,|y|,|z| < 100 dps, accel Z in roughly ±1 g
  INA219     — bus voltage 3.0–5.5 V (whatever rail you're on)
  DS3231     — read date+time, must change after a 1-second wait

Requires the Semaeopus sensor drivers copied into `bringup/lib/`:

    mpremote cp -r firmware/satellite/lib :/bringup_lib
    mpremote run bringup/04_sensor_smoke.py
"""

import time
from machine import Pin, I2C

# Sensor drivers — try a local copy first, then assume the firmware is
# already on the device under /lib.
import sys
sys.path.insert(0, "/bringup_lib")
sys.path.insert(0, "/lib")

try:
    from bme280  import BME280
    from mpu6050 import MPU6050
    from ina219  import INA219
    from ds3231  import DS3231
except ImportError as e:
    print("FAIL: sensor drivers not on device.")
    print("Run:  mpremote cp -r firmware/satellite/lib :/bringup_lib")
    print("then retry. Underlying error:", e)
    raise SystemExit


i2c0 = I2C(0, sda=Pin(4),  scl=Pin(5),  freq=400_000)
i2c1 = I2C(1, sda=Pin(20), scl=Pin(21), freq=400_000)

scores = []


def check(name, ok, detail):
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name:10s}  {detail}")
    scores.append(ok)


# --- BME280 ---------------------------------------------------------
try:
    bme = BME280(i2c0, addr=0x76)
    t, p, h = bme.read_compensated()
    ok = (0 <= t <= 50) and (800 <= p <= 1100) and (0 <= h <= 100)
    check("BME280", ok, f"T={t:.2f}°C  P={p:.1f}hPa  RH={h:.1f}%")
except Exception as e:
    check("BME280", False, f"exception {e}")

# --- MPU6050 --------------------------------------------------------
try:
    mpu = MPU6050(i2c0, addr=0x68)
    gx, gy, gz = mpu.read_gyro_dps()
    ax, ay, az = mpu.read_accel_mg()
    ok = (abs(gx) < 100 and abs(gy) < 100 and abs(gz) < 100
          and 600 < abs(az) < 1400)        # ~1 g on Z
    check("MPU6050", ok,
          f"ω=({gx:+.1f}, {gy:+.1f}, {gz:+.1f}) dps  a_z={az}mg")
except Exception as e:
    check("MPU6050", False, f"exception {e}")

# --- INA219 ---------------------------------------------------------
try:
    ina = INA219(i2c0, addr=0x40)
    v = ina.bus_voltage()
    i = ina.current_ma()
    ok = 0.5 <= v <= 5.6
    check("INA219", ok, f"Vbus={v:.3f}V  I={i:.1f}mA")
except Exception as e:
    check("INA219", False, f"exception {e}")

# --- DS3231 ---------------------------------------------------------
try:
    rtc = DS3231(i2c1, addr=0x68)
    t1 = rtc.read_datetime()
    time.sleep(1.2)
    t2 = rtc.read_datetime()
    ok = t1 != t2
    check("DS3231", ok, f"t1={t1}  t2={t2}  advancing={'yes' if ok else 'NO'}")
except Exception as e:
    check("DS3231", False, f"exception {e}")

print()
if all(scores):
    print("PASS: all four sensors return plausible values")
else:
    print("FAIL: see [FAIL] rows above")
