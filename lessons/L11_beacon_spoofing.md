# L11 — Beacon spoofing

## Goal
Forge a satellite BEACON from scratch and confuse the operator. The
BEACON APID (0x001) is unauthenticated at all four security levels
in Semaeopus — exactly the same design as most amateur and several
commercial CubeSats, where the beacon is meant to be a *public
service ad* (call sign, mode, basic state).

That's a design trade — and an exploitable one.

## Setup

Any security level works; let's use L0 for simplicity:

```bash
python -m sim.virtual_satellite       # the real one
python -m groundstation.operator.gs --sim
```

## Steps

### 1. Watch the real beacon stream

The operator should be printing one BEACON per 10 s:
```
[    1 BEACON] TM RSSI=-32  SEMAEOPUS-1 M0 B1 U10 SOC60
[   2 BEACON] TM RSSI=-32  SEMAEOPUS-1 M0 B1 U20 SOC60
```

### 2. Run the beacon spoofer

In another terminal:
```bash
python -m groundstation.attacker.spoof_beacon --sim \
    --callsign "SEMAEOPUS-1" --mode 1 --soc 5 --interval 8 \
    --tx-power 13
```

`--tx-power 13` makes the spoof "louder" at the operator's receiver
than the real satellite (which transmits at +10 dBm by default in
the simulator). RSSI is now higher for the spoof — looks more legit.

In the operator console you'll see beacons coming in roughly every
8 s with the *wrong* mode (M1 = SAFE) and low battery (SOC 5):

```
[ N BEACON] TM RSSI=-32  SEMAEOPUS-1 M0 B1 U30 SOC60   ← real
[ M BEACON] TM RSSI=-29  SEMAEOPUS-1 M1 B9999 U12345 SOC5   ← spoofed
```

A naive operator (or auto-monitoring script) might:
- Send a `req 12` to ask the EPS subsystem for details, wasting the
  pass on bogus telemetry.
- Trigger an alert based on "SOC 5%" and send a `safe` command — now
  the *real* satellite enters SAFE. (Mission objective denied.)
- Update internal tracking ("the satellite is in SAFE") and miss the
  real next pass's command window.

### 3. Try a fully bogus call sign

Some ground stations route based on call sign:
```bash
python -m groundstation.attacker.spoof_beacon --sim \
    --callsign "ROGUE-1" --interval 5
```

Now the operator sees two satellites. Their UI ID logic — if any —
splits attention.

## Defensive lab

The fix is straightforward: **sign the beacon**. Make the satellite
include an HMAC tag in the beacon's body. The defence is *not*
perfect (anyone who's solved L09 can forge), but it changes the
attack surface from "any attacker with a radio" to "attackers with
the key".

### Implementation sketch

In `firmware/satellite/comms/beacon.py`:

```python
def build(self):
    uptime_s = ticks_diff(ticks_ms(), self._t0) // 1000
    s = "%s M%d B%d U%d SOC%d" % (
        self.state.callsign, self.state.mode.current,
        self.state.boot_count, uptime_s, int(self.state.eps.soc),
    )
    body = s.encode()
    # Append an HMAC over (beacon body || a public counter)
    if self.state.security >= sp.SEC_L1_HMAC:
        tag = sp.hmac_sha256(self.state.session_key,
                             body + uptime_s.to_bytes(4, "big"))[:4]
        body = body + b"|" + tag.hex().encode()
    return (sp.APID_BEACON, body)
```

In the operator's `decoder.py`, verify the suffix and flag unsigned
beacons in red.

Apply that patch, re-run the spoofer, and watch the operator UI
correctly distinguish signed-real from unsigned-spoofed beacons.

## Discussion

- Why might a CubeSat team *want* unsigned beacons even in 2026?
  (Public outreach, amateur tracking — e.g. SatNOGS — relies on
  open beacons.)
- The defensive lab uses a 4-byte truncated HMAC. Is that enough for
  the threat model? (Birthday bound is 2¹⁶ — i.e., a few seconds at
  high TX rate. Pair the truncation with a rate limit at the
  receiver.)
- Real ground stations sometimes display *every* received beacon
  with no de-duplication. What if the spoofer's beacons all share
  the same sequence number as a real one? (UI behaviour depends —
  some clients silently drop dupes, some flag a sequence-counter
  inconsistency.)
- Some amateur satellites change their on-air ID after orbit
  insertion. If your operator UI looks for the *first* call sign
  ever seen and ignores changes, what's the spoofer's leverage?
