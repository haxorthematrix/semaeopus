# Bring-up scripts

Tiny, self-contained MicroPython scripts that verify each subsystem
*before* the full satellite firmware is uploaded. Run them in order
after wiring each chunk of the build; each prints a clear PASS / FAIL
line.

Run on a Pico over `mpremote`:

```bash
mpremote connect /dev/ttyACM0 run bringup/01_blink.py
mpremote connect /dev/ttyACM0 run bringup/02_i2c_scan.py
# ... etc
```

The scripts are **standalone** — they do not import any Semaeopus
firmware modules, so you can run them on a fresh Pico that only has
MicroPython on it.

| # | Script                       | Verifies                                          | Needs hardware                       |
|---|------------------------------|---------------------------------------------------|--------------------------------------|
| 1 | `01_blink.py`                | MicroPython is alive, GPIO works                  | Pi Pico only                         |
| 2 | `02_i2c_scan.py`             | I²C bus 0 and bus 1 wiring + addresses            | + I²C devices wired                  |
| 3 | `03_oled_test.py`            | SSD1306 OLED I²C + display                        | + OLED                               |
| 4 | `04_sensor_smoke.py`         | BME280 + MPU6050 + INA219 + DS3231 return data    | + four sensors                       |
| 5 | `05_spi_loopback.py`         | SPI0 wiring (MOSI ↔ MISO jumper test)             | + a jumper between MOSI/MISO         |
| 6 | `06_cc1101_id.py`            | CC1101 SPI link via PARTNUM/VERSION read          | + CC1101 wired                       |
| 7 | `07_radio_loopback.py`       | Two-radio TX/RX with a known payload              | + two Picos+CC1101, on same band     |

If 1–6 pass, the satellite is ready for full firmware. Script 7 is
the end-to-end check that proves both halves of the link work together.

## What to do if a script fails

See [`hardware/bringup-checks.md`](../hardware/bringup-checks.md) for
the troubleshooting tree — each FAIL message in the scripts is keyed
to a row in that doc.
