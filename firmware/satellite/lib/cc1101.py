"""
Minimal CC1101 driver for MicroPython on RP2040.

Implements the subset Semaeopus needs:
  - reset, configure for 2-GFSK 9600 bps
  - set frequency (433 MHz / 915 MHz)
  - set sync word
  - transmit a variable-length packet (length-byte first)
  - receive (blocking, or non-blocking via GDO0 IRQ)

Not a full driver. Refer to TI DN005 / DN509 for the magic register
values. The defaults below were exported from TI's SmartRF Studio for
9600 bps 2-GFSK with a 58 kHz IF and 4.8 kHz deviation.
"""

from machine import Pin, SPI
import time

# --- Strobe commands ---
SRES    = 0x30
SFSTXON = 0x31
SXOFF   = 0x32
SCAL    = 0x33
SRX     = 0x34
STX     = 0x35
SIDLE   = 0x36
SFRX    = 0x3A
SFTX    = 0x3B
SNOP    = 0x3D

# --- Register addresses (selected) ---
IOCFG2  = 0x00
IOCFG0  = 0x02
FIFOTHR = 0x03
SYNC1   = 0x04
SYNC0   = 0x05
PKTLEN  = 0x06
PKTCTRL1= 0x07
PKTCTRL0= 0x08
FSCTRL1 = 0x0B
FREQ2   = 0x0D
FREQ1   = 0x0E
FREQ0   = 0x0F
MDMCFG4 = 0x10
MDMCFG3 = 0x11
MDMCFG2 = 0x12
MDMCFG1 = 0x13
MDMCFG0 = 0x14
DEVIATN = 0x15
MCSM1   = 0x17
MCSM0   = 0x18
FOCCFG  = 0x19
AGCCTRL2= 0x1B
FREND0  = 0x22
FSCAL3  = 0x23
FSCAL2  = 0x24
FSCAL1  = 0x25
FSCAL0  = 0x26
TEST2   = 0x2C
TEST1   = 0x2D
TEST0   = 0x2E
PATABLE = 0x3E
TXFIFO  = 0x3F
RXFIFO  = 0x3F

# Status registers (must be read with burst bit set)
PKTSTATUS = 0x38
RXBYTES   = 0x3B
MARCSTATE = 0x35

XTAL_HZ = 26_000_000


