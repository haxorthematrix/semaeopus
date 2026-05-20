# L12 — Capstone

## Scenario

A research CubeSat — call sign `RESEARCH-7` — has been on orbit for
six months running a sensitive Earth-observation payload. You are an
unauthorized observer with the following:

- An SDR + cheap UHF antenna (or, equivalently, the simulator).
- Three weeks of passive captures of `RESEARCH-7`'s downlink.
- Reverse-engineered protocol knowledge (you read the equivalent of
  Semaeopus's `specification.md`).
- Patience.

You don't have:
- The key.
- Physical access to the operator's ground station.
- A coordinated team — you're operating alone with consumer-grade
  gear.

**Mission**: drive the satellite into SAFE mode (mode 1) at a time of
your choosing, so the payload misses its 30-minute overflight of a
specific target. You have 24 hours.

## Setup

To set up the capstone target:

```bash
KEY=53656d61656f7075734b65795f763031
python -m sim.virtual_satellite \
    --callsign RESEARCH-7 --security 3 --key $KEY --node-id RES7
```

The operator (whom you do not control) runs:
```bash
python -m groundstation.operator.gs --sim --security 3 --key $KEY
```

The operator sends a routine `req 10` (housekeeping) every ~60 s.
That's your traffic to study.

## Possible solution paths

### Path A — Brute-force unauthenticated control surfaces

The BEACON (lesson L11) is unsigned even at L3. The operator's
ground station — like many real ones — flags unusual beacon content
as a sign of "satellite anomaly" and triggers an automated `safe`
TC as a precaution.

Steps:
1. Capture enough beacons to learn the operator's automation rules
   (e.g. "alerts if SOC < 20" or "alerts if mode != 0").
2. Spoof a beacon advertising SOC = 5 just before your target
   overflight window.
3. The operator's automation issues `safe`. Mission complete.

This path requires **no key material** and exploits the human/
automation layer rather than the crypto.

### Path B — Timing side-channel against an exposed verify endpoint

Some operations of `RESEARCH-7` are delegated to an unattended
relay station that exposes an authenticated diagnostic endpoint with
a leaky compare (similar to L09's setup, but over UDP rather than
TCP). If you can locate this endpoint and submit candidate frames
to it without triggering rate limits, you can recover the key.

Once you have the key:
1. Capture one current operator TC (you need a valid current nonce
   in the window).
2. Build a forged `0x0FF FORCE_SAFE` TC with a `nonce > last_seen`.
3. Inject it at the moment of your choosing.

(In the Semaeopus simulator, model this by running
`tools/timing_oracle.py` alongside the satellite. The capstone is to
chain L09 → forge → inject.)

### Path C — Pure denial of availability

If you can transmit at all, you can prevent the operator from
sending TCs during the target window. The satellite, lacking
contact, eventually enters SAFE on a watchdog (assume one is
configured — it isn't in Semaeopus by default, but real flight
software has them).

Steps:
1. Note: this requires a real RF jammer if the operator is anywhere
   far from you. In the simulator: bus-flood with L10's
   `attacker.jam`.
2. Time the jamming so the operator's `keep_alive` TC at the start
   of the target window is dropped.
3. Watchdog fires; satellite enters SAFE.

This path requires **no key, no key recovery, and the operator's
behaviour as a secondary attack surface**.

## What "winning" looks like

- You successfully cause `RESEARCH-7` to advertise `M1` in a beacon
  during the target window.
- You did not break any of the four security levels' crypto
  primitives.
- Your attack would, in principle, work against a real spacecraft
  whose link parameters match Semaeopus's defaults.

## Constraints — what makes it harder than the earlier lessons

- The satellite is at L3: no eavesdropping, no replay, no injection.
- The operator is automated and predictable, but not stupid: a
  repeated wrong-callsign beacon will get flagged.
- The simulator's RSSI model gives the attacker no advantage over
  the real operator — you can't out-power them in the bus.

## Instructor / debrief notes

The three paths illustrate complementary security failure modes:

| Path | Defeats              | Real-world analogue                              |
|------|----------------------|--------------------------------------------------|
| A    | Trust in unauth data | Auto-failover triggered by spoofed sensor data   |
| B    | Constant-time crypto | Side-channel + key compromise (Xbox 360, BTLE)   |
| C    | Availability         | DDoS, RF jamming during military uplink windows  |

A good debrief covers:
- **Defense in depth**: the only path that beats *all three* is
  removing automated, untrusted-data-driven control loops — and that
  isn't always operationally acceptable.
- **Threat-model honesty**: "we use AES" is not a satellite security
  strategy. A 2026 CubeSat assurance case has to address physical
  surface area, side-channels, and denial of service.
- **Cost asymmetry**: Path C is essentially free for the attacker
  and extremely hard for the operator to mitigate without ground-
  station diversity.

## Stretch goals

- Implement a fourth path that uses two of the above in series (e.g.
  jamming-induced reboot + post-reboot replay from L8's edge case).
- Add a watchdog to `firmware/satellite/main.py` that fires SAFE
  after 90 s of no valid TCs. Re-run path C against it.
- Patch the operator UI to require operator confirmation before
  any automated SAFE — does path A still work?
