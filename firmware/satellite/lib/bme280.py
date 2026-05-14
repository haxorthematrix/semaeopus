"""
Bosch BME280 minimal driver. Reads chip calibration on init, returns
compensated (T °C, P hPa, RH %).

This is a slimmed-down port of Adafruit's algorithm — enough for
housekeeping telemetry, not flight-grade.
"""

import struct
import time


class BME280:
    REG_ID       = 0xD0
    REG_RESET    = 0xE0
    REG_CTRL_HUM = 0xF2
    REG_CTRL_MEAS= 0xF4
    REG_CONFIG   = 0xF5
    REG_DATA     = 0xF7
    REG_CALIB1   = 0x88
    REG_CALIB2   = 0xE1

    def __init__(self, i2c, addr=0x76):
        self.i2c = i2c
        self.addr = addr
        chip = self.i2c.readfrom_mem(addr, self.REG_ID, 1)[0]
        if chip not in (0x60, 0x58):
            raise OSError("BME280 not found (id 0x%02x)" % chip)
        self._read_calibration()
        self.i2c.writeto_mem(addr, self.REG_CTRL_HUM,  b"\x01")    # H oversample x1
        self.i2c.writeto_mem(addr, self.REG_CTRL_MEAS, b"\x27")    # T x1, P x1, normal
        self.i2c.writeto_mem(addr, self.REG_CONFIG,    b"\xA0")    # 1000 ms standby

    def _read_calibration(self):
        c1 = self.i2c.readfrom_mem(self.addr, self.REG_CALIB1, 24)
        c2 = self.i2c.readfrom_mem(self.addr, self.REG_CALIB2, 7)
        (self.dT1,) = struct.unpack("<H", c1[0:2])
        (self.dT2, self.dT3) = struct.unpack("<hh", c1[2:6])
        (self.dP1,) = struct.unpack("<H", c1[6:8])
        (self.dP2, self.dP3, self.dP4, self.dP5,
         self.dP6, self.dP7, self.dP8, self.dP9) = struct.unpack("<hhhhhhhh", c1[8:24])
        self.dH1 = c1[23] if len(c1) > 23 else 0
        # Humidity
        self.dH1 = self.i2c.readfrom_mem(self.addr, 0xA1, 1)[0]
        (self.dH2, ) = struct.unpack("<h", c2[0:2])
        self.dH3 = c2[2]
        e4, e5, e6 = c2[3], c2[4], c2[5]
        self.dH4 = (e4 << 4) | (e5 & 0x0F)
        self.dH5 = (e6 << 4) | (e5 >> 4)
        self.dH6 = struct.unpack("<b", bytes([c2[6]]))[0]

    def read_compensated(self):
        d = self.i2c.readfrom_mem(self.addr, self.REG_DATA, 8)
        adc_P = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_T = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
        adc_H = (d[6] << 8)  |  d[7]

        var1 = (((adc_T >> 3) - (self.dT1 << 1)) * self.dT2) >> 11
        var2 = (((((adc_T >> 4) - self.dT1) * ((adc_T >> 4) - self.dT1)) >> 12) * self.dT3) >> 14
        t_fine = var1 + var2
        T = ((t_fine * 5 + 128) >> 8) / 100.0

        var1p = t_fine - 128000
        var2p = var1p * var1p * self.dP6
        var2p = var2p + ((var1p * self.dP5) << 17)
        var2p = var2p + (self.dP4 << 35)
        var1p = ((var1p * var1p * self.dP3) >> 8) + ((var1p * self.dP2) << 12)
        var1p = (((1 << 47) + var1p) * self.dP1) >> 33
        if var1p == 0:
            P = 0
        else:
            p = 1048576 - adc_P
            p = (((p << 31) - var2p) * 3125) // var1p
            var1p = (self.dP9 * (p >> 13) * (p >> 13)) >> 25
            var2p = (self.dP8 * p) >> 19
            p = ((p + var1p + var2p) >> 8) + (self.dP7 << 4)
            P = p / 25600.0  # hPa

        v_x1 = t_fine - 76800
        v_x1 = (((((adc_H << 14) - (self.dH4 << 20) - (self.dH5 * v_x1)) +
                  16384) >> 15) *
                (((((((v_x1 * self.dH6) >> 10) *
                     (((v_x1 * self.dH3) >> 11) + 32768)) >> 10) + 2097152) *
                  self.dH2 + 8192) >> 14))
        v_x1 = v_x1 - (((((v_x1 >> 15) * (v_x1 >> 15)) >> 7) * self.dH1) >> 4)
        v_x1 = max(0, min(v_x1, 419430400))
        H = (v_x1 >> 12) / 1024.0

        return T, P, H
