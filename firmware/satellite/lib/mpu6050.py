"""MPU6050 — gyro/accel only, default ±250 dps / ±2 g."""

import struct


class MPU6050:
    def __init__(self, i2c, addr=0x68):
        self.i2c = i2c
        self.addr = addr
        # Wake from sleep
        i2c.writeto_mem(addr, 0x6B, b"\x00")
        # Gyro full-scale 250 dps (0x00), accel full-scale 2 g (0x00)
        i2c.writeto_mem(addr, 0x1B, b"\x00")
        i2c.writeto_mem(addr, 0x1C, b"\x00")

    def _read6(self, reg):
        return struct.unpack(">hhh", self.i2c.readfrom_mem(self.addr, reg, 6))

    def read_accel_mg(self):
        ax, ay, az = self._read6(0x3B)
        # 16384 LSB / g
        return (int(ax * 1000 / 16384),
                int(ay * 1000 / 16384),
                int(az * 1000 / 16384))

    def read_gyro_dps(self):
        gx, gy, gz = self._read6(0x43)
        # 131 LSB / (deg/s)
        return (gx / 131.0, gy / 131.0, gz / 131.0)
