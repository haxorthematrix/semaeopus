# Ground Station Wiring

Both the **operator** and the **active-TX attacker** front-ends use the
same Pico + CC1101 + OLED wiring as the satellite, minus the
housekeeping sensors. Build once, flash with the appropriate firmware.

## Pi Pico + CC1101 front-end

Identical to satellite SPI/CC1101 wiring:

| CC1101 | Pi Pico        |
|--------|----------------|
| VCC    | 3V3 OUT (36)   |
| GND    | GND            |
| CSN    | GP13           |
| SCK    | GP18           |
| MOSI   | GP19           |
| MISO   | GP12           |
| GDO0   | GP10           |
| GDO2   | (unused)       |

Antenna: same 170 mm wire (433 MHz) / 82 mm (915 MHz).

## OLED (status)

| SSD1306 | Pi Pico |
|---------|---------|
| VCC     | 3V3     |
| GND     | GND     |
| SDA     | GP4     |
| SCL     | GP5     |

The OLED on the operator station shows: link state, last RSSI, beacon
sequence count, and any sequence-count holes (when an attacker is
injecting).

## RTL-SDR (attacker RX)

No wiring — plug the dongle into the laptop, attach the bundled
antenna. The antenna that ships with most RTL-SDR v3 kits is a small
telescopic dipole; extend each leg to ~17 cm for 433 MHz, or ~8 cm for
915 MHz.

## HackRF One (attacker active TX, optional)

No wiring — USB to the laptop. **TX with the ANT500 fully extended is
adequate for the bench**; do not chain external amplifiers.

## Pico flashing — firmware-per-role

| Build target                       | Firmware folder                 | Notes                              |
|------------------------------------|---------------------------------|------------------------------------|
| Satellite                          | `firmware/satellite/`           | MicroPython, runs `main.py`        |
| Operator GS radio front-end        | `firmware/gs_frontend/`         | Same MicroPython, exposes USB-CDC  |
| Attacker active-TX front-end       | `firmware/gs_frontend/`         | Same firmware as operator          |

The operator and attacker Picos run **the same** front-end firmware —
they differ only in what software on the laptop is talking to them
(`gs-operator` vs `gs-attacker`). This is intentional: the attacker
should not need a special radio.
