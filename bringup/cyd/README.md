# CYD bring-up: CC1101 on the microSD slot

First-power test for the CYD satellite and operator stations. Wire both
boards identically (see `firmware/shared/cyd_pins.py` for the full pin map):

| CC1101    | CYD source        | GPIO |
|-----------|-------------------|------|
| SCK       | sniffer CLK       | 18   |
| MOSI (SI) | sniffer CMD       | 23   |
| MISO (SO) | sniffer DAT0      | 19   |
| CSN       | sniffer CD/DAT3   | 5    |
| GDO0      | CN1 IO27          | 27   |
| VCC       | CN1 3.3V          | -    |
| GND       | CN1 GND           | -    |

Before powering up:

* **3.3 V only.** Never connect the CC1101 to the CYD's 5 V.
* **Leave the sniffer's own microSD socket empty.**
* **Wire by the CC1101 silkscreen labels**, not pin position; module
  pinouts vary by vendor.
* **Check CN1's pin order** on your board (usually GND, IO22, IO27, 3.3V).

Neither test transmits.

## Option A: MicroPython (recommended)

This matches the existing Semaeopus firmware, so the satellite code
ports with mostly pin changes.

```bash
pip install esptool mpremote

# Download the ESP32_GENERIC .bin from https://micropython.org/download/ESP32_GENERIC/
# Port: macOS /dev/cu.usbserial-* or /dev/cu.wchusbserial-*, Linux /dev/ttyUSB0
esptool.py --port PORT erase_flash
esptool.py --port PORT --baud 460800 write_flash -z 0x1000 ESP32_GENERIC-<version>.bin

tools/deploy.sh bringup-cyd PORT        # or: mpremote connect PORT run bringup/cyd/06_cc1101_cyd.py
```

## Option B: Arduino

Open `arduino/CYD_CC1101_Bringup/CYD_CC1101_Bringup.ino`, choose board
**ESP32 Dev Module** (arduino-esp32 core 2.x or 3.x), upload, and open
the serial monitor at 115200 baud. No extra libraries are needed.

## Reading the results

Both versions run the same seven stages. Each stage adds one wire to
what it proves, so **fix the first FAIL**; later failures usually
follow from it.

| Stage | Proves | Common fault |
|---|---|---|
| 1 LED self-test | Board and firmware alive | None |
| 2 Chip ready | VCC, GND, CSN, MISO | Card in sniffer socket; CSN or VCC loose |
| 3 ID @ 1 MHz | + SCK | `0xFF/0xFF` = no chip or MISO; same byte twice = MOSI |
| 4 Write / read back | + MOSI | Writes not landing |
| 5 GDO0 wire | GDO0 to IO27 | CN1 pin order differs on your board |
| 6 ID + read back @ 5 MHz | Operating SPI speed | Long leads; lower `SPI_BAUD` |
| 7 RX at 915 MHz | Crystal, PLL lock, RF section | 433 MHz module bought by mistake |

At the end, the RGB LED is **green** if every stage passed and **red**
if any failed. If the radio reached RX, a live RSSI meter follows (blue
LED).

**RF sanity check:** the expected noise floor is roughly -100 to
-110 dBm. With the meter running, key a HackRF carrier at minimum gain
and the bar should jump:

```bash
hackrf_transfer -f 915000000 -c 127 -x 0     # CW carrier, amp off; Ctrl-C to stop
```

## Testing without hardware

The CYD firmware (not this bring-up script) is exercised against a
simulated CC1101 by `tests/firmware/`; run `python -m pytest tests/firmware -q`.
