"""
Pin map for the ESP32-2432S028R "Cheap Yellow Display" (CYD).

Used by the Semaeopus satellite and operator stations. Both stations
are wired identically: the CC1101 radio sits on the CYD's VSPI bus,
reached through a microSD sniffer plugged into the SD slot, with
power, ground and GDO0 taken from the CN1 header.

    CC1101 pin   CYD source              ESP32 GPIO
    ----------   ---------------------   ----------
    SCK          sniffer CLK             18
    MOSI (SI)    sniffer CMD             23
    MISO (SO)    sniffer DAT0            19
    CSN          sniffer CD/DAT3         5
    GDO0         CN1 IO27                27
    VCC          CN1 3.3V                -   (3.3 V ONLY, never 5 V)
    GND          CN1 GND                 -

Notes
  * Leave the sniffer's own microSD socket EMPTY. A card in it shares
    the bus with the CC1101 and corrupts every transfer.
  * CN1 pin order on most boards is GND, IO22, IO27, 3.3V. Confirm on
    your board's silkscreen; revisions differ. If IO27 is not on your
    CN1, IO22 works for GDO0 (change PIN_CC1101_GDO0).
  * MicroPython on the classic ESP32 exposes SPI(1) = HSPI and
    SPI(2) = VSPI. SPI(0) does not exist (it is the flash bus), so
    code written for the Pico's SPI(0) must take the bus ID from here.
"""

# ---------------------------------------------------------------------------
# CC1101 radio (VSPI, via the microSD slot)
# ---------------------------------------------------------------------------

CC1101_SPI_ID   = 2            # VSPI. SPI(1)/HSPI belongs to the display.
PIN_SPI_SCK     = 18           # microSD CLK
PIN_SPI_MOSI    = 23           # microSD CMD
PIN_SPI_MISO    = 19           # microSD DAT0
PIN_CC1101_CS   = 5            # microSD CD/DAT3 (strapping pin; pulled up at boot, fine for CSN)
PIN_CC1101_GDO0 = 27           # CN1 IO27

SPI_BAUD_BRINGUP = 1_000_000   # safe over Dupont leads and a sniffer
SPI_BAUD         = 5_000_000   # operating speed; CC1101 max is 6.5 MHz (burst)

# Radio defaults for the US build (47 C.F.R. 15.249, 902-928 MHz)
RF_FREQ_HZ       = 915_000_000
RF_TX_POWER_DBM  = 0
PATABLE_915_0DBM = 0x8E        # TI DN013 value for 915 MHz. The 433 MHz table
                               # entry (0x60) gives a different power at 915.

# ---------------------------------------------------------------------------
# On-board peripherals (fixed by the CYD board, do not reuse)
# ---------------------------------------------------------------------------

# ILI9341 display, 240 x 320, on HSPI
TFT_SPI_ID   = 1
PIN_TFT_SCK  = 14
PIN_TFT_MOSI = 13
PIN_TFT_MISO = 12              # strapping pin
PIN_TFT_CS   = 15
PIN_TFT_DC   = 2               # strapping pin
PIN_TFT_BL   = 21              # backlight, active high
# Display reset is tied to the ESP32 EN line (no GPIO).
# USB-C "CYD2USB" revisions use an ST7789 on the same pins.

# XPT2046 resistive touch, on its own pins (use SoftSPI)
PIN_TOUCH_CLK  = 25
PIN_TOUCH_MOSI = 32
PIN_TOUCH_MISO = 39            # input only
PIN_TOUCH_CS   = 33
PIN_TOUCH_IRQ  = 36            # input only

# RGB status LED, ACTIVE LOW (write 0 to light)
PIN_LED_R = 4
PIN_LED_G = 16
PIN_LED_B = 17

# Light-dependent resistor (the satellite's "sun sensor"), ADC1
PIN_LDR = 34                   # input only

# Speaker amplifier input (DAC)
PIN_SPEAKER = 26

# BOOT button, active low
PIN_BOOT_BTN = 0

# ---------------------------------------------------------------------------
# Spare GPIO on the expansion headers
# ---------------------------------------------------------------------------

# CN1 (JST 1.25 mm, 4-pin): GND, IO22, IO27, 3.3V
PIN_CN1_IO22 = 22              # free
PIN_CN1_IO27 = 27              # used for CC1101 GDO0

# P3 (JST 1.25 mm, 4-pin): GND, IO35, IO22, IO21
PIN_P3_IO35 = 35               # input only, free
# P3's IO21 is the display backlight on most revisions. Do not use it.
