"""
Attitude / determination subsystem (very simplified).

Reads MPU6050 gyro + accel, reports rate vector and a synthesized
quaternion. Real ADCS does sensor fusion (e.g. Madgwick / EKF); here
we just expose raw rates, which is realistic for early-mission "ADCS
detumble" telemetry.

ADCS_TLM layout (16 bytes):
    i16 gyro_x_dps_q8  (deg/s * 256)
    i16 gyro_y_dps_q8
    i16 gyro_z_dps_q8
    i16 accel_x_mg
    i16 accel_y_mg
    i16 accel_z_mg
    u8  wheel_rpm_high   (simulated reaction wheel)
    u8  wheel_rpm_low
    u8  detumble_flag
    u8  reserved
"""

import struct


def _s16(x):
    v = int(x)
    if v >  32767: return  32767
    if v < -32768: return -32768
    return v


class ADCS:
    def __init__(self, mpu):
        self.mpu = mpu
        self.wheel_rpm = 0
        self.detumble = False

    def encode(self):
        try:
            gx, gy, gz = self.mpu.read_gyro_dps()
            ax, ay, az = self.mpu.read_accel_mg()
        except Exception:
            gx = gy = gz = 0.0
            ax = ay = az = 0
        # very crude "detumble" heuristic
        omega = (gx * gx + gy * gy + gz * gz) ** 0.5
        self.detumble = omega > 5.0
        return struct.pack(
            ">hhhhhhHBB",
            _s16(gx * 256), _s16(gy * 256), _s16(gz * 256),
            _s16(ax),       _s16(ay),       _s16(az),
            self.wheel_rpm & 0xFFFF,
            1 if self.detumble else 0,
            0,
        )
