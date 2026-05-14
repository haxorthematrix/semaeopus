# Satellite (FlatSat) — Bill of Materials

All parts are through-hole or come on pre-soldered breakout boards with
0.1" headers. Nothing requires SMD soldering or a custom PCB.

Prices are USD, rough, late-2025 retail (Amazon / AliExpress / Adafruit
/ Pimoroni). Substitutions in the "Alt" column are functionally
equivalent for Semaeopus purposes.

| #  | Part                                       | Role                                | Qty | Approx $ | Notes / Alt                                              |
|----|--------------------------------------------|-------------------------------------|-----|---------:|----------------------------------------------------------|
| 1  | Raspberry Pi Pico (or Pico 2 / Pico W)     | OBC + radio controller              | 1   | 4–6      | Pico W gives a "wifi side-channel" lesson later          |
| 2  | CC1101 433 MHz module, 8-pin header        | UHF transceiver                     | 1   | 3–6      | E07-M1101D recommended (SMA), generic 8-pin OK           |
| 3  | SSD1306 0.96" I²C OLED                     | Status display                      | 1   | 3–5      | 128×64 mono. 4-pin (VCC/GND/SCL/SDA)                     |
| 4  | BME280 I²C breakout                        | Temp / pressure / humidity ("HK")   | 1   | 4–7      | BMP280 also OK (loses humidity), update firmware         |
| 5  | MPU6050 I²C breakout (GY-521)              | IMU — simulated ADCS                | 1   | 2–4      | MPU9250 fine but pin-compatible only roughly             |
| 6  | INA219 I²C breakout                        | Power telemetry                     | 1   | 3–5      | Adafruit or generic                                      |
| 7  | DS3231 I²C RTC + CR2032                    | OBC time                            | 1   | 2–4      | Cell included on most boards                             |
| 8  | 5 mm LED, green                            | RX activity                         | 1   | <1       | Any colour                                               |
| 9  | 5 mm LED, red                              | TX activity                         | 1   | <1       |                                                          |
| 10 | 220 Ω resistor, ¼ W                        | LED current limit                   | 2   | <1       |                                                          |
| 11 | Half-size breadboard, 400-tie              | Build substrate                     | 1   | 4–6      | Solderless                                               |
| 12 | Dupont jumper wires (M–M, M–F mix)         | Wiring                              | 40  | 4–6      | Pre-made kit                                             |
| 13 | 17 cm solid-core wire, 22 AWG              | ¼-wave 433 MHz whip antenna         | 1   | <1       | Use 8.2 cm if you switched to 915 MHz                    |
| 14 | (Optional) SMA female pigtail              | Connect a "real" antenna later      | 1   | 2        | Only if your CC1101 module exposes SMA                   |
| 15 | USB-A → micro-B cable (or USB-C for Pico 2)| Power + console for the Pico        | 1   | 2–4      |                                                          |

**Approx total: $35 USD** for the Pico-W satellite, less for the
plain Pico variant.

## Notes on CC1101 module variants

There are three common form factors. Any of them work, but pinouts vary:

- **8-pin generic ("E07-M1101D" or similar, no shielding)** — the
  cheapest. SMA connector or U.FL on most boards. *This is the one
  Semaeopus wiring diagrams assume.*
- **"CC1101 433MHz Wireless Transceiver Module" 10-pin** — adds GDO0
  and GDO2 on separate pins. Wire GDO0 as in the diagram; ignore GDO2
  or break it out to a free Pico GPIO if you want to follow
  packet-end interrupts in firmware.
- **CC1101 + PA/LNA combo boards** — do **not** buy these. They push
  output power well past ISM limits and will get you into trouble.

## Sensor I²C address summary

| Device    | Default 7-bit addr | Notes                                  |
|-----------|--------------------|----------------------------------------|
| SSD1306   | 0x3C               | Some boards 0x3D — check the silk      |
| BME280    | 0x76               | 0x77 on some breakouts                 |
| MPU6050   | 0x68               | 0x69 if AD0 tied high                  |
| INA219    | 0x40               | Configurable via A0/A1 pads            |
| DS3231    | 0x68               | **Collides with MPU6050.** Two options: (a) move MPU6050 to 0x69 by tying AD0 to 3V3, or (b) put DS3231 on the *second* I²C bus (Pico has two). Semaeopus default: MPU6050 on bus0 @ 0x68, DS3231 on bus1 @ 0x68. |
