# L09 — Timing side-channel

## Goal
Recover an unknown 8-byte HMAC tag from a "black box" verifier using
nothing but the time it takes to say *yes* or *no*. The verifier
never leaks the tag — but by short-circuiting on the first mismatched
byte, it spends a microscopically different amount of time depending
on how many leading bytes you got right. That one fact reduces
2⁶⁴ guesses to 8 × 256 = 2048.

The technique is the same one that broke Xbox 360 secure boot
(2007), Java's `MessageDigest.isEqual` (CVE-2011-3105), Keyczar
(2009), early TLS implementations, and many CubeSat key-storage
modules. The defence — constant-time compare — is a single line of
code that's somehow still being skipped in 2025.

## What's set up for you

- A leaky-compare hook in `protocol/space_packet.py`. Setting the env
  var `SEMAEOPUS_LEAKY_HMAC=1` swaps the constant-time tag check for
  a short-circuit one with 4 ms of artificial work per matching byte.
- `tools/timing_oracle.py` — a localhost TCP server that loads the
  codec in leaky mode and replies `ACCEPT` / `REJECT` per submitted
  frame. Nothing else: no timing field, no error detail.
- `tools/timing_attack.py` — submits 8 × 256 candidate frames,
  measures the per-query time on the wire, and recovers the tag.

## Why "artificial 4 ms"?

Real-life timing leaks are nanoseconds. Recovering them from across
an RF link is so noisy in practice that it's almost always done
*against the radio module's own datasheet timing tables* or against
a side-channel like power-analysis. The 4 ms knob in Semaeopus makes
the technique reproducible on a stock laptop without an oscilloscope.
The *attack code is identical* in shape to what would run against a
nanosecond leak with better instrumentation.

## Run it

### 1. Start the oracle

```bash
python -m tools.timing_oracle
```

It prints — for tutorial visibility only — the correct frame and tag.
Real life: you wouldn't see those.

```
=== ORACLE STARTING (DEMO MODE) ===
Body the attacker wants to send : 00
APID                            : 0x0ff
Seq                             : 1
Nonce (publicly visible)        : 00000000000000aa
Tag (NOT revealed to attacker)  : c2be0097206db598
Frame (NOT revealed)            : 1918ffc001001000000000000000aac2be0097206db598005393

Listening on 127.0.0.1:9009 — one ACCEPT/REJECT per hex frame.
```

### 2. Run the attack

In a separate terminal:
```bash
python -m tools.timing_attack --samples 7
```

Takes ~3–4 minutes on a quiet laptop. Output:

```
--- byte position 0 ---
  best=0xc2  min=4107.7µs  gap to 2nd-best=+3979.5µs
  recovered so far: c2
--- byte position 1 ---
  best=0xbe  min=12214.3µs  gap to 2nd-best=+7985.2µs
  recovered so far: c2be
...
--- byte position 7 ---
  best=0x98  min=32176.0µs  gap to 2nd-best=+3876.9µs
  recovered so far: c2be0097206db598
=== ATTACK COMPLETE ===
recovered tag: c2be0097206db598
oracle accepts forged frame: True
```

The "min" column is the minimum query time across `--samples` runs
(7 by default). Using the **minimum** rather than the mean cuts past
scheduler interference: the busy-loop inside the oracle takes the
same time when it's not preempted, so the floor of the distribution
is the cleanest signal.

The "gap to 2nd-best" should be roughly the per-byte delay
(`LEAKY_BYTE_DELAY_US = 4000`). If it's much smaller, something is
wrong — see troubleshooting.

## How it works — step by step

The attack uses one fact: the oracle's verify function does
**delay then match-or-return** for each byte. Concretely:

```python
def _leaky_eq(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            return False     # ← short-circuit
        n += 1
        _busy_sleep_us(4000) # ← only delays AFTER a match
    return n == len(a)
```

Time as a function of where the first mismatch happens:

| First mismatch at byte | Time |
|------------------------|------|
| 0 (immediate)          | 0 ms |
| 1                      | 4 ms |
| 2                      | 8 ms |
| ...                    | ...  |
| 7                      | 28 ms|
| no mismatch (all 8)    | 32 ms|

So if you can measure time, you can locate the first mismatch.

For byte position k = 0, the attacker:

1. Submits 256 frames — one for each candidate byte 0 (b = 0x00 to
   0xFF) — with all other tag bytes zero.
2. For 255 of those, the very first byte mismatches and the oracle
   takes ~0 ms.
3. For 1 of those — the correct byte — the first byte matches; the
   oracle delays 4 ms, then encounters a mismatch at byte 1 (because
   we set byte 1 = 0, almost certainly ≠ the real byte 1). Total
   query time: ~4 ms.

The candidate whose median time is ~4 ms is the right byte 0. Lock
it in and proceed to byte 1 (testing candidates with the recovered
byte 0 fixed). Repeat 8 times.

## The defence — constant-time compare

`protocol/space_packet._ct_eq` is the safe version Semaeopus uses
when `SEMAEOPUS_LEAKY_HMAC` is unset:

```python
def _ct_eq(a, b):
    if len(a) != len(b):
        return False
    acc = 0
    for x, y in zip(a, b):
        acc |= x ^ y       # always do all bytes
    return acc == 0
```

No early exit. Every byte contributes to the accumulator. Whether
all 8 match or only the first 7 do, the time is identical. The
attack collapses.

Python's `hmac.compare_digest` (and OpenSSL's `CRYPTO_memcmp`) are
the canonical fast versions of this. Use them; never roll your own.

## Discussion

- The lesson uses an artificial 4 ms delay. With realistic
  nanosecond delays, what becomes hard? (Answer: SNR. You need many
  more samples and very low jitter — e.g., a dedicated test rig
  rather than across a network.)
- We attacked an offline localhost oracle. Why does this *not*
  translate to "attack the live satellite link"? (RF jitter, sat
  receiver duty-cycling, RTT variance.)
- The receiver could mitigate without going constant-time by adding
  a random delay after every verify. What does that buy you, and how
  many extra samples does the attacker need?
- The oracle responds to as many queries as you can send. What if
  the satellite *rate-limits* TC processing to, say, 1 per second?
  Estimate how long the attack would take.

## Defensive lab

Unset `SEMAEOPUS_LEAKY_HMAC` (don't set the env var) and re-run the
oracle + attack. Verify that the attack fails — the gap-to-2nd-best
collapses to noise and you get a random tag that the oracle
rejects.