class CC1101:
    def __init__(self, spi, cs_pin, gdo0_pin=None):
        self.spi = spi
        self.cs = Pin(cs_pin, Pin.OUT, value=1)
        self.gdo0 = Pin(gdo0_pin, Pin.IN) if gdo0_pin is not None else None
        self._buf = bytearray(1)

    # ---- low-level helpers -------------------------------------------------

    def _strobe(self, cmd):
        self.cs.value(0)
        self._buf[0] = cmd
        self.spi.write(self._buf)
        self.cs.value(1)

    def _write_reg(self, addr, val):
        self.cs.value(0)
        self.spi.write(bytes([addr & 0x3F, val & 0xFF]))
        self.cs.value(1)

    def _read_reg(self, addr):
        # Single-byte read: addr | 0x80
        self.cs.value(0)
        self.spi.write(bytes([addr | 0x80]))
        out = self.spi.read(1)
        self.cs.value(1)
        return out[0]

    def _read_status(self, addr):
        # Status registers need burst-read bit (0xC0) to avoid the
        # CC1101 mapping collision with strobe commands.
        self.cs.value(0)
        self.spi.write(bytes([addr | 0xC0]))
        out = self.spi.read(1)
        self.cs.value(1)
        return out[0]

    def _write_burst(self, addr, data):
        self.cs.value(0)
        self.spi.write(bytes([addr | 0x40]) + bytes(data))
        self.cs.value(1)

    def _read_burst(self, addr, n):
        self.cs.value(0)
        self.spi.write(bytes([addr | 0xC0]))
        out = self.spi.read(n)
        self.cs.value(1)
        return out

    # ---- bring-up ----------------------------------------------------------

    def reset(self):
        self.cs.value(1); time.sleep_us(40)
        self.cs.value(0); time.sleep_us(40)
        self.cs.value(1); time.sleep_us(40)
        self._strobe(SRES)
        time.sleep_ms(5)

    def configure_default(self, freq_hz, sync_word, bitrate_bps,
                          deviation_hz, rx_bw_hz, tx_power_dbm=0):
        # Most registers come from SmartRF Studio export for
        # 433.92 MHz, 9.6 kBaud, 4.8 kHz dev, 58 kHz BW, 2-GFSK.
        self._write_reg(IOCFG0,  0x06)   # GDO0: asserts on sync, deasserts at packet end
        self._write_reg(IOCFG2,  0x29)   # GDO2: CHIP_RDYn (unused)
        self._write_reg(FIFOTHR, 0x47)
        self._write_reg(PKTLEN,  0xFF)   # max 255 bytes; variable len header drives actual size
        self._write_reg(PKTCTRL1,0x04)   # APPEND_STATUS=1
        self._write_reg(PKTCTRL0,0x05)   # WHITENING=0, VAR_LEN, CRC enabled, no FEC
        self._write_reg(FSCTRL1, 0x06)
        self._write_reg(MDMCFG4, 0xF8)   # CHANBW=58 kHz, DRATE_E=8
        self._write_reg(MDMCFG3, 0x83)   # DRATE_M=131  ->  ~9.6 kBaud
        self._write_reg(MDMCFG2, 0x13)   # 2-GFSK, sync 16/16, no Manchester
        self._write_reg(MDMCFG1, 0x22)
        self._write_reg(MDMCFG0, 0xF8)
        self._write_reg(DEVIATN, 0x35)   # ~4.8 kHz
        self._write_reg(MCSM1,   0x30)   # CCA, then IDLE after TX/RX
        self._write_reg(MCSM0,   0x18)   # auto-cal from IDLE to RX/TX
        self._write_reg(FOCCFG,  0x16)
        self._write_reg(AGCCTRL2,0x43)
        self._write_reg(FREND0,  0x10)
        self._write_reg(FSCAL3,  0xE9)
        self._write_reg(FSCAL2,  0x2A)
        self._write_reg(FSCAL1,  0x00)
        self._write_reg(FSCAL0,  0x1F)
        self._write_reg(TEST2,   0x81)
        self._write_reg(TEST1,   0x35)
        self._write_reg(TEST0,   0x09)

        self.set_frequency(freq_hz)
        self.set_sync_word(sync_word)
        self.set_tx_power(tx_power_dbm)

    def set_frequency(self, freq_hz):
        freq_word = int((freq_hz << 16) / XTAL_HZ)
        self._write_reg(FREQ2, (freq_word >> 16) & 0xFF)
        self._write_reg(FREQ1, (freq_word >>  8) & 0xFF)
        self._write_reg(FREQ0,  freq_word        & 0xFF)

    def set_sync_word(self, sync16):
        self._write_reg(SYNC1, (sync16 >> 8) & 0xFF)
        self._write_reg(SYNC0,  sync16       & 0xFF)

    def set_tx_power(self, dbm):
        # CC1101 PATABLE entries for 433 MHz, single-byte mode.
        table = { -30: 0x12, -20: 0x0E, -15: 0x1D, -10: 0x34,
                    0: 0x60,  +5: 0x84, +7: 0xC8, +10: 0xC0 }
        # Pick closest <= requested.
        chosen = 0x60
        for k in sorted(table.keys()):
            if k <= dbm:
                chosen = table[k]
        self._write_reg(PATABLE, chosen)

    # ---- packet I/O --------------------------------------------------------

    def transmit(self, payload):
        """Variable-length packet: payload[0] must be the length byte."""
        self._strobe(SIDLE)
        self._strobe(SFTX)
        self._write_burst(TXFIFO, payload)
        self._strobe(STX)
        # Wait for GDO0 to deassert (= packet sent), or poll MARCSTATE.
        if self.gdo0:
            # Spin briefly for GDO0 rise, then for fall.
            t0 = time.ticks_ms()
            while self.gdo0.value() == 0 and time.ticks_diff(time.ticks_ms(), t0) < 100:
                pass
            t0 = time.ticks_ms()
            while self.gdo0.value() == 1 and time.ticks_diff(time.ticks_ms(), t0) < 1000:
                pass
        else:
            time.sleep_ms(100)
        self._strobe(SIDLE)

    def listen(self):
        """Enter RX mode."""
        self._strobe(SIDLE)
        self._strobe(SFRX)
        self._strobe(SRX)

    def packet_available(self):
        """True if a complete packet sits in the RX FIFO."""
        # GDO0 goes low at end-of-packet — easier: poll RXBYTES.
        n = self._read_status(RXBYTES) & 0x7F
        return n > 0

    def read_packet(self):
        """Return (payload, rssi_dbm, lqi) for the next FIFO packet, or
        (None, None, None) if nothing is available."""
        n = self._read_status(RXBYTES) & 0x7F
        if n == 0:
            return None, None, None
        length_byte = self._read_reg(RXFIFO)
        if length_byte == 0 or length_byte > 64:
            self._strobe(SFRX)
            return None, None, None
        data = self._read_burst(RXFIFO, length_byte)
        # Two appended status bytes: RSSI, LQI|CRC_OK
        status = self._read_burst(RXFIFO, 2)
        raw_rssi = status[0]
        if raw_rssi >= 128:
            rssi_dbm = (raw_rssi - 256) // 2 - 74
        else:
            rssi_dbm = raw_rssi // 2 - 74
        lqi = status[1] & 0x7F
        crc_ok = bool(status[1] & 0x80)
        if not crc_ok:
            return None, None, None
        payload = bytes([length_byte]) + bytes(data)
        return payload, rssi_dbm, lqi


def make_default(config):
    """Wire SPI + return a configured CC1101 ready to listen()."""
    spi = SPI(0,
              baudrate=5_000_000,
              polarity=0, phase=0,
              sck=Pin(config.PIN_SPI_SCK),
              mosi=Pin(config.PIN_SPI_MOSI),
              miso=Pin(config.PIN_SPI_MISO))
    radio = CC1101(spi, config.PIN_CC1101_CS, config.PIN_CC1101_GDO0)
    radio.reset()
    radio.configure_default(
        freq_hz=config.RF_FREQ_HZ,
        sync_word=config.RF_SYNC_WORD,
        bitrate_bps=config.RF_BITRATE_BPS,
        deviation_hz=config.RF_DEVIATION_HZ,
        rx_bw_hz=config.RF_RX_BW_HZ,
        tx_power_dbm=config.RF_TX_POWER_DBM,
    )
    return radio
