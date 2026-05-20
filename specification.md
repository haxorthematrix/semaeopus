# Semaeopus: A Realistic CubeSat Hacking Platform

> *Semaeopus* (Gr. *sēma* "signal" + *opus* "work") — a flat-sat / FlatSat-style
> educational platform for hands-on satellite communication security training.

---

## 1. Goals & Non-Goals

### Goals
- Reproduce the **TT&C (Telemetry, Tracking & Command)** architecture of a real
  CubeSat closely enough that lessons transfer to real spacecraft work.
- Operate **legally on ISM bands** (433 MHz EU / 915 MHz US) so no amateur
  licence is required for the default configuration.
- Be **buildable from breadboard + Dupont wires + through-hole / pre-soldered
  modules** — no custom PCBs, no SMD soldering.
- Provide a **graduated curriculum** in capture → decode → replay →
  injection → spoofing → crypto-attack → side-channel.
- Use the **Raspberry Pi Pico** (RP2040) as the satellite "OBC + radio
  controller" — same class of MCU as STM32/SAMD parts flown in many real
  CubeSats.
- Let the learner build **two ground stations**: a *legitimate operator*
  station and an *attacker* station, so both sides of the link are visible.

### Non-Goals
- Orbit dynamics modelling at scientific fidelity (we simulate, not solve
  Kepler in real-time).
- Flight-qualified hardware. Components are educational analogues of their
  flight equivalents.
- Encrypted-by-default operation in the v0 build — early lessons rely on
  cleartext so the learner can see what's on the air. Crypto is enabled
  progressively.

---

## 2. System Architecture

```
   ┌─────────────────────────────────────────────────────────────────────┐
   │                       SEMAEOPUS PLATFORM                            │
   │                                                                     │
   │  ┌─────────────────┐                       ┌─────────────────────┐  │
   │  │ "SATELLITE"     │                       │ OPERATOR GROUND     │  │
   │  │ (FlatSat)       │                       │ STATION             │  │
   │  │                 │   <── 433/915 MHz ──> │                     │  │
   │  │ Pi Pico + CC1101│       ISM downlink    │ Pi Pico + CC1101    │  │
   │  │ + housekeeping  │       ISM uplink      │  ↕ USB-serial       │  │
   │  │ sensors & disp  │                       │ Laptop: gs-operator │  │
   │  └─────────────────┘                       └─────────────────────┘  │
   │           ▲                                                         │
   │           │                                ┌─────────────────────┐  │
   │           │                                │ ATTACKER STATION    │  │
   │           └──── eavesdrop / inject ───────►│                     │  │
   │                                            │ RTL-SDR v3 (RX)     │  │
   │                                            │ + Pi Pico + CC1101  │  │
   │                                            │   or HackRF (TX/RX) │  │
   │                                            │ Laptop: gs-attacker │  │
   │                                            │ + GNU Radio         │  │
   │                                            └─────────────────────┘  │
   └─────────────────────────────────────────────────────────────────────┘
```

### 2.1 The Satellite ("FlatSat")
A flat-sat is a CubeSat with its subsystems laid out on a bench instead of
stacked in a 10 cm cube. It is electrically identical to the flight unit so
software, protocols, and operations can be exercised end-to-end.

Subsystems modelled:

| Subsystem        | Real CubeSat                  | Semaeopus analogue                |
|------------------|-------------------------------|-----------------------------------|
| OBC              | STM32, SAMD, MSP430           | Raspberry Pi Pico (RP2040)        |
| UHF Comms        | NanoCom AX100, EnduroSat UHF  | CC1101 @ 433 / 915 MHz            |
| EPS (power)      | GomSpace NanoPower P31u       | INA219 reading a "battery" rail   |
| ADCS (attitude)  | Star tracker + IMU + wheels   | MPU6050 IMU                       |
| Thermal HK       | Multiple PT1000 / thermistors | BME280 (T / P / RH)               |
| RTC / time       | Chip-scale atomic clock       | DS3231                            |
| Telemetry beacon | Periodic AX.25 / CCSDS frame  | CCSDS-inspired beacon every 10 s  |
| Payload          | Camera, science instrument    | "Camera" simulated — returns JPEG |

### 2.2 The Operator Ground Station
The "legitimate" side. A Raspberry Pi Pico + CC1101 acts as the radio
front-end, communicating over USB-serial with a Python application
(`gs-operator`) running on the learner's laptop. The operator station knows
the link parameters and (in later lessons) the keys.

