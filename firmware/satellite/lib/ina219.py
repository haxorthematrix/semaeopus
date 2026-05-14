"""
INA219 minimal driver. Default config: 32 V FSR, 320 mV shunt, 12-bit,
continuous shunt+bus. Assumes a 0.1 Ω shunt (most breakout boards).
"""

import struct


class INA219:
    def __init__(self, i2c, addr=0x40, shunt_ohm=0.1):
        self.i2c = i2c
        self.addr = addr
        self.shunt = shunt_ohm
        # Calibration: cal = trunc(0.04096 / (current_LSB * R_shunt))
        # current_LSB = 0.0001 A → cal = 4096
        self.current_lsb = 0.0001
        i2c.writeto_mem(addr, 0x05, struct.pack(">H", 4096))
        # Config: 32 V FSR, gain /8, 12-bit, continuous shunt+bus
        i2c.writeto_mem(addr, 0x00, b"\x39\x9F")

    def _read_s16(self, reg):
        (v,) = struct.unpack(">h", self.i2c.readfrom_mem(self.addr, reg, 2))
        return v

    def _read_u16(self, reg):
        (v,) = struct.unpack(">H", self.i2c.readfrom_mem(self.addr, reg, 2))
        return v

    def bus_voltage(self):
        raw = self._read_u16(0x02) >> 3
        return raw * 0.004  # 4 mV / LSB

    def current_ma(self):
        return self._read_s16(0x04) * self.current_lsb * 1000
