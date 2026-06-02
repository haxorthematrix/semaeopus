# Amazon BOM — current candidates

A snapshot of specific Amazon product candidates for each item in the
satellite, operator GS, and attacker GS builds.

> **Honest caveats.**
>
> 1. **I cannot verify what's actually for sale at the moment you read this.**
>    Amazon listings churn weekly: ASINs get reused, sellers swap out,
>    prices change, products get delisted.
> 2. The specific links below are a **snapshot as of 2026-06-01**.
>    Treat them as starting points, not endorsements.
> 3. Each row also gives a **search URL** (which never breaks) and the
>    **specs you must verify** before buying — so if a specific link
>    is dead you can find a working substitute on your own.
> 4. **Generic CC1101 / sensor breakouts are commodity boards.** A
>    different-coloured PCB from a different vendor with the same chip
>    is the same part.

Rough totals for late-2026 pricing:

| Build                              | Approx cost (USD) |
|------------------------------------|------------------:|
| Satellite (FlatSat)                | $30 – $50         |
| Operator ground station            | $18 – $25         |
| Attacker — Tier 1 (RTL-SDR + Pico) | $40 – $60         |
| Attacker — Tier 2 (+ HackRF One)   | $360 – $400       |

---

## How to read each row

```
ITEM — short description
  Role:               what it does in Semaeopus
  Must match:         the specs your substitute MUST meet
  Watch out for:      common gotchas / counterfeits
  Candidate (snapshot 2026-06-01):  a specific Amazon link
  Search:             stable Amazon search URL
  Approx price:       USD at the time of search
```

---

## Satellite (FlatSat)

### 1. Raspberry Pi Pico H — OBC + radio controller

