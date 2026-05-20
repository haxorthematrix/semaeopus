# Bring-up checks — wire-then-test in seven stages

The biggest reason a build fails on first boot is "I wired everything
at once, none of it works, I don't know where to look." This guide
breaks the build into seven verifiable stages. After each stage, run
the corresponding bring-up script and confirm it prints **PASS** before
moving on.

If you already have all components wired, you can still run the seven
checks in order — they don't interfere with each other.

> Pre-req: you've finished [`install-os.md`](install-os.md) and
> `mpremote devs` shows your Pico.

---

## Stage 1 — Power up the Pico (no other parts)

1. Plug the Pico into your laptop via USB. It should enumerate as
   `/dev/ttyACM0` (Linux/macOS) or a new COM port (Windows).
2. Run:
   ```bash
   mpremote connect /dev/ttyACM0 run bringup/01_blink.py
   ```
3. Watch the onboard LED — ten quick blinks — and look for
   `PASS: pico alive, MicroPython responsive`.

If the LED doesn't blink, MicroPython didn't take. Re-flash the .uf2.
If the LED blinks but you don't see PASS, your `mpremote` connection
chose the wrong port — try `mpremote devs` and pin the right device.

---

## Stage 2 — Build the 3V3 power rail

Lay the breadboard out:

- Connect Pico **3V3 OUT (pin 36)** to the breadboard's red rail.
- Connect Pico **GND** (any of pins 3/8/13/18/23/28/33/38) to the
  black rail.

Now power-cycle (unplug + replug USB). Nothing should smoke. If
anything gets warm to the touch, **unplug immediately** and recheck.

No bring-up script here — this is a smell-test stage.

---

## Stage 3 — Wire the I²C bus 0 sensors

Add to the breadboard (all on the same 3V3 / GND rails):

- **SSD1306 OLED**: VCC→3V3, GND→GND, SDA→GP4, SCL→GP5
- **BME280**: same VCC/GND, SDA→GP4, SCL→GP5
- **MPU6050**: same, SDA→GP4, SCL→GP5
- **INA219**: same, SDA→GP4, SCL→GP5

These four share the bus 0 SDA/SCL pair. They have on-board pull-ups,
so no external resistors needed.

Then run:
```bash
mpremote connect /dev/ttyACM0 run bringup/02_i2c_scan.py
```

