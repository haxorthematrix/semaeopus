"""
Per-build satellite configuration.

Change values here, copy this file plus the rest of `firmware/satellite/`
to the Pico (Thonny: "Save copy to MicroPython device"), and reset.
"""

CALLSIGN        = "SEMAEOPUS-1"

# ---------------------------------------------------------------------------
# Radio
# ---------------------------------------------------------------------------

# Frequency in Hz. 433.920 MHz (EU/R1 default), 915.000 MHz (US Part 15.247).
RF_FREQ_HZ      = 433_920_000

RF_BITRATE_BPS  = 9600
RF_DEVIATION_HZ = 4800
RF_RX_BW_HZ     = 58_000
RF_MODULATION   = "2-GFSK"
RF_SYNC_WORD    = 0xD391
RF_TX_POWER_DBM = 0       # 0 dBm = 1 mW. CC1101 can go to +10 dBm. Stay legal.

# CC1101 wiring (see hardware/wiring-satellite.md)
PIN_SPI_SCK   = 18
PIN_SPI_MOSI  = 19
PIN_SPI_MISO  = 12
PIN_CC1101_CS = 13
PIN_CC1101_GDO0 = 10

# I²C buses
I2C0_SDA, I2C0_SCL = 4, 5
I2C1_SDA, I2C1_SCL = 20, 21

# LEDs (active high)
PIN_LED_RX = 16
PIN_LED_TX = 17

# ---------------------------------------------------------------------------
# Lesson knob — security level (see protocol/space_packet.py)
# ---------------------------------------------------------------------------

# 0 = L0 cleartext (default — lessons L00–L06)
# 1 = L1 HMAC only, no nonce binding (lesson L07)
# 2 = L2 HMAC + nonce counter (lesson L08–L09)
# 3 = L3 AES-128-CTR + HMAC (lesson L10+)
SECURITY_LEVEL  = 0

# Pre-shared key for L1+ lessons. 16 bytes (AES-128) — the same key is
# used for HMAC and AES; lesson notes call this out as deliberately weak.
SHARED_KEY      = b"SemaeopusKey_v01"

# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

BEACON_PERIOD_MS    = 10_000
HK_TLM_PERIOD_MS    =  5_000
ADCS_TLM_PERIOD_MS  =  2_000
EPS_TLM_PERIOD_MS   =  5_000
RX_POLL_PERIOD_MS   =     20

# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

MODE_NOMINAL = 0
MODE_SAFE    = 1
MODE_PAYLOAD = 2
MODE_IDLE    = 3

START_MODE   = MODE_NOMINAL
