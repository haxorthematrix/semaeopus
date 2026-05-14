"""DS3231 RTC minimal driver."""

import time


def _bcd2dec(b): return (b >> 4) * 10 + (b & 0x0F)
def _dec2bcd(d): return ((d // 10) << 4) | (d % 10)


class DS3231:
    def __init__(self, i2c, addr=0x68):
        self.i2c = i2c
        self.addr = addr

    def read_datetime(self):
        d = self.i2c.readfrom_mem(self.addr, 0x00, 7)
        return (
            2000 + _bcd2dec(d[6]),       # year
            _bcd2dec(d[5] & 0x1F),       # month
            _bcd2dec(d[4]),              # day
            _bcd2dec(d[2] & 0x3F),       # hour (24)
            _bcd2dec(d[1]),              # min
            _bcd2dec(d[0] & 0x7F),       # sec
        )

    def set_epoch(self, epoch):
        # Convert UNIX epoch to broken-down — MicroPython has time.localtime
        t = time.localtime(epoch)
        self.i2c.writeto_mem(self.addr, 0x00, bytes([
            _dec2bcd(t[5]),
            _dec2bcd(t[4]),
            _dec2bcd(t[3]),
            _dec2bcd(t[6] + 1),  # weekday 1-7
            _dec2bcd(t[2]),
            _dec2bcd(t[1]),
            _dec2bcd(t[0] - 2000),
        ]))