Expect to see (note: bus 1 will print "no devices" — that's fine, we
haven't wired the RTC yet):

```
--- bus 0  (SDA=GP4  SCL=GP5) ---
  0x3C  SSD1306 OLED
  0x40  INA219 (power)
  0x68  MPU6050 (IMU)
  0x76  BME280 (env)
```

### Troubleshooting Stage 3

| Symptom                                         | Likely cause / fix                                                                                 |
|-------------------------------------------------|----------------------------------------------------------------------------------------------------|
| `bus error: [Errno 5] EIO`                      | SDA or SCL shorted to 3V3 or GND. Pull the wires and recheck.                                      |
| Empty scan (`no devices responded`)             | SDA/SCL swapped, or the whole bus has no pull-up. Try adding 4.7 kΩ from each line to 3V3.         |
| `MISSING 0x3C` (no OLED)                        | OLED might be at 0x3D — many "0.96 inch" boards ship with the address-select solder bridge flipped.|
| `MISSING 0x68` (no MPU6050)                     | AD0 pin tied high → MPU is at 0x69. Either pull AD0 low or update `SECURITY_LEVEL`-style configs.  |
| `MISSING 0x76` (no BME280)                      | BME280 SDO floating → address is 0x77. Tie SDO to GND for 0x76, or update `config.py`.             |
| Multiple `MISSING` together                     | Stage 2 power rail problem. Verify 3V3 reads 3.30 V on a multimeter at the far end of the rail.    |

---

## Stage 4 — Verify the OLED actually displays

```bash
mpremote connect /dev/ttyACM0 run bringup/03_oled_test.py
```

You should see a frame around the screen, a checkerboard in the lower
half, and two lines of text. If the screen lights up but shows static
or scrambled pixels, the I²C clock may be too fast — drop
`freq=400_000` to `freq=100_000` in `03_oled_test.py` and retry.

---

## Stage 5 — Add the RTC on bus 1

- **DS3231**: VCC→3V3, GND→GND, SDA→**GP20**, SCL→**GP21**
- Make sure the CR2032 backup cell is in (most boards ship with it).

Re-run the I²C scan — this time bus 1 should also report:
```
--- bus 1  (SDA=GP20  SCL=GP21) ---
  0x68  DS3231 (RTC)
```

Then run the full sensor smoke test:
```bash
mpremote connect /dev/ttyACM0 cp -r firmware/satellite/lib :/bringup_lib
mpremote connect /dev/ttyACM0 run bringup/04_sensor_smoke.py
```

Expect four PASS lines. The DS3231 check waits 1.2 seconds and
confirms the seconds field advances — if it doesn't, the cell is dead
or the crystal isn't oscillating; replace the board.

---

## Stage 6 — Wire and verify SPI to the CC1101

**Before plugging in the CC1101**, place a single Dupont wire between
**GP19 (MOSI)** and **GP12 (MISO)**. Then run:
```bash
mpremote connect /dev/ttyACM0 run bringup/05_spi_loopback.py
```

The TX hex and RX hex must match. If they don't, you've miswired SPI
pins. **Don't add the CC1101 yet** — fix SPI first.

Now remove that loopback jumper and wire the CC1101 per
[`wiring-satellite.md`](wiring-satellite.md):

| CC1101 | Pi Pico        |
|--------|----------------|
| VCC    | 3V3 OUT (36)   |
| GND    | GND            |
| CSN    | GP13           |
| SCK    | GP18           |
| MOSI   | GP19           |
| MISO   | GP12           |
| GDO0   | GP10           |

> **3V3 only.** Driving the CC1101 from 5 V will destroy it.

Then:
```bash
mpremote connect /dev/ttyACM0 run bringup/06_cc1101_id.py
```

Expect `PARTNUM = 0x00` and a non-zero / non-0xFF `VERSION`. See the
troubleshooting block inside the script if not.

---

## Stage 7 — Two-radio link check

You need a second Pico+CC1101 (e.g. your operator GS Pico) wired the
same way, with the same 17 cm antenna.

On both Picos, copy the firmware lib first:
```bash
mpremote connect /dev/ttyACM0 cp -r firmware/satellite/lib :/lib
mpremote connect /dev/ttyACM1 cp -r firmware/satellite/lib :/lib
```

Open two terminals. In one:
```bash
mpremote connect /dev/ttyACM0 run bringup/07_radio_loopback.py tx
```
In the other:
```bash
mpremote connect /dev/ttyACM1 run bringup/07_radio_loopback.py rx
```

The RX side should receive ≥ 10 valid frames in 30 seconds and PASS.
RSSI on a bench-distance link (≥ 30 cm apart) is typically -30 to
-60 dBm.

### Troubleshooting Stage 7

| Symptom                                        | Likely cause                                                                  |
|------------------------------------------------|-------------------------------------------------------------------------------|
| RX prints nothing at all                       | Antenna missing or wrong length. 17 cm for 433.92 MHz; 8.2 cm for 915 MHz.    |
| RX gets junk bytes (CRC fails)                 | Antennas too close (front-end saturating) — move them ≥ 30 cm apart           |
| RX RSSI very low (-100+) but bytes correct     | Antenna is fine; you just have a long link. Nothing wrong.                    |
| RX gets nothing AND `bringup/06_cc1101_id.py` PASSed | Frequency or sync word mismatch — both scripts use defaults; re-run both    |
| Both sides print PASS but main firmware doesn't link | Different CC1101 register config in `firmware/satellite/lib/cc1101.py` — update `RF_FREQ_HZ` etc. in `config.py` and retry |

---

## After all seven PASS

You're ready to deploy the full Semaeopus firmware. Follow
[`firmware/satellite/README.md`](../firmware/satellite/README.md) for
the production upload, then jump to lesson
[L00](../lessons/L00_build_and_first_beacon.md).
