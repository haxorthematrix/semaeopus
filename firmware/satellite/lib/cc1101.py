"""
Minimal CC1101 driver for MicroPython (RP2040 Pico and ESP32 CYD).

Implements the subset Semaeopus needs:
  - reset, configure for 2-GFSK 9600 bps
  - set frequency (433 MHz / 915 MHz)
  - set sync word
  - transmit a variable-length packet (length-byte first)
  - receive (blocking, or non-blocking via GDO0 IRQ)

Not a full driver. Refer to TI DN005 / DN509 for the magic register
values. The defaults below were exported from TI's SmartRF Studio for
9600 bps 2-GFSK with a 58 kHz receive filter and ~20.6 kHz deviation.
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

# MARCSTATE values used by packet_available()
MARC_IDLE            = 0x01
MARC_RX              = 0x0D
MARC_RX_RST          = 0x0F
MARC_RXFIFO_OVERFLOW = 0x11

XTAL_HZ = 26_000_000


class CC1101:
    def __init__(self, spi, cs_pin, gdo0_pin=None):
        self.spi = spi
        self.cs = Pin(cs_pin, Pin.OUT, value=1)
        self.gdo0 = Pin(gdo0_pin, Pin.IN) if gdo0_pin is not None else None
        self._buf = bytearray(1)
        self._freq_hz = 915_000_000
        self._held = None          # complete packet kept aside by transmit()

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
        # Most registers come from a SmartRF Studio export: 9.6 kBaud,
        # 58 kHz BW, 2-GFSK. On-air format, which SDR tools must match
        # (see tools/air_frame.py): 4 preamble bytes, the sync word sent
        # twice, LEN + data, then a CRC-16 (poly 0x8005) added by the chip.
        # The deviation_hz argument is not used: DEVIATN is fixed below.
        self._write_reg(IOCFG0,  0x06)   # GDO0: asserts on sync, deasserts at packet end
        self._write_reg(IOCFG2,  0x29)   # GDO2: CHIP_RDYn (unused)
        self._write_reg(FIFOTHR, 0x47)
        self._write_reg(PKTLEN,  0xFF)   # max 255 bytes; variable len header drives actual size
        self._write_reg(PKTCTRL1,0x04)   # APPEND_STATUS=1
        self._write_reg(PKTCTRL0,0x05)   # WHITENING=0, VAR_LEN, CRC enabled, no FEC
        self._write_reg(FSCTRL1, 0x06)
        self._write_reg(MDMCFG4, 0xF8)   # CHANBW=58 kHz, DRATE_E=8
        self._write_reg(MDMCFG3, 0x83)   # DRATE_M=131  ->  ~9.6 kBaud
        self._write_reg(MDMCFG2, 0x13)   # 2-GFSK, sync 30/32 (sync word sent twice), no Manchester
        self._write_reg(MDMCFG1, 0x22)   # 4 preamble bytes
        self._write_reg(MDMCFG0, 0xF8)
        self._write_reg(DEVIATN, 0x35)   # 26 MHz / 2^17 * 13 * 8 = ~20.6 kHz
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
        self._freq_hz = freq_hz
        freq_word = int((freq_hz << 16) / XTAL_HZ)
        self._write_reg(FREQ2, (freq_word >> 16) & 0xFF)
        self._write_reg(FREQ1, (freq_word >>  8) & 0xFF)
        self._write_reg(FREQ0,  freq_word        & 0xFF)

    def set_sync_word(self, sync16):
        self._write_reg(SYNC1, (sync16 >> 8) & 0xFF)
        self._write_reg(SYNC0,  sync16       & 0xFF)

    def set_tx_power(self, dbm):
        # PATABLE values from TI DN013, single-byte mode. The right byte
        # depends on the band, so call set_frequency() first.
        if self._freq_hz >= 800_000_000:
            table = { -30: 0x03, -20: 0x0E, -15: 0x1E, -10: 0x27,
                        0: 0x8E,  +5: 0x84, +7: 0xCC, +10: 0xC3 }   # 915 MHz
        else:
            table = { -30: 0x12, -20: 0x0E, -15: 0x1D, -10: 0x34,
                        0: 0x60,  +5: 0x84, +7: 0xC8, +10: 0xC0 }   # 433 MHz
        # Pick closest <= requested (lowest entry if below the table).
        keys = sorted(table.keys())
        chosen = table[keys[0]]
        for k in keys:
            if k <= dbm:
                chosen = table[k]
        self._write_reg(PATABLE, chosen)

    def set_rx_bandwidth(self, bw_hz):
        """Set the receive channel filter to the nearest supported width
        (58 kHz to 812 kHz). Returns the actual bandwidth in Hz.

        BW = XTAL / (8 * (4 + CHANBW_M) * 2**CHANBW_E). A narrow filter
        lets the attacker modem hear a signal right beside a jammer
        (lesson L10). Call from IDLE; listen() afterwards re-enters RX."""
        best = None
        for e in range(4):
            for m in range(4):
                bw = XTAL_HZ // (8 * (4 + m) * (1 << e))
                if best is None or abs(bw - bw_hz) < abs(best[0] - bw_hz):
                    best = (bw, e, m)
        bw, e, m = best
        cur = self._read_reg(MDMCFG4)
        self._write_reg(MDMCFG4, (e << 6) | (m << 4) | (cur & 0x0F))
        return bw

    def idle(self):
        self._strobe(SIDLE)

    # ---- packet I/O --------------------------------------------------------

    def transmit(self, payload):
        """Variable-length packet: payload[0] must be the length byte.

        The radio is half duplex and SIDLE aborts a reception, so first let
        a packet that is already arriving finish (GDO0 is high from its
        sync word to its end), and keep any complete packet for the next
        read_packet() instead of losing it."""
        if self.gdo0:
            t0 = time.ticks_ms()
            while self.gdo0.value() == 1 and time.ticks_diff(time.ticks_ms(), t0) < 150:
                pass
        if self._held is None and self.packet_available():
            got = self.read_packet()
            if got[0] is not None:
                self._held = got
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

    def _rx_bytes(self):
        """RXBYTES, read until two reads agree (CC1101 errata: SPI reads of
        status registers can be corrupted while the value is changing)."""
        a = self._read_status(RXBYTES)
        while True:
            b = self._read_status(RXBYTES)
            if a == b:
                return a & 0x7F, bool(a & 0x80)
            a = b

    def packet_available(self):
        """True once a COMPLETE packet is waiting in the RX FIFO.

        configure_default() sets MCSM1 RXOFF_MODE = IDLE, so the chip
        leaves RX for IDLE the moment a packet ends. While it is still in
        RX, bytes in the FIFO belong to a packet that is still arriving
        (a 30-byte frame takes about 30 ms at 9.6 kBaud), so we wait.
        Whenever the chip is idle with nothing to read, or the FIFO
        overflowed, we put it back into RX here."""
        if self._held is not None:
            return True
        state = self._read_status(MARCSTATE) & 0x1F
        if MARC_RX <= state <= MARC_RX_RST:
            return False                    # listening, or mid-packet
        n, overflow = self._rx_bytes()
        if overflow or state == MARC_RXFIFO_OVERFLOW:
            self.listen()
            return False
        if state == MARC_IDLE:
            if n > 0:
                return True
            self.listen()                   # e.g. after a CRC-failed packet was discarded
        return False

    def read_packet(self):
        """Return (payload, rssi_dbm, lqi) for the waiting packet, or
        (None, None, None) if there is none or it failed the CRC.
        Always leaves the radio listening again."""
        if self._held is not None:
            got, self._held = self._held, None
            return got
        try:
            n, _ = self._rx_bytes()
            if n == 0:
                return None, None, None
            length_byte = self._read_reg(RXFIFO)
            if length_byte == 0 or length_byte + 2 > n - 1:
                return None, None, None     # incomplete or corrupt: drop it
            data = self._read_burst(RXFIFO, length_byte)
            # Two appended status bytes: RSSI, LQI|CRC_OK
            status = self._read_burst(RXFIFO, 2)
        finally:
            self.listen()                   # flush leftovers, back to RX
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
    # Pico: SPI(0). ESP32 CYD: SPI(2) (VSPI); the ESP32 has no SPI(0).
    spi = SPI(getattr(config, "CC1101_SPI_ID", 0),
              baudrate=getattr(config, "SPI_BAUD", 5_000_000),
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
