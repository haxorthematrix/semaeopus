"""
SSD1306 OLED driver — vendor reference port, public domain.

Trimmed to the I²C variant Semaeopus uses. If you'd rather pull in the
upstream `micropython-ssd1306` package via mip/upip, delete this file
and `import ssd1306` from the standard location.
"""

import framebuf


SET_CONTRAST        = 0x81
SET_ENTIRE_ON       = 0xA4
SET_NORM_INV        = 0xA6
SET_DISP            = 0xAE
SET_MEM_ADDR        = 0x20
SET_COL_ADDR        = 0x21
SET_PAGE_ADDR       = 0x22
SET_DISP_START_LINE = 0x40
SET_SEG_REMAP       = 0xA0
SET_MUX_RATIO       = 0xA8
SET_COM_OUT_DIR     = 0xC0
SET_DISP_OFFSET     = 0xD3
SET_COM_PIN_CFG     = 0xDA
SET_DISP_CLK_DIV    = 0xD5
SET_PRECHARGE       = 0xD9
SET_VCOM_DESEL      = 0xDB
SET_CHARGE_PUMP     = 0x8D


class SSD1306_I2C(framebuf.FrameBuffer):
    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self.width  = width
        self.height = height
        self.pages  = height // 8
        self.buffer = bytearray(self.pages * width)
        self.i2c    = i2c
        self.addr   = addr
        self.external_vcc = external_vcc
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)
        self.init_display()

    def write_cmd(self, cmd):
        self.i2c.writeto(self.addr, b"\x80" + bytes([cmd]))

    def write_data(self, buf):
        self.i2c.writeto(self.addr, b"\x40" + buf)

    def init_display(self):
        for cmd in (
            SET_DISP | 0x00,
            SET_MEM_ADDR, 0x00,
            SET_DISP_START_LINE | 0x00,
            SET_SEG_REMAP | 0x01,
            SET_MUX_RATIO, self.height - 1,
            SET_COM_OUT_DIR | 0x08,
            SET_DISP_OFFSET, 0x00,
            SET_COM_PIN_CFG, 0x02 if self.height == 32 else 0x12,
            SET_DISP_CLK_DIV, 0x80,
            SET_PRECHARGE, 0x22 if self.external_vcc else 0xF1,
            SET_VCOM_DESEL, 0x30,
            SET_CONTRAST, 0xFF,
            SET_ENTIRE_ON,
            SET_NORM_INV,
            SET_CHARGE_PUMP, 0x10 if self.external_vcc else 0x14,
            SET_DISP | 0x01,
        ):
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    def show(self):
        self.write_cmd(SET_COL_ADDR)
        self.write_cmd(0)
        self.write_cmd(self.width - 1)
        self.write_cmd(SET_PAGE_ADDR)
        self.write_cmd(0)
        self.write_cmd(self.pages - 1)
        self.write_data(self.buffer)
