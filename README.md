# Semaeopus

**A realistic CubeSat hacking platform — flat-sat satellite, two
ground stations, and a 12-step curriculum, buildable from breadboards
and through-hole modules. Plus a software-only simulator so you can
start now without parts.**

Operates on ISM 433 MHz (EU) or 915 MHz (US), so no amateur licence
is required. The on-air protocol is a deliberately simplified
[CCSDS Space Packet] layered on a CC1101 GFSK PHY — the same shape
real CubeSats fly. The platform ships with documented gaps in the
security model so learners can attack it: no-auth replay, HMAC-only
replay, counter-bound HMAC, AES-CTR + HMAC.

[CCSDS Space Packet]: https://public.ccsds.org/Pubs/133x0b2.pdf

## What you can do today

Three independent paths:

### A. Software simulator (no hardware, ~5 min)
A virtual satellite and two virtual ground stations talk over UDP
multicast, sharing the **same firmware code** that runs on the real
Pico. Replay and inject work end-to-end.

```bash
git clone https://github.com/haxorthematrix/semaeopus
cd semaeopus
pip install pyserial pytest

python -m sim.virtual_satellite &        # the "satellite"
python -m groundstation.operator.gs --sim
op> ping
op> safe
op> mode 0
```

In another terminal — passive capture and a forged FORCE_SAFE:

```bash
python -m groundstation.attacker.capture --sim --out cap.jsonl
python -m groundstation.attacker.inject  --sim --apid 0xFF
```

### B. Synthetic RF (no hardware + GNU Radio)
A 2.7-second `.cu8` IQ recording of a 2-GFSK Semaeopus session, ready
to feed into `inspectrum`, `gqrx`, or a GNU Radio flowgraph. Build the
demodulator, recover the bits, compare against the oracle JSONL.

```bash
python -m tools.generate_iq          # writes captures/baseline.iq + .jsonl
# Open captures/baseline.iq in gqrx as "Raw I/Q", or follow lesson L02
```

### C. Real hardware (~ $35 + a laptop)
Build a satellite + operator GS from Pi Picos, CC1101 modules, sensor
breakouts, and Dupont wire. Optionally add an RTL-SDR ($30) and a
second Pico+CC1101 to play the attacker.

Detailed BOMs and wiring diagrams in [`hardware/`](hardware/). Lesson
[L00](lessons/L00_build_and_first_beacon.md) walks the first build.

## Running the tests

```bash
python -m pytest tests/ -q
```

37 tests cover the protocol codec (all four security levels, CRC
detection, replay rules), the TC dispatcher, an end-to-end virtual-sat
regression that proves an injected `FORCE_SAFE` flips the satellite
into SAFE mode, the GFSK modulator self-check, and the textual TUI
import surface.

For the hardware path, `bringup/` has seven standalone MicroPython
smoke tests that verify each subsystem wires up correctly before you
flash the full firmware. See
[`hardware/bringup-checks.md`](hardware/bringup-checks.md).

## Layout

```
specification.md      ← full design + status (start here)
docs/                 ← project website (serves at semaeopus.net)
hardware/             ← BOMs, wiring, breadboard diagrams
firmware/
  satellite/          ← MicroPython for the flat-sat
  gs_frontend/        ← MicroPython for both GS radios
groundstation/
  operator/           ← legitimate operator app
  attacker/           ← capture / replay / inject / fuzz
  shared/             ← link & decoder common to both
sim/                  ← software-only simulator (UDP "ether")
protocol/             ← CCSDS-lite codec (shared everywhere)
tools/                ← IQ generator + utilities
captures/             ← reference IQ + JSONL for hardware-free L01–L04
tests/                ← pytest suite (35 tests)
lessons/              ← curriculum, L00–L12
```

## Curriculum at a glance

| #   | Title                            | Sim only? |
|-----|----------------------------------|-----------|
| L00 | Build & first beacon             | partial   |
| L01 | Spectrum survey                  | use IQ    |
| L02 | Demod in GNU Radio               | use IQ    |
| L03 | Frame sync & CRC                 | use IQ    |
| L04 | Telemetry decode                 | ✓         |
| L05 | Replay attack                    | ✓         |
| L06 | Command injection                | ✓         |
| L07 | HMAC bypass via replay (L1)      | ✓         |
| L08 | Counter-bound HMAC (L2)          | ✓         |
| L09 | Timing side-channel              | partial   |
| L10 | Encryption + jam & replay        | partial   |
| L11 | Beacon spoofing                  | ✓         |
| L12 | Capstone                         | ✓         |

## Legality & ethics

Read `specification.md` §9 before transmitting. Defaults: 433.920 MHz
at 0 dBm — well inside ISM in EU/R1. US users: rebuild with
`RF_FREQ_HZ = 915_000_000`. Don't aim at amateur satellite frequencies.
Don't attach an external PA. Practice attacks only on systems you own
or have written permission to test.

## License

MIT for code, CC-BY-SA 4.0 for lessons and hardware documentation.