### 2.3 The Attacker Ground Station
Pure RX is done with an **RTL-SDR v3** ($30) — sufficient to demodulate the
satellite downlink in GNU Radio. For active attacks (replay, injection,
spoofing) the learner uses either:
- a **second Pi Pico + CC1101** (cheap, $15, but limited to the modulations
  the chip supports — perfect for replay and command injection), or
- a **HackRF One** (~$330) for arbitrary-waveform TX, jamming, and
  GPS-spoofing extensions.

---

## 3. RF Design

### 3.1 Band selection (region-dependent)

| Region          | Default freq    | Power limit  | Notes                          |
|-----------------|----------------:|-------------:|--------------------------------|
| EU (R1) ISM     | 433.05–434.79 MHz | 10 mW ERP  | 10 % duty cycle on the band    |
| US (R2) ISM     | 902–928 MHz       | 1 W (FHSS) / 36 dBm EIRP | Part 15.247  |
| Worldwide (alt) | 2400–2483.5 MHz   | varies     | Higher path loss, less "sat-like" |

The CC1101 supports 300–348 / 387–464 / 779–928 MHz, so the **same hardware
serves all three regions** — just rebuild the firmware with a different
`RF_FREQ_HZ` constant. The default ships as **433.920 MHz** with a build flag
to switch to **915.000 MHz** for US users.

### 3.2 Modulation

CubeSats today most commonly use **2-GFSK** or **4-GFSK** for downlink at
9600–19200 bps. Semaeopus uses **2-GFSK at 9600 bps** by default — within
CC1101's capabilities and a strong match to flight-typical link parameters.

| Parameter        | Default value      |
|------------------|--------------------|
| Modulation       | 2-GFSK             |
| Bit rate         | 9600 bps           |
| Deviation        | 4.8 kHz            |
| RX bandwidth     | 58 kHz             |
| Preamble         | 32 bits (0xAA × 4) |
| Sync word        | 0xD391 (configurable per lesson) |
| Whitening        | PN9, on            |
| FEC              | none (lesson 0)  → Reed-Solomon (255,223) in lesson 7 |
| CRC              | CRC-16-CCITT      |
| Packet format    | Variable length, length byte first |

### 3.3 Antennas
A simple **17 cm straight wire** (¼-wave at 433 MHz) on each radio is enough
for bench-range work (1–10 m). Provide a 50 Ω SMA-pigtail-to-wire adaptor
in the BOM so users can later swap to a proper antenna without changes
elsewhere. Keep both stations on opposite ends of the bench to avoid
overloading the RX front-ends.

> **Power & legality reminder.** CC1101 modules are 10 dBm (10 mW). With a
> simple wire antenna this is well inside ISM limits in every region listed
> above. Do not add an external power amplifier without rechecking your
> local rules.

---

## 4. Protocol Stack

The on-air protocol is a deliberately simplified version of
**CCSDS Space Packet Protocol** layered inside a CC1101 PHY frame. It is
the same conceptual stack used by most modern CubeSats; lessons explore
how each layer fails when implemented naively.

### 4.1 PHY (CC1101)
```
[ Preamble 0xAA…AA | Sync 0xD391 | LEN | PAYLOAD (CCSDS) | CRC16 ]
```

### 4.2 Transport — CCSDS-lite Space Packet

```
 Bit:   0                                 16                     32        48
       ┌──────────┬─────┬───────┬───────┬─────────────┬──────────┬────────────────────┐
       │ Version  │ TYP │  SEC  │ APID  │ Seq Flags+  │ Pkt Data │  USER DATA  + CRC  │
       │ (3 b)    │(1b) │(1b)   │(11 b) │ Seq Count   │ Length   │                    │
       │          │ 0=TM│ 0=N/A │       │ (16 b)      │ (16 b)   │                    │
       │          │ 1=TC│       │       │             │          │                    │
       └──────────┴─────┴───────┴───────┴─────────────┴──────────┴────────────────────┘
```

