"""
Satellite configuration for the CYD build.

Edit values here and re-copy only this file; the rest of the firmware
does not need to change. Pin numbers live in pins.py.
"""

from pins import *   # noqa: F401,F403  (CYD pin map)

CALLSIGN = "SEMAEOPUS-1"

# ---------------------------------------------------------------------------
# Radio (US build: 47 C.F.R. 15.249, 902-928 MHz)
# ---------------------------------------------------------------------------

RF_FREQ_HZ      = 915_000_000
RF_BITRATE_BPS  = 9600
RF_DEVIATION_HZ = 4800
RF_RX_BW_HZ     = 58_000
RF_MODULATION   = "2-GFSK"
RF_SYNC_WORD    = 0xD391
RF_TX_POWER_DBM = 0           # 1 mW. Plenty for a bench; stay low.

# pins.py provides CC1101_SPI_ID, SPI_BAUD, PIN_SPI_*, PIN_CC1101_CS and
# PIN_CC1101_GDO0, which lib/cc1101.make_default() reads from here.

# ---------------------------------------------------------------------------
# Lesson knob: security level (see protocol/space_packet.py)
# ---------------------------------------------------------------------------

# 0 = L0 cleartext (lessons L00-L06)
# 1 = L1 HMAC only, no nonce binding (L07)
# 2 = L2 HMAC + monotonic nonce (L08-L09)
# 3 = L3 AES-128-CTR + HMAC (L10+)
SECURITY_LEVEL = 0

# Pre-shared key for L1+. 16 bytes; deliberately weak, as the lessons note.
SHARED_KEY = b"SemaeopusKey_v01"

# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

BEACON_PERIOD_MS   = 10_000
HK_TLM_PERIOD_MS   =  5_000
ADCS_TLM_PERIOD_MS =  2_000
EPS_TLM_PERIOD_MS  =  5_000
RX_POLL_PERIOD_MS  =      0   # every loop pass (one status read)
SCREEN_PERIOD_MS   =    500

# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

MODE_NOMINAL = 0
MODE_SAFE    = 1
MODE_PAYLOAD = 2
MODE_IDLE    = 3

START_MODE = MODE_NOMINAL

# ---------------------------------------------------------------------------
# CYD display and light sensor
# ---------------------------------------------------------------------------

# Orientation. 0x28 = landscape. If the picture is upside down use 0xE8.
# If it is mirrored, try 0x68 or 0xA8. If red and blue are swapped,
# toggle the 0x08 bit (for example 0x28 -> 0x20).
DISPLAY_MADCTL = 0x28
# USB-C "CYD2USB" boards (ST7789 panel) usually need this set to True.
DISPLAY_INVERT = False

# The CYD's LDR reads LOW in bright light. Flip if yours reads the other way.
LDR_BRIGHT_IS_LOW = True