- **Role**: runs the satellite firmware; SPI master to the CC1101; I²C master to the sensors.
- **Must match**: RP2040 microcontroller, USB-A → micro-B (Pico/Pico W) or USB-C (Pico 2). The **"H" variant has headers pre-soldered** — get this unless you want to solder pins yourself.
- **Watch out for**: third-party RP2040 clones (Adafruit KB2040, Pimoroni Tiny 2040) work but use different pin numbering — you'll need to remap in `firmware/satellite/config.py`.
- **Candidate**: [Raspberry Pi Pico H (official)](https://www.amazon.com/Raspberry-Pi-Pico-H/dp/B0B5H2LNL2) — official Raspberry Pi listing, ~$5–6.
- **Search**: [raspberry pi pico h](https://www.amazon.com/s?k=raspberry+pi+pico+h)
- **Approx price**: $5–6 (bare) or $10–18 in a starter kit with breadboard

### 2. CC1101 433 MHz transceiver — UHF radio

- **Role**: the actual radio. Sub-GHz 2-GFSK transceiver Semaeopus tunes to 433.92 MHz (EU) or 915 MHz (US).
- **Must match**: TI **CC1101** chip; 3V3 logic (not 5V); SMA antenna jack or solder pad. The **E07-M1101D-SMA** from EBYTE/CDSENET is the exact module Semaeopus's wiring diagrams target.
- **Watch out for**: CC1101 + **PA/LNA combo modules** push output well past ISM legal limits — do not buy these. Also avoid "915 MHz" boards if you want to operate in EU and vice versa.
- **Candidate**: [EBYTE E07-M1101D-SMA CC1101 433 MHz 10 dBm module](https://www.amazon.com/EBYTE-E07-M1101D-SMA-Transceiver-Transmission-Transmitter/dp/B07P8S9M4W) — the exact form factor in the wiring docs.
- **Search**: [cc1101 module sma](https://www.amazon.com/s?k=cc1101+module+sma)
- **Approx price**: $5–8 per module

### 3. SSD1306 0.96″ OLED — status display

- **Role**: shows mode / boot count / SoC / TX sequence on the satellite OBC.
- **Must match**: **SSD1306** controller (not SH1106 — different command set), 128×64, **I²C interface** (not SPI), 0.96″, 4-pin (VCC / GND / SCL / SDA), 3V3 or 3–5V tolerant.
- **Watch out for**: SH1106 boards look identical but use a different driver; check the silkscreen or product description before buying. Also some boards ship at address 0x3D instead of 0x3C — the bring-up scripts handle either.
- **Candidate**: [4-pack DIYmall SSD1306 128×64 I²C white](https://www.amazon.com/Display-Module-SSD1306-Du-pont-Arduino/dp/B07VDXYDVY) — 4 displays + 40-pin jumper kit; plenty of spares.
- **Search**: [ssd1306 0.96 i2c oled](https://www.amazon.com/s?k=ssd1306+0.96+i2c+oled)
- **Approx price**: $3–5 single; $10–15 for a 4-pack

### 4. BME280 — temperature / pressure / humidity

- **Role**: housekeeping telemetry.
- **Must match**: **BME280** (NOT BMP280 — humidity matters for HK_TLM), I²C interface, 3V3 / 5V tolerant.
- **Watch out for**: cheap blue boards often labeled "BME280" actually ship the BMP280 (missing humidity). The Adafruit and SparkFun boards are guaranteed BME280; generic ones are a coin flip — search for `BME280` in the description and check seller reviews. The DS3231 + BME280 combo on a single bus 0 needs no pull-ups (both have them on board).
- **Candidate**: [ACEIRMC BME280 2-pack](https://www.amazon.com/Organizer-Temperature-Humidity-Atmospheric-Barometric/dp/B07V5CL3L8) — verified BME280 (not BMP280) per recent reviews.
- **Search**: [bme280 i2c breakout](https://www.amazon.com/s?k=bme280+i2c+breakout)
- **Approx price**: $4–7 single; $8–12 for a 2- or 3-pack

### 5. MPU6050 (GY-521) — IMU

- **Role**: simulated ADCS — gyro + accelerometer.
- **Must match**: **MPU-6050** chip on a **GY-521** breakout, I²C, 8-pin layout (VCC GND SCL SDA XDA XCL ADO INT). 3V3 / 5V tolerant.
- **Watch out for**: MPU-6500 / MPU-9250 boards look similar; the drivers in `firmware/satellite/lib/mpu6050.py` are MPU-6050-specific. Also: the MPU6050's default I²C address (0x68) collides with the DS3231 — Semaeopus puts each on a separate I²C bus (see wiring docs); you don't need to do anything except follow the wiring.
- **Candidate**: [HiLetgo GY-521 MPU-6050](https://www.amazon.com/HiLetgo-MPU-6050-Accelerometer-Gyroscope-Converter/dp/B078SS8NQV) — well-known seller for hobby electronics.
- **Search**: [mpu6050 gy-521](https://www.amazon.com/s?k=mpu6050+gy-521)
- **Approx price**: $2–4 single; $8–12 for a multi-pack

### 6. INA219 — power telemetry

- **Role**: bus voltage + current draw → EPS_TLM.
- **Must match**: **INA219** chip, I²C, **0.1 Ω built-in shunt** (the standard GY-219 breakout), default address 0x40.
- **Watch out for**: INA226 is a closely related part but uses a different register layout — won't work with the Semaeopus driver as-is.
- **Candidate**: [HiLetgo INA219 2-pack](https://www.amazon.com/HiLetgo-INA219-Bi-Directional-Current-Breakout/dp/B07VL8NY32) — generic, well-supported.
- **Search**: [ina219 i2c breakout](https://www.amazon.com/s?k=ina219+i2c+breakout)
- **Approx price**: $3–5 single; $7–10 for a 2-pack

### 7. DS3231 RTC + battery

- **Role**: real-time clock so post-reboot lessons (L08 nonce-reset edge case) actually have a wall clock.
- **Must match**: **DS3231SN** chip on the typical "ZS-042" board, I²C, default address 0x68 — Semaeopus routes this to **I²C bus 1** so it doesn't collide with the MPU6050.
- **Watch out for**: some breakouts include a charging circuit for a **LIR2032** (rechargeable lithium) — if you stick a non-rechargeable CR2032 in those, you may kill the battery. Easiest path: buy a board that has the AT24C32 + DS3231SN and use the **LIR2032** the board ships with, OR cut the charging-circuit trace and use a CR2032.
- **Candidate**: [HiLetgo DS3231 V2.0 2-pack](https://www.amazon.com/HiLetgo-DS3231-DS3231SN-Module-PinHeader/dp/B0832PM954) — version 2.0 board, well-documented charging-circuit workaround.
- **Search**: [ds3231 rtc module i2c](https://www.amazon.com/s?k=ds3231+rtc+module+i2c)
- **Approx price**: $2–4 single; battery often **not included** — add a [CR2032 / LIR2032 button cell](https://www.amazon.com/s?k=cr2032+battery) for ~$1 each.

### 8. LEDs (RX/TX activity) + 220 Ω resistors

- **Role**: blink on each radio transmission.
- **Must match**: 5 mm through-hole LEDs, any colour, 1.8–2.2 V Vf, 20 mA If. 220 Ω ¼ W resistors for current limiting.
- **Watch out for**: "kit" packs are *much* cheaper than buying single LEDs — and you get spares for future projects.
- **Candidate**: [WayinTop 200 LEDs + 600 resistors assortment](https://www.amazon.com/WayinTop-Resistor-Assortment-Respberry-Resistors/dp/B07YWNHZHS) — overkill for Semaeopus alone but a great kit for future builds.
- **Search**: [5mm led resistor assortment kit](https://www.amazon.com/s?k=5mm+led+resistor+assortment+kit)
- **Approx price**: $10–15 for the assortment kit; $2–3 if you can find a small LED-only 5-pack

### 9. Half-size breadboard, 400-tie

- **Role**: physical substrate.
- **Must match**: 400 tie-points, ~3.3″ × 2.2″ × 0.3″ (84 × 55 × 9 mm), self-adhesive backing optional.
- **Watch out for**: very cheap breadboards have poor spring tension and intermittent contacts; reviews are the best filter.
- **Candidate**: [ELEGOO 6-pack 400-point breadboards](https://www.amazon.com/ELEGOO-Breadboard-Solderless-Breadboards-Electronics/dp/B0CYPVMK9J) — best value for the satellite + operator GS + spares.
- **Search**: [400 point breadboard](https://www.amazon.com/s?k=400+point+breadboard)
- **Approx price**: $4–6 single; $10–14 for a 6-pack

### 10. Dupont jumper wire kit

- **Role**: connect everything.
- **Must match**: 2.54 mm (0.1″) pitch DuPont housing connectors. You need a **mix of M-M, M-F, and F-F** since the Pico has male headers (after H-variant assembly) and the breakouts have female headers.
- **Watch out for**: very-short (4″) wires can be too short to reach across a half-size breadboard cleanly. 8″ (20 cm) is the sweet spot.
- **Candidate**: [ELEGOO 120-piece DuPont kit (M-M + M-F + F-F)](https://www.amazon.com/Elegoo-EL-CP-004-Multicolored-Breadboard-arduino/dp/B01EV70C78) — well-reviewed standard.
- **Search**: [dupont jumper wires 120 male female](https://www.amazon.com/s?k=dupont+jumper+wires+120+male+female)
- **Approx price**: $5–8 for a 120-piece mixed kit

### 11. 22 AWG solid-core wire (antenna)

- **Role**: ¼-wave whip antenna soldered or screwed into the CC1101's SMA jack pad. **170 mm** for 433 MHz, **82 mm** for 915 MHz.
- **Must match**: 22 AWG solid (NOT stranded — stranded won't hold its shape as a whip), PVC insulated, copper or tinned-copper conductor.
- **Watch out for**: if your CC1101 module has an SMA jack, you'll want a short SMA pigtail + a wire antenna soldered onto an SMA plug, OR a proper 433/915 MHz mini-whip. The bare-wire approach is the cheap-and-cheerful default.
- **Candidate**: [TUOFENG 22 AWG solid core, 6 colours × 30 ft](https://www.amazon.com/TUOFENG-Hookup-Wires-6-Different-Colored/dp/B07TX6BX47) — overkill for a single antenna but a useful general kit.
- **Search**: [22 awg solid core hookup wire](https://www.amazon.com/s?k=22+awg+solid+core+hookup+wire)
- **Approx price**: $12–18 for the multi-colour kit (you only need ~20 cm)

### 12. USB cable (Pico → laptop)

- **Role**: power + serial console + MicroPython REPL.
- **Must match**: **data-capable** USB-A → micro-B for Pico/Pico W; USB-A → USB-C for Pico 2 / Pico 2 W. Cheap "charge-only" cables won't enumerate the Pico.
- **Watch out for**: many starter kits include a cable; check before buying. Length: 3–6 ft (~ 1 m) is comfortable for benchwork.
- **Candidate**: [CableCreation 4 ft braided USB-A → micro-B](https://www.amazon.com/CableCreation-Braided-High-Speed-Triple-Shielded/dp/B013G4EDKY) — data-capable, well-reviewed.
- **Search**: [micro usb data cable 3ft](https://www.amazon.com/s?k=micro+usb+data+cable+3ft)
- **Approx price**: $5–8 single

---

## Operator ground station

The operator GS uses items 1, 2, 3, 9, 10, 11, 12 from the satellite
list above. No extras to buy — same modules, same vendor, same
sourcing.

If you're buying for both at once: 2 × Pi Pico H, 2 × CC1101 SMA, 2 ×
SSD1306, plus shared breadboard / DuPont / wire / USB stock.

---

## Attacker — Tier 1 (RTL-SDR + active TX)

### 13. RTL-SDR Blog V3 — passive RX

- **Role**: wideband receive for the spectrum-survey lesson (L01) and the GNU Radio demod lesson (L02).
- **Must match**: **RTL-SDR Blog V3** specifically — it has the 1 PPM TCXO, bias-tee, and aluminum enclosure that distinguishes it from generic R820T2 dongles. The V4 (R828D) is the newer model and works fine too. Generic "DVB-T" dongles without the 1 PPM TCXO will drift too much for clean demodulation.
- **Watch out for**: counterfeits flooding the "RTL-SDR" search. Buy directly from RTL-SDR Blog's official Amazon listing — check seller name.
- **Candidate**: [RTL-SDR Blog V3 R820T2 + dipole antenna kit](https://www.amazon.com/R820t2-Rtl2832u-Antenna-Software-Defined/dp/B0C8SBBV7Q) — includes the multi-band telescoping dipole that covers 433 MHz.
- **Search**: [rtl-sdr blog v3 dipole](https://www.amazon.com/s?k=rtl-sdr+blog+v3+dipole)
- **Approx price**: $32–40 for the V3 + dipole kit

### 14. Second Pi Pico + CC1101 — attacker active TX

Buy a duplicate of items 1, 2, 3, 9, 10, 11, 12 from the satellite list.

---

## Attacker — Tier 2 (HackRF One)

### 15. HackRF One + ANT500

- **Role**: needed for L10 jamming lab and any RF-TX experiments outside the CC1101's modulation/power envelope.
- **Must match**: **genuine HackRF One** from Great Scott Gadgets, ideally with the 0.5 PPM TCXO upgrade and an aluminum enclosure. Nooelec's official bundle includes the ANT500 telescoping antenna which covers 75 MHz – 1 GHz.
- **Watch out for**: clones marketed as "HackRF One" that lack the TCXO upgrade — output frequency stability suffers. The Nooelec-branded bundle is the safest mainstream Amazon listing.
- **Candidate**: [Nooelec HackRF Complete Bundle (HackRF One + 0.5 PPM TCXO + ANT500 + USB + SMA adapters)](https://www.amazon.com/NooElec-HackRF-Complete-Bundle-Enclosure/dp/B0BKJGKCDP) — best one-box option for Semaeopus L10.
- **Search**: [hackrf one bundle](https://www.amazon.com/s?k=hackrf+one+bundle)
- **Approx price**: $330–390 for the full bundle

---

## Substitution principles

If a specific link is dead, use this decision tree:

1. **Try the search URL.** Pick the top result with > 50 reviews, > 4.0 stars, and clear specs in the description.
2. **Verify the key specs** in the "Must match" line above for that item.
3. **Avoid counterfeits**: if the price is significantly below the
   median for the category (e.g. "RTL-SDR for $12"), it almost
   certainly is one.
4. **Check the seller**: Adafruit, SparkFun, EBYTE, HiLetgo, ELEGOO,
   Nooelec, RTL-SDR Blog — all reliable. Random no-name vendors with
   < 100 reviews are higher risk.
5. **If in doubt, buy a 2-pack** — same per-unit cost as a single,
   and you get a spare for when the magic smoke escapes during
   bring-up.

## Non-Amazon alternatives worth knowing

- **AliExpress** is usually 30–50 % cheaper for generic CC1101 / sensor
  boards but takes 2–4 weeks.
- **Mouser / Digi-Key** carry the SparkFun and Adafruit variants of
  every sensor here — pricier but guaranteed authentic and same-day
  shipping.
- **PiShop.us / Pimoroni** are the safest official-Pico sources if
  you want to avoid resellers.

---

*Last verified: 2026-06-01. If you spot a dead link or better
candidate, please open an issue on
[GitHub](https://github.com/haxorthematrix/semaeopus/issues).*