| Field          | Width | Meaning                                                    |
|----------------|-------|------------------------------------------------------------|
| Version        | 3 b   | Always 000                                                 |
| Type (TYP)     | 1 b   | 0 = TM (downlink), 1 = TC (uplink command)                 |
| Sec hdr flag   | 1 b   | 1 if a security header (HMAC / nonce) is present           |
| APID           | 11 b  | Application Process ID — see table 4.4                     |
| Seq Flags      | 2 b   | 11 = standalone (we don't fragment)                        |
| Seq Count      | 14 b  | Monotonic counter (wraps at 16383) — anti-replay material  |
| Pkt Data Len   | 16 b  | (Payload bytes − 1)                                        |
| User Data      | N×8   | Command/telemetry-specific                                 |
| CRC            | 16 b  | CRC-16-CCITT over the whole space packet                   |

### 4.3 Optional Security Header (later lessons)

```
[ Nonce (8 B) ][ HMAC-SHA256-truncated-to-8 B (8 B) ]  → 16 B total
```

Lessons progressively enable:
1. **L0**: no security header, no auth, no encryption — replay/injection
   trivial.
2. **L1**: HMAC only (no counter binding) — replay still works, signature
   doesn't.
3. **L2**: HMAC over (nonce ‖ packet); receiver enforces strictly
   increasing nonce — replay blocked, injection requires key compromise.
4. **L3**: AES-128-CTR encryption of user-data + HMAC — eavesdropping
   blocked too.

### 4.4 APIDs

| APID  | Direction | Name           | Purpose                                  |
|-------|-----------|----------------|------------------------------------------|
| 0x001 | TM        | BEACON         | Periodic call-sign + status              |
| 0x010 | TM        | HK_TLM         | Housekeeping telemetry                   |
| 0x011 | TM        | ADCS_TLM       | Attitude telemetry                       |
| 0x012 | TM        | EPS_TLM        | Power telemetry                          |
| 0x020 | TM        | EVENT          | Event-driven (warning, fault)            |
| 0x030 | TM        | PAYLOAD_DATA   | "Camera" image chunk                     |
| 0x080 | TC        | PING           | No-op, expects 0x081 PONG                |
| 0x081 | TM        | PONG           | Response to PING                         |
| 0x082 | TC        | REQ_TLM        | Request specific TLM frame               |
| 0x083 | TC        | SET_MODE       | NOMINAL / SAFE / PAYLOAD / IDLE          |
| 0x084 | TC        | ARM_PAYLOAD    | Two-step arming                          |
| 0x085 | TC        | FIRE_PAYLOAD   | "Take photo" — only after ARM            |
| 0x086 | TC        | UPLOAD_TLE     | Update simulated orbital elements        |
| 0x087 | TC        | TIME_SET       | Set OBC time                             |
| 0x088 | TC        | KEY_ROTATE     | Rotate session key (used in L2 / L3)     |
| 0x0FF | TC        | FORCE_SAFE     | Force safe mode (no-arg)                 |

---

## 5. Hardware Selection

See `hardware/satellite-bom.md` and `hardware/ground-station-bom.md` for
exact part numbers, suppliers, and rough pricing. Highlights:

**Satellite (~ $35)**
- Raspberry Pi Pico (or Pico 2 / Pico W) — RP2040 MCU
- CC1101 433 MHz module (E07-M1101D or generic) — through-hole pins
- SSD1306 0.96" I²C OLED — status display
- BME280 I²C breakout — environment telemetry
- MPU6050 I²C breakout — IMU (attitude)
- INA219 I²C breakout — power telemetry
- DS3231 I²C RTC — onboard time
- 2× LEDs (RX/TX activity) + 220 Ω resistors
- Half-size breadboard + Dupont kit
- 17 cm whip antenna (or SMA pigtail + wire)

**Operator Ground Station (~ $20 + laptop)**
- Raspberry Pi Pico
- CC1101 module (matching the satellite)
- SSD1306 OLED
- Same antenna
- USB cable to learner's laptop

**Attacker Ground Station (~ $30 minimum, ~ $360 full)**
- *Minimum:* RTL-SDR v3 + a second Pico/CC1101 — $30 + $15
- *Recommended:* HackRF One — $330 (adds arbitrary-waveform TX, useful for
  jamming and GPS spoofing labs)

---

## 6. Firmware Architecture (satellite)

Language: **MicroPython** for accessibility; a parallel C/Pico-SDK port
lives under `firmware/satellite/c/` for learners who want lower-latency
interrupt-driven RX or to compare resource usage to a real flight OBC.

```
firmware/satellite/
├── main.py                # boot, task scheduler
├── config.py              # frequency, sync word, keys, lesson level
├── lib/
│   ├── cc1101.py          # SPI driver for CC1101
│   ├── ssd1306.py         # OLED
│   ├── bme280.py
│   ├── mpu6050.py
│   ├── ina219.py
│   └── ds3231.py
├── obc/
│   ├── scheduler.py       # cooperative scheduler ("tasks" w/ periods)
│   ├── housekeeping.py    # sensor reads → HK_TLM
│   ├── adcs.py            # IMU read + simulated wheel
│   ├── eps.py             # INA219 read + battery model
│   ├── payload.py         # "camera" simulator
│   └── modes.py           # NOMINAL / SAFE / PAYLOAD / IDLE state machine
├── comms/
│   ├── phy.py             # CC1101 packet TX/RX wrapper
│   ├── space_packet.py    # CCSDS-lite encode/decode
│   ├── security.py        # HMAC / AES-CTR (L1–L3, off in L0)
│   ├── beacon.py          # periodic BEACON emitter
│   └── handlers.py        # APID → handler dispatch
└── tests/                 # host-side pytest for codecs
```

### 6.1 Scheduler
A simple cooperative loop runs five tasks at fixed periods:

| Task           | Period   | APID emitted |
|----------------|---------:|--------------|
| Beacon         | 10 000 ms| 0x001        |
| HK telemetry   |  5 000 ms| 0x010        |
| ADCS telemetry |  2 000 ms| 0x011        |
| EPS telemetry  |  5 000 ms| 0x012        |
| Comms RX poll  |     20 ms| (in/out)     |

### 6.2 Lesson knob
`config.SECURITY_LEVEL = 0` ships by default. Bumping it to 1, 2, 3
enables HMAC, then HMAC + counter, then AES + HMAC. Keys live in
`config.py` for L0 lessons; later lessons move them to flash and add a
key-rotate command.

---

## 7. Ground-Station Software

```
groundstation/
├── operator/
│   ├── gs.py              # serial-link to Pico+CC1101 front-end
│   ├── ui.py              # textual TUI (rich/textual)
│   ├── decoder.py         # space-packet decoder (shared)
│   └── commands.py        # high-level command helpers
├── attacker/
│   ├── sdr_rx.py          # RTL-SDR → demodulated bytes (uses inspectrum / gr-satellites pattern)
│   ├── gnuradio/          # .grc flowgraphs for capture + decode
│   ├── replay.py          # capture+retransmit any frame
│   ├── inject.py          # build & TX an arbitrary command
│   └── fuzz.py            # APID & length fuzzing harness
└── shared/
    ├── space_packet.py    # *exactly* the satellite codec, in pure Python
    ├── crc.py
    └── crypto.py
```

The operator UI shows the live beacon, latest HK telemetry, a "send
command" panel, and a log of inbound frames with sequence-counter holes
highlighted (useful when the attacker starts injecting).

The attacker tooling is intentionally split between **GNU Radio** (for
the "see the spectrum, demodulate from baseband" lessons) and a
straight Python+CC1101 path (for the "drop a forged TC into the air"
lessons). Both decode through the same `shared/space_packet.py` so the
learner sees the same bits on both sides.

---

## 8. Curriculum

| #   | Title                                       | Goal                                                                                    | Tools                          |
|-----|---------------------------------------------|-----------------------------------------------------------------------------------------|--------------------------------|
| L00 | Build & first beacon                        | Solder-free build; bring up satellite + operator station; see the BEACON in the UI      | Both stations                  |
| L01 | Spectrum survey                             | Find the downlink with `rtl_power`; characterize the signal                              | RTL-SDR, gqrx                  |
| L02 | Demod in GNU Radio                          | Build a GFSK demodulator flowgraph; recover bits                                         | RTL-SDR, GNU Radio             |
| L03 | Frame sync & CRC                            | Find the sync word in a bitstream; verify CRC; extract space packets                     | Python                         |
| L04 | Telemetry decode                            | Map APIDs → meaning; live-plot HK telemetry from the attacker side                       | Python                         |
| L05 | Replay attack                               | Capture an `ARM_PAYLOAD` TC from the operator; retransmit and observe the satellite act  | Pico+CC1101 attacker           |
| L06 | Command injection                           | Forge a `FORCE_SAFE` TC from scratch; trigger safe mode without the operator             | Pico+CC1101 attacker           |
| L07 | Add HMAC (L1) → bypass via replay           | Show signed but counter-less HMAC still falls to replay                                   | All                            |
| L08 | Add counter-bound HMAC (L2)                 | Replay fails; learner explores nonce-window edge cases                                    | All                            |
| L09 | Side-channel: timing on HMAC verify         | Naive `==` in `security.py` is timing-leaky; recover MAC byte-by-byte                    | Python                         |
| L10 | Encryption + jam-and-replay                 | L3 hides content; show a "delete-and-replay" still affects availability                  | HackRF for jam tone            |
| L11 | Beacon spoofing & ground-station confusion  | Forge a BEACON from a "second satellite"; observe operator UI                            | Pico+CC1101 attacker           |
| L12 | Mission scenario (capstone)                 | Take over a "research satellite" given only RX + 1 captured authenticated TC             | Everything                     |

Each lesson lives in `lessons/LXX_name.md` with build steps, expected
captures, and instructor notes.

---

## 9. Safety, Legality & Ethics

1. **Bench operation only.** All Semaeopus traffic is intended to be
   contained to your workshop. 17 cm whip antennas at 10 mW will not
   reach orbit, but they *will* reach a neighbour with an SDR.
2. **Pick the right band for your jurisdiction.** EU/R1 users:
   433 MHz, 10 mW, 10 % duty cycle. US users: switch the build flag to
   915 MHz. Anywhere else: check before you key down.
3. **Never aim Semaeopus at a real satellite frequency.** UHF amateur sat
   downlinks are at 435–438 MHz; CC1101 *can* be programmed there but
   Semaeopus's default 433.920 MHz is deliberately *below* the amateur
   segment.
4. **No public PA mods.** A Cyclone-style PA brick will turn Semaeopus
   into an illegal local jammer. Don't.
5. **The attacks are practiced on your own satellite.** Treat
   `gs-attacker` as you would Metasploit: lab-only against systems you
   own or have explicit written permission to test.

---

## 10. Project Layout

```
semaeopus/
├── specification.md                ← this file
├── docs/
│   ├── architecture.md
│   ├── protocol.md
│   └── threat-model.md
├── hardware/
│   ├── satellite-bom.md
│   ├── ground-station-bom.md
│   ├── wiring-satellite.md         ← ASCII pinout + breadboard diagram
│   └── wiring-ground-station.md
├── firmware/satellite/             ← MicroPython (default)
├── groundstation/
│   ├── operator/
│   └── attacker/
├── protocol/
│   └── space_packet.py             ← shared reference codec
└── lessons/
    └── L00 … L12
```

---

## 11. Status

As of 2026-05-20:

### Done
| Area                                  | Notes                                                       |
|---------------------------------------|-------------------------------------------------------------|
| Design spec (this doc)                | Full RF, protocol, curriculum, threat model                 |
| Hardware BOMs + wiring                | Satellite, operator GS, attacker GS                         |
| **Hardware bring-up cookbook**        | OS install, 7-stage check sequence, troubleshooting tree    |
| **Bring-up scripts**                  | 7 standalone MicroPython smoke tests, each prints PASS/FAIL |
| Shared CCSDS-lite codec               | L0/L1/L2/L3 + leaky-compare hook for L09; 24 codec tests    |
| Satellite firmware (MicroPython)      | Scheduler, OBC modules, CC1101 driver, sensor drivers       |
| GS front-end firmware                 | USB-CDC modem for operator & attacker Picos                 |
| Operator GS app + **textual TUI**     | gs, tui, capture, replay, inject, jam, fuzz, spoof-beacon   |
| Attacker tooling — full security      | All tools accept `--security` + `--key` for L1/L2/L3        |
| Software-only simulator               | Virtual sat + UDP "ether"; reuses real OBC modules unchanged|
| GFSK IQ generator + reference demod   | `captures/baseline.iq` + `tools/demod_iq.py` recovers 11/11 |
| **Timing side-channel toolkit**       | `tools/timing_oracle.py` + `tools/timing_attack.py` (works) |
| **All 13 lessons L00–L12**            | Build through capstone; every sim-only lesson runnable today|
| **GNU Radio recipes**                 | RX + TX block-by-block guides for GR 3.10                   |
| pytest suite                          | 37 tests: codec, handlers, end-to-end sim, IQ, TUI smoke    |

### Next
- Bring up the actual hardware once parts arrive; tune CC1101 register
  set from bench measurements (current values are SmartRF-Studio
  defaults, expect minor tweaks).
- `tools/deploy.sh` wrapping the `mpremote` upload sequence.
- Validate the GNU Radio recipes end-to-end against a real RTL-SDR
  pointed at a flat-sat.

### Future
- Simulated **GPS receiver** (NMEA over UART driven by a trajectory
  propagator) → GPS-spoofing lesson with HackRF + `gps-sdr-sim`.
- **I²C bus** lesson where the OBC trusts an attached "experiment"
  peripheral that the attacker has compromised.
- **TLE manipulation** lesson where uploading a malformed orbit causes
  a real fault-handler to misbehave.
- Hardware-loop CI: a small bench rig that the test suite can hit
  over USB-serial.
