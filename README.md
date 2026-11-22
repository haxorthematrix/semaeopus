# Semaeopus

[![tests](https://img.shields.io/badge/tests-48%20passing-brightgreen)](#running-the-tests)
[![license](https://img.shields.io/badge/license-MIT%20%2F%20CC--BY--SA-blue)](LICENSE)
[![site](https://img.shields.io/badge/site-semaeopus.net-3df97f)](https://semaeopus.net)

**A realistic CubeSat hacking platform.** Build a FlatSat satellite and
ground station from two ESP32 "Cheap Yellow Display" boards and a Pi Pico
attacker radio (or the original all-Pico breadboard build), *or* run the
whole thing in a software-only simulator on your laptop. Then attack it
across a 13-lesson curriculum that mirrors how real satellite security
fails in the wild.

> *Semaeopus* (Gr. *sēma* "signal" + L. *opus* "work") — a FlatSat /
> education platform inspired by PwnSat and similar bench-style CubeSat
> security testbeds.

---

## Table of contents

1. [What Semaeopus is](#what-semaeopus-is)
2. [Three ways to use it](#three-ways-to-use-it)
3. [Quick start](#quick-start)
4. [Architecture](#architecture)
5. [Bill of materials](#bill-of-materials)
6. [Wiring](#wiring)
7. [Software dependencies](#software-dependencies)
8. [Installation](#installation)
9. [Running the tests](#running-the-tests)
10. [Curriculum](#curriculum)
11. [Repository layout](#repository-layout)
12. [Safety, legality & ethics](#safety-legality--ethics)
13. [License](#license)

---

## What Semaeopus is

Semaeopus reproduces the **TT&C link** (telemetry, tracking & command)
of a modern CubeSat closely enough that the lessons transfer to real
spacecraft work. The on-air protocol is a deliberately simplified
[CCSDS Space Packet] layered on a 2-GFSK CC1101 PHY at **915 MHz (US,
default)** or **433.92 MHz (EU)** — same shape of stack flown today by
small-sat operators, with off-the-shelf boards and modules in place of
the flight integration.

[CCSDS Space Packet]: https://public.ccsds.org/Pubs/133x0b2.pdf

The platform ships with **four security levels** so you can attack
each in turn:

| Level | Authentication           | Confidentiality | Replay defence              | Attacks that still work |
|-------|--------------------------|-----------------|-----------------------------|--------------------------|
| L0    | none (cleartext)         | none            | none                        | replay, injection, eavesdrop |
| L1    | HMAC over body only      | none            | none (HMAC ≠ freshness)     | replay, eavesdrop        |
| L2    | HMAC over `nonce ‖ body` | none            | strict monotonic nonce      | eavesdrop, denial-of-service |
| L3    | + AES-128-CTR            | yes             | strict monotonic nonce      | DoS, side-channel        |

Toggle by changing `SECURITY_LEVEL` in the satellite's `config.py`
(`firmware/cyd_satellite/` or `firmware/satellite/`), or pass
`--security N` to the simulator. The curriculum walks you
through breaking each level.

This is **education**: the goal is for you to leave knowing how real
flight links go wrong and how to defend them, not to attack anyone
else's spacecraft. See [Safety, legality & ethics](#safety-legality--ethics).

---

## Three ways to use it

| Path | Hardware required | Time to first packet | What you can do                  |
|------|-------------------|----------------------|----------------------------------|
| **A. Simulator**       | none — just Python    | ~ 1 minute    | Lessons L04–L12. Replay & inject. End-to-end protocol attacks. |
| **B. Synthetic RF**    | none (+ optional SDR) | ~ 5 minutes   | Lessons L01–L04 via a pre-rendered `.cu8` IQ file. Build a GFSK demodulator. |
| **C. Real hardware**   | ~ $30 per CYD node    | ~ 2 hours     | Everything, including L09's timing side-channel against real silicon and L10's RF jamming with a HackRF. |

You can run paths A and B with zero hardware **today**. Path C is the
full bench-build using the BOM below.

---

## Quick start

```bash
git clone https://github.com/haxorthematrix/semaeopus
cd semaeopus
pip install pyserial pytest

# Terminal 1 — start the virtual satellite
python -m sim.virtual_satellite

# Terminal 2 — operator ground station, plain CLI
python -m groundstation.operator.gs --sim
op> ping
op> req 12
op> safe

# Terminal 3 — attacker passive capture
python -m groundstation.attacker.capture --sim --out cap.jsonl

# Terminal 4 — forge a FORCE_SAFE command (works at L0)
python -m groundstation.attacker.inject --sim --apid 0xFF
```

For the textual TUI dashboard instead of plain CLI:

```bash
pip install textual rich
python -m groundstation.operator.tui --sim
```

For the SDR / GNU Radio path, see [`lessons/L02_demod_gnuradio.md`](lessons/L02_demod_gnuradio.md).

For the full hardware build, jump to
[Installation §C — real hardware](#c-real-hardware).

---

## Architecture

```
   ┌───────────────────────────────────────────────────────────────────────┐
   │                              SEMAEOPUS                                │
   │                                                                       │
   │  ┌──────────────────┐                       ┌─────────────────────┐   │
   │  │ "SATELLITE"      │                       │ OPERATOR GROUND     │   │
   │  │ (FlatSat)        │                       │ STATION             │   │
   │  │                  │   <── 915/433 MHz ──> │                     │   │
   │  │ CYD + CC1101     │       ISM downlink    │ CYD + CC1101        │   │
   │  │ (or Pico + I²C   │       ISM uplink      │  ↕ USB-serial       │   │
   │  │  sensors + OLED) │                       │ Laptop: gs / TUI    │   │
   │  └──────────────────┘                       └─────────────────────┘   │
   │           ▲                                                           │
   │           │                                  ┌─────────────────────┐  │
   │           │                                  │ ATTACKER STATION    │  │
   │           └──── eavesdrop / inject ─────────►│                     │  │
   │                                              │ RTL-SDR v3 (RX)     │  │
   │                                              │ + Pi Pico + CC1101  │  │
   │                                              │   or HackRF (TX/RX) │  │
   │                                              │ Laptop: capture /   │  │
   │                                              │ replay / inject /   │  │
   │                                              │ fuzz / jam / spoof  │  │
   │                                              └─────────────────────┘  │
   └───────────────────────────────────────────────────────────────────────┘
```

In the **simulator**, replace all three radio boxes with
Python processes joined to a UDP multicast group. The protocol layer,
firmware modules, and ground-station code are identical across the two
paths.

| Subsystem        | Real CubeSat                  | Semaeopus analogue                |
|------------------|-------------------------------|-----------------------------------|
| OBC              | STM32, SAMD, MSP430           | ESP32 on the CYD (Pico build: RP2040) |
| UHF Comms        | NanoCom AX100, EnduroSat UHF  | CC1101 @ 915 / 433 MHz            |
| EPS (power)      | GomSpace NanoPower P31u       | CYD light sensor as the solar input (Pico build: INA219) |
| ADCS (attitude)  | Star tracker + IMU + wheels   | Simulated IMU; BOOT button tumbles it (Pico build: MPU6050) |
| Thermal HK       | Multiple PT1000 / thermistors | Simulated drift (Pico build: BME280) |
| RTC / time       | Chip-scale atomic clock       | Software RTC (Pico build: DS3231) |
| Status display   | Ground-side telemetry view    | CYD 2.8″ screen: mode, power, last commands |
| Telemetry beacon | Periodic AX.25 / CCSDS frame  | CCSDS-lite beacon every 10 s      |
| Payload          | Camera, science instrument    | "Camera" simulated — returns JPEG header |

Full design details in [`specification.md`](specification.md).

---

## Bill of materials

All parts are through-hole or pre-soldered on 0.1″ breakouts. No PCBs,
no SMD soldering. Prices are USD, late 2025 retail.

> **Specific Amazon links?** See
> [`hardware/amazon-bom.md`](hardware/amazon-bom.md) — date-stamped
> product candidates for every line item below, with stable search
> URLs, key specs to match, and substitution guidance for when an
> ASIN goes stale.

### CYD build (recommended) — ~ $30 per node

The satellite and the operator ground station are the same hardware:
an ESP32-2432S028R "Cheap Yellow Display" with a CC1101 reached through
its microSD slot. Full build, wiring and flashing guide:
[`hardware/cyd-build.md`](hardware/cyd-build.md).

| # | Part                                                  | Role                               | Qty per node | Approx $ |
|---|-------------------------------------------------------|------------------------------------|-----|---------:|
| 1 | ESP32-2432S028R "Cheap Yellow Display" (CYD)          | OBC / modem + 2.8″ screen          | 1   | 12–18    |
| 2 | CC1101 **868/915 MHz** module (E07-900M10S or similar) | UHF transceiver                    | 1   | 3–8      |
| 3 | microSD sniffer / breakout that plugs into a SD slot  | Breaks the CYD's SPI bus out to 0.1″ | 1 | 3–6      |
| 4 | JST 1.25 mm 4-pin pigtail (CN1 header)                | 3.3 V, GND and GDO0                | 1   | <1       |
| 5 | Dupont jumpers (F-F)                                  | Wiring                             | 7   | <1       |
| 6 | 915 MHz SMA antenna, or 82 mm of 22 AWG wire          | Antenna                            | 1   | 0–5      |

The attacker station is a Pi Pico + 915 MHz CC1101 USB modem (below) plus
a HackRF for spectrum work and jamming.

### Pico breadboard build: satellite (FlatSat) — ~ $35

| #  | Part                                       | Role                                | Qty | Approx $ |
|----|--------------------------------------------|-------------------------------------|-----|---------:|
| 1  | Raspberry Pi Pico (or Pico W / 2 / 2 W)    | OBC + radio controller              | 1   | 4–6      |
| 2  | CC1101 433 MHz module (E07-M1101D or sim.) | UHF transceiver                     | 1   | 3–6      |
| 3  | SSD1306 0.96″ I²C OLED                     | Status display                      | 1   | 3–5      |
| 4  | BME280 I²C breakout                        | Env. telemetry (T/P/RH)             | 1   | 4–7      |
| 5  | MPU6050 I²C breakout (GY-521)              | IMU / ADCS                          | 1   | 2–4      |
| 6  | INA219 I²C breakout                        | Power telemetry                     | 1   | 3–5      |
| 7  | DS3231 I²C RTC + CR2032                    | OBC time                            | 1   | 2–4      |
| 8  | 5 mm LED ×2 (different colours)            | RX/TX activity                      | 2   | <1       |
| 9  | 220 Ω ¼ W resistor ×2                      | LED current limit                   | 2   | <1       |
| 10 | Half-size breadboard (400-tie)             | Build substrate                     | 1   | 4–6      |
| 11 | Dupont jumper kit (M-M, M-F mix)           | Wiring                              | 40  | 4–6      |
| 12 | 22 AWG solid wire, 17 cm (433 MHz)         | ¼-wave whip antenna                 | 1   | <1       |
| 13 | USB cable (matches Pico variant)           | Power + serial console              | 1   | 2–4      |

### Pico operator ground station (alternative to a CYD) — ~ $20 (+ laptop)

| # | Part                                | Role                              | Qty | Approx $ |
|---|-------------------------------------|-----------------------------------|-----|---------:|
| 1 | Raspberry Pi Pico                   | Radio front-end + USB-serial      | 1   | 4–6      |
| 2 | CC1101 433/915 MHz module           | UHF transceiver (match satellite) | 1   | 3–6      |
| 3 | SSD1306 0.96″ I²C OLED              | At-a-glance link status           | 1   | 3–5      |
| 4 | Half-size breadboard                | Build substrate                   | 1   | 4–6      |
| 5 | Dupont wires                        | Wiring                            | 20  | 2–3      |
| 6 | 17 cm / 8.2 cm wire                 | ¼-wave antenna                    | 1   | <1       |
| 7 | USB cable                           | Pico → laptop                     | 1   | 2–4      |

### Attacker ground station (two tiers)

Tier 1 — minimum (~ $45). Sufficient for lessons L00–L09.

| # | Part                                    | Role                          |
|---|-----------------------------------------|-------------------------------|
| 1 | RTL-SDR v3 dongle + bundled antenna     | Wideband RX 24 MHz – 1.7 GHz  |
| 2 | Raspberry Pi Pico                       | Active-TX front-end           |
| 3 | CC1101 433/915 MHz module               | Active-TX transceiver         |
| 4 | Breadboard + Dupont + wire antenna      | (as per operator GS)          |

Tier 2 — recommended (~ $360 total). Unlocks L10 (jamming) and the
GPS-spoof extension.

| # | Part         | Role                                  | Approx $ |
|---|--------------|---------------------------------------|---------:|
| 1 | HackRF One   | 1 MHz – 6 GHz half-duplex SDR         | 320–360  |
| 2 | ANT500       | Telescopic antenna for HackRF         | 15       |

**Do not buy** CC1101 + PA/LNA combo modules. They blow past ISM
power limits and will get you into trouble.

Detailed substitution notes in
[`hardware/satellite-bom.md`](hardware/satellite-bom.md) and
[`hardware/ground-station-bom.md`](hardware/ground-station-bom.md).
**Specific Amazon links** in
[`hardware/amazon-bom.md`](hardware/amazon-bom.md).

---

## Wiring

### CYD ↔ CC1101 (CYD satellite and ground station)

| CC1101 pin | CYD source            | ESP32 GPIO | Notes                                   |
|------------|-----------------------|------------|-----------------------------------------|
| SCK        | microSD sniffer CLK   | 18         | VSPI bus (the display uses HSPI)        |
| MOSI (SI)  | microSD sniffer CMD   | 23         |                                         |
| MISO (SO)  | microSD sniffer DAT0  | 19         |                                         |
| CSN        | microSD sniffer CD/DAT3 | 5        |                                         |
| GDO0       | CN1 IO27              | 27         | Check CN1's order on your board's silk  |
| VCC        | CN1 3.3V              | —          | **3.3 V only.**                         |
| GND        | CN1 GND               | —          |                                         |

Leave the sniffer's own card socket empty. Full pin map, including every
on-board peripheral: [`firmware/shared/cyd_pins.py`](firmware/shared/cyd_pins.py).

### Pi Pico ↔ CC1101 (attacker modem, and the Pico breadboard build)

The same Pi Pico ↔ CC1101 SPI wiring is used on every Pico board
(attacker modem, and the Pico satellite / operator if you build those).
The Pico satellite adds the housekeeping sensors on top.

### Pi Pico pin map (satellite — all parts)

```
                  ┌─────── USB ───────┐
              GP0 │ 1               40│ VBUS         (5 V from USB — unused)
              GP1 │ 2               39│ VSYS         (1.8–5.5 V battery in)
              GND │ 3               38│ GND
              GP2 │ 4               37│ 3V3 EN
   SDA0 ◀── GP4   │ 6               36│ 3V3 OUT  ──▶ to all 3V3 rails
   SCL0 ◀── GP5   │ 7               35│ ADC_VREF
              GND │ 8               33│ GND
              GP12│16               25│ GP19  ─▶ MOSI    (CC1101 SI)
   CSn  ◀── GP13  │17               24│ GP18  ─▶ SCK     (CC1101 SCK)
 RX-LED ◀── GP14  │19               22│ GP17  ─▶ TX-LED
              GP15│20               21│ GP16  ◀─ MISO    (CC1101 SO)
   GDO0  ◀── GP10 │14               26│ GP20  ─▶ SDA1   (DS3231 only)
                                    27│ GP21  ─▶ SCL1   (DS3231 only)
                  └───────────────────┘
```

### CC1101 ↔ Pi Pico (all boards)

| CC1101 pin | Pi Pico pin     | Notes                                    |
|------------|-----------------|------------------------------------------|
| VCC        | 3V3 OUT (pin 36)| **3V3 only.** 5 V will destroy the chip. |
| GND        | GND             | Any GND pin                              |
| CSN        | GP13            | SPI chip-select                          |
| SCK        | GP18            | SPI clock                                |
| MOSI       | GP19            | SPI MOSI                                 |
| MISO       | GP16 (pin 21)   | SPI0 MISO (GP12 is not an SPI0 pin)      |
| GDO0       | GP10            | Packet-end interrupt                     |
| GDO2       | (unused)        | Leave floating                           |

### I²C bus 0 — sensors + display (satellite only)

All four devices share `SDA = GP4` / `SCL = GP5`, plus 3V3 / GND. The
breakouts ship with on-board pull-ups, so no external resistors are
typically needed. If you see flaky reads, add 4.7 kΩ from each line to
3V3.

| Device  | Default address | Notes                                  |
|---------|-----------------|----------------------------------------|
| SSD1306 | 0x3C            | 0x3D on some boards — check the silk   |
| BME280  | 0x76            | 0x77 if SDO floats                     |
| MPU6050 | 0x68            | 0x69 if AD0 tied high                  |
| INA219  | 0x40            | Configurable via A0/A1 solder bridges  |

### I²C bus 1 — RTC (separate bus avoids the MPU6050/DS3231 0x68 collision)

| Device  | Default address | SDA  | SCL  |
|---------|-----------------|------|------|
| DS3231  | 0x68            | GP20 | GP21 |

### LEDs

```
   GP14 (RX) ── 220 Ω ──[GRN LED]── GND   (active high)
   GP17 (TX) ── 220 Ω ──[RED LED]── GND   (active high)
```

### Antenna

- **915 MHz** (US, default): 22 AWG solid wire, **82 mm** long, or a 915 MHz SMA antenna.
- **433.92 MHz** (EU/R1): same wire, **170 mm** long.

Use a CC1101 module matched for the band you run; 433 MHz modules
perform poorly at 915 MHz.

Keep antennas vertical and the boards 1–3 m apart on the bench. Closer
than about 30 cm saturates the receivers (RSSI near -20 dBm).

### ASCII breadboard

A full ASCII breadboard view is in
[`hardware/wiring-satellite.md`](hardware/wiring-satellite.md), and
the ground-station variants are in
[`hardware/wiring-ground-station.md`](hardware/wiring-ground-station.md).

---

## Software dependencies

### Required (any path)

| Package            | Why                                              |
|--------------------|--------------------------------------------------|
| Python 3.11+       | All host code                                    |
| `pyserial`         | USB-serial to Pico front-ends                    |
| `pytest`           | Test suite                                       |

```bash
pip install pyserial pytest
```

### Optional — TUI dashboard

| Package            | Why                                              |
|--------------------|--------------------------------------------------|
| `textual`          | Interactive terminal UI for the operator         |
| `rich`             | Coloured log / table rendering inside TUI        |

```bash
pip install textual rich
```

### Optional — SDR / GNU Radio path (lessons L01–L03 with real RX)

| Package            | Why                                              |
|--------------------|--------------------------------------------------|
| `gnuradio` ≥ 3.10  | Spectrum / demod flowgraphs                      |
| `gr-satellites`    | Reference CCSDS / AX.25 decoder                  |
| `rtl-sdr`          | RTL-SDR dongle driver                            |
| `hackrf`           | HackRF One driver (optional, for L10)            |
| `gqrx` or `SDR++`  | Spectrum visualisation                           |
| `inspectrum`       | Offline IQ inspection                            |

Debian/Ubuntu: `sudo apt install gnuradio gr-satellites rtl-sdr hackrf gqrx-sdr inspectrum`.

### Optional — security level 3 (AES-CTR + HMAC)

| Package            | Why                                              |
|--------------------|--------------------------------------------------|
| `pycryptodome`     | AES-128-CTR on CPython (MicroPython builds it from built-in `cryptolib` AES) |

```bash
pip install pycryptodome
```

### Optional — hardware path

| Package            | Why                                              |
|--------------------|--------------------------------------------------|
| `mpremote`         | Copy firmware to the boards (`tools/deploy.sh`)  |
| `esptool`          | Flash MicroPython onto the CYDs                  |

```bash
python3 -m pip install mpremote esptool
```

Plus MicroPython on each board: `ESP32_GENERIC` for the CYDs (see
[`hardware/cyd-build.md`](hardware/cyd-build.md)) and the RP2040 `.uf2`
for each Pico (see [`hardware/install-os.md`](hardware/install-os.md)).

---

## Installation

### A. Simulator (no hardware)

```bash
git clone https://github.com/haxorthematrix/semaeopus
cd semaeopus
pip install pyserial pytest

python -m pytest tests/ -q          # expect: all pass (a few skip without pycryptodome / textual / mpy-cross)
python -m sim.virtual_satellite     # leave running in one terminal
```

In a second terminal:

```bash
python -m groundstation.operator.gs --sim
op> ping       # should see PONG within ~1 s
op> req 10     # housekeeping telemetry on demand
op> safe       # FORCE_SAFE — satellite reports M1 on next beacon
```

Jump to [`lessons/L04_telemetry_decode.md`](lessons/L04_telemetry_decode.md)
or any subsequent lesson — they all run sim-only by default.

### B. Synthetic RF (no SDR)

```bash
# Same checkout + Python install as path A, then:
python -m tools.generate_iq         # writes captures/baseline.iq (5 MB)
python -m tools.demod_iq            # recovers all 11 frames, prints hex + CRC
```

Open `captures/baseline.iq` in `gqrx` (File → I/Q file, type "Raw I/Q",
sample rate 1 Msps). Lesson L02 walks the GNU Radio Companion build.

### C. Real hardware

#### CYD build (recommended)

Full step-by-step guide to the parts, wiring and flashing:
[`hardware/cyd-build.md`](hardware/cyd-build.md). In short:

```bash
# 1. Flash MicroPython (ESP32_GENERIC) onto each CYD with esptool, and the .uf2 onto the Pico
# 2. Check each radio
tools/deploy.sh bringup-cyd  /dev/cu.usbserial-XXXX
tools/deploy.sh bringup-pico /dev/cu.usbmodemXXXX
# 3. Deploy
tools/deploy.sh cyd-satellite /dev/cu.usbserial-AAAA
tools/deploy.sh cyd-ground    /dev/cu.usbserial-BBBB
tools/deploy.sh pico-modem    /dev/cu.usbmodemCCCC
# 4. Operate and attack
python -m groundstation.operator.gs --port /dev/cu.usbserial-BBBB
python -m groundstation.attacker.capture --port /dev/cu.usbmodemCCCC --out cap.jsonl
```

#### Pico breadboard build

#### 1. Flash MicroPython to each Pico

Hold **BOOTSEL** while plugging the Pico in. It mounts as `RPI-RP2`.
Drag the matching `.uf2` (see table in
[`hardware/install-os.md`](hardware/install-os.md)). Repeat for the
second Pico.

#### 2. Wire the satellite

Follow the [Wiring](#wiring) section above. Bring up in seven stages,
running one bring-up script after each — see
[`hardware/bringup-checks.md`](hardware/bringup-checks.md):

```bash
mpremote connect /dev/ttyACM0 run bringup/01_blink.py        # MicroPython alive
mpremote connect /dev/ttyACM0 run bringup/02_i2c_scan.py     # I²C devices respond
mpremote connect /dev/ttyACM0 run bringup/03_oled_test.py    # display works
mpremote connect /dev/ttyACM0 cp -r firmware/satellite/lib :/bringup_lib
mpremote connect /dev/ttyACM0 run bringup/04_sensor_smoke.py # sensors read OK
mpremote connect /dev/ttyACM0 run bringup/05_spi_loopback.py # SPI wiring OK
mpremote connect /dev/ttyACM0 run bringup/06_cc1101_id.py    # CC1101 fingerprint
# 07_radio_loopback.py needs two Picos+CC1101s; runs at the next stage
```

Each script prints **PASS** or **FAIL** with a hint about what to
check on failure.

#### 3. Deploy the full firmware

```bash
tools/deploy.sh pico-satellite /dev/ttyACM0

# Operator's Pico — the GS front-end modem
tools/deploy.sh pico-modem     /dev/ttyACM1
```

Reset both Picos. Within ~ 10 s the satellite emits its first beacon.

#### 4. Run the operator GS

```bash
python -m groundstation.operator.gs --port /dev/ttyACM1
```

You should see beacon, HK_TLM, ADCS_TLM, EPS_TLM streams. Now you're
on the **same** functional setup as the simulator — the rest of the
curriculum works identically.

---

## Running the tests

```bash
python -m pytest tests/ -q
# expect: 48 passed in ~25 s (L3 / TUI / MicroPython-compile tests skip
# without pycryptodome / textual / mpy-cross)
```

Coverage:

| Test file                | What it verifies                                      |
|--------------------------|-------------------------------------------------------|
| `test_space_packet.py`   | Codec round-trips, CRC bit-flip detection, all four security levels, L1/L2 replay rules, fuzz round-trip |
| `test_handlers.py`       | TC dispatcher — ping, set-mode, arm/fire ordering, illegal transitions |
| `test_sim_e2e.py`        | Spawns the virtual satellite as a subprocess and asserts an injected `FORCE_SAFE` actually flips the satellite into SAFE mode |
| `test_iq.py`             | GFSK modulator self-check; regenerates `captures/baseline.iq` if missing |
| `test_tui_smoke.py`      | Operator TUI imports cleanly and `OperatorState` produces monotonic nonces |
| `firmware/test_cyd_satellite.py` | The CYD satellite firmware on a register-level simulated CC1101: telemetry, commands, L0/L2/L3, commands arriving mid-transmission |
| `firmware/test_modems.py` | CYD ground station and Pico modem: line protocol, CFG/BW/PWR, error handling, continuous reception at real 9600 bps timing |
| `firmware/test_display_and_build.py` | CYD screen driver output; every firmware file compiles with MicroPython's `mpy-cross` |

The firmware tests stage each board exactly as `tools/deploy.sh` would
and run the MicroPython code on CPython against simulated hardware
(`tests/firmware/mpsim.py`).

---

## Curriculum

All 13 lessons (L00–L12) are written and runnable today.

| #   | Title                                     | Hardware required        | Sim only? |
|-----|-------------------------------------------|--------------------------|-----------|
| L00 | Build & first beacon                      | satellite + operator     | partial   |
| L01 | Spectrum survey                           | + RTL-SDR (or use IQ)    | use IQ    |
| L02 | Demod in GNU Radio                        | + GNU Radio              | use IQ    |
| L03 | Frame sync & CRC                          | + Python                 | use IQ    |
| L04 | Telemetry decode                          | (any)                    | ✓         |
| L05 | Replay attack                             | + attacker Pico          | ✓         |
| L06 | Command injection                         | + attacker Pico          | ✓         |
| L07 | HMAC bypass via replay (L1)               | (any)                    | ✓         |
| L08 | Counter-bound HMAC (L2)                   | (any)                    | ✓         |
| L09 | Timing side-channel — recovers full tag   | (any)                    | ✓         |
| L10 | Encryption + jam-and-replay (L3)          | + HackRF for full lab    | partial   |
| L11 | Beacon spoofing                           | (any)                    | ✓         |
| L12 | Capstone                                  | everything               | ✓         |

Each lesson is a self-contained Markdown file with build steps,
expected captures, discussion questions, and a defensive lab. See
[`lessons/`](lessons/).

---

## Repository layout

```
specification.md          ← full design + threat model + roadmap
README.md                 ← this file
LICENSE                   ← MIT (code) + CC-BY-SA 4.0 (lessons & docs)

docs/                     ← project website (semaeopus.net)
  index.html
  style.css
  assets/logo.svg
  CNAME

hardware/                 ← hardware references
  satellite-bom.md
  ground-station-bom.md
  wiring-satellite.md     ← ASCII breadboard diagram
  wiring-ground-station.md
  install-os.md           ← MicroPython flash, mpremote setup
  bringup-checks.md       ← 7-stage wire-then-test sequence
  cyd-build.md            ← CYD build: parts, wiring, flashing, first test

bringup/                  ← MicroPython smoke scripts
  01_blink.py … 07_radio_loopback.py
  cyd/                    ← CYD radio bring-up (MicroPython + Arduino)

firmware/
  cyd_satellite/          ← CYD satellite: main, config, sensor stand-ins
  cyd_ground/             ← CYD operator ground station (modem + screen)
  shared/                 ← modem.py, cyd_display.py, cyd_pins.py
  satellite/              ← MicroPython OBC for the Pico FlatSat;
                            obc/, comms/ and lib/cc1101.py are shared by the CYD build
    config.py             ← per-build knobs (frequency, security level, keys)
    main.py               ← scheduler + handlers
    lib/                  ← CC1101 + sensor drivers
    obc/                  ← scheduler, modes, housekeeping, ADCS, EPS
    comms/                ← beacon, handlers, security wrappers
  gs_frontend/            ← Pico USB modem (attacker, or a Pico ground station)

groundstation/
  operator/
    gs.py                 ← interactive CLI
    tui.py                ← textual TUI dashboard
  attacker/
    capture.py            ← passive logger
    replay.py             ← replay captured frames
    inject.py             ← build & TX an arbitrary TC
    fuzz.py               ← APID/length fuzzer
    jam.py                ← bus-level DoS (noise / flood-TC / replay-spam)
    spoof_beacon.py       ← impersonate the satellite
    gnuradio/             ← GNU Radio RX + TX recipes
  shared/                 ← link.py, decoder.py — common to operator + attacker

sim/                      ← software-only simulator
  virtual_satellite.py    ← reuses real OBC modules over UDP "ether"
  radio_bus.py            ← UDP multicast radio with synthesized RSSI
  sim_link.py             ← drop-in Link for the host tools
  fakes.py                ← FakeBME280 / FakeMPU6050 / FakeINA219 / FakeDS3231

protocol/
  space_packet.py         ← CCSDS-lite codec, shared everywhere

tools/
  generate_iq.py          ← GFSK IQ synthesis (2.7 s @ 1 Msps)
  demod_iq.py             ← pure-Python reference demodulator
  verify_iq.py            ← modulator self-check
  cu8_to_cfile.py         ← .cu8 → GNU Radio .cfile
  timing_oracle.py        ← localhost oracle for L09
  timing_attack.py        ← byte-by-byte tag recovery
  deploy.sh               ← copy firmware onto a board (CYD or Pico)

captures/
  baseline.iq             ← 5 MB synthetic capture
  baseline.jsonl          ← oracle (decoded frames)

tests/                    ← pytest suite (firmware/ runs the board code on simulated hardware)
lessons/                  ← L00 – L12 curriculum
```

---

## Safety, legality & ethics

1. **Bench operation only.** The default, 915 MHz at 0 dBm, is a
   low-power device under US 47 CFR 15.249. It won't reach orbit — but
   it will reach a neighbour with an SDR. For EU/R1 use 433.920 MHz:
   set `RF_FREQ_HZ = 433_920_000` in the satellite's `config.py` and pass
   `--freq 433920000` to the laptop tools.
2. **No external power amplifiers.** A CC1101 + PA module turns
   Semaeopus into an illegal local jammer. Don't build one.
3. **Never aim at amateur satellite frequencies** (435–438 MHz UHF).
   CC1101 *can* tune there; the EU setting, 433.920 MHz, is
   deliberately below the amateur segment.
4. **Practice attacks only on systems you own** or have explicit
   written permission to test. The L09 timing oracle, the L10
   jammer, and the L12 capstone are educational tools — treat them
   as you would Metasploit.
5. **The HackRF jam-and-replay lab (L10)** can saturate ISM-band
   receivers across a wide radius. Use a 50 Ω dummy load on the
   HackRF output for indoor labs, or work inside a Faraday cage.

Detailed legal/safety discussion is in
[`specification.md`](specification.md) §9.

---

## License

- **Code** — MIT (see [LICENSE](LICENSE))
- **Lessons, hardware docs, this README, the project website** —
  Creative Commons Attribution-ShareAlike 4.0 International
  (CC-BY-SA 4.0)

You may freely reuse, modify, teach from, and commercialise the code.
The lessons and documentation may be reused under the same share-alike
terms — re-publish improvements under CC-BY-SA so others benefit.

---

## Status & contributing

Current state: **v0.3 — CYD hardware build running.**

- All 13 lessons written and runnable in the simulator.
- 48 tests passing, including the board firmware on simulated hardware.
- Validated on physical hardware at 915 MHz: CYD satellite beaconing and
  telemetry, CYD ground station reception, operator ping/pong, and the
  attacker Pico's capture, replay and injection (lessons L05–L06).
- Not yet exercised on hardware: security levels L1–L3, the L10 jamming
  lab, and the Pico breadboard satellite.

Issues, PRs, and lesson contributions welcome at
[github.com/haxorthematrix/semaeopus](https://github.com/haxorthematrix/semaeopus).

If you build the hardware, please share your bring-up log and any
register-tuning notes you discover for the CC1101.

Project site: [semaeopus.net](https://semaeopus.net).
