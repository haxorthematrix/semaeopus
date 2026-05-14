# Software-only simulator

A virtual satellite and a UDP "ether" that lets you run most of the
Semaeopus curriculum on a single laptop — no Pico, no CC1101, no
RTL-SDR — by replaying the same protocol over multicast UDP instead
of 433 MHz RF.

```
                  UDP multicast group 239.10.6.7:53433
                                 │
   ┌─────────────────────────────┼─────────────────────────────┐
   │                             │                             │
   ▼                             ▼                             ▼
sim.virtual_satellite      gs-operator --sim         gs-attacker --sim
   (SAT0)                  (OPGS)                   (ATKR)
```

## Quick start

```bash
# Terminal 1 — start the virtual satellite
python -m sim.virtual_satellite

# Terminal 2 — attach the operator
python -m groundstation.operator.gs --sim
op> ping
op> req 12
op> safe

# Terminal 3 — passive capture (attacker)
python -m groundstation.attacker.capture --sim --out cap.jsonl

# Terminal 4 — replay or inject
python -m groundstation.attacker.replay --sim --in cap.jsonl --apid 0x084
python -m groundstation.attacker.inject --sim --apid 0xFF
```

All five tools accept `--sim`; when given, they use `sim/sim_link.py`
(UDP) instead of the serial Link.

## What changes vs. the real link

The simulator preserves **everything above the PHY**:
  - Same `protocol.space_packet` encoder/decoder.
  - Same satellite firmware modules (`obc.*`, `comms.handlers`,
    `comms.beacon`) — only sensor drivers and the radio are swapped.
  - Same security levels (0, 1, 2, 3) and the same lesson outcomes
    for L05–L09.

The simulator does **not** replicate:
  - Real GFSK demodulation (for that, use `tools/generate_iq.py` to
    produce an `.cu8` recording and follow lesson L02).
  - RF effects: multipath, ground-noise, antenna patterns, jamming.
  - Hardware timing — the Pico's interrupt latency and the CC1101's
    FIFO behaviour aren't modelled. For lessons L09 (timing
    side-channel) you really do want hardware.

## Lessons playable in the simulator alone

| Lesson | Title                          | Sim-only? |
|--------|--------------------------------|-----------|
| L00    | Build & first beacon           | partial — skip the build step, the rest works |
| L01–L03| Spectrum survey / GNU Radio    | use `tools/generate_iq.py` instead |
| L04    | Telemetry decode               | ✓                                 |
| L05    | Replay attack                  | ✓                                 |
| L06    | Command injection              | ✓                                 |
| L07    | HMAC bypass via replay (L1)    | ✓                                 |
| L08    | Counter-bound HMAC (L2)        | ✓                                 |
| L09    | Timing side-channel            | mostly — no real timing jitter    |
| L10    | Encryption + jam-and-replay    | partial — no jamming              |
| L11    | Beacon spoofing                | ✓                                 |
| L12    | Capstone                       | ✓                                 |

## Configuration

Two environment variables tune the bus:

| Var                | Default        | Meaning                              |
|--------------------|----------------|--------------------------------------|
| `SEMAEOPUS_GROUP`  | `239.10.6.7`   | Multicast group                      |
| `SEMAEOPUS_PORT`   | `53433`        | UDP port                             |

Change either to run multiple isolated sims on the same host.
