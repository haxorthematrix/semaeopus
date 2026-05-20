# L07 — HMAC bypass via replay (security level 1)

## Goal
Show that authentication without freshness is broken: an HMAC tag
over body-only is unchanged when you retransmit the same frame, so
replay succeeds even though injection now fails.

This is the canonical "we added crypto but the attack still works"
lesson — the failure mode that bit the 2008 ISS lab demo, IEEE
802.11 WEP, and countless IoT devices.

## You'll need
- The satellite (real or `sim/virtual_satellite.py`).
- Operator GS.
- Attacker capture + inject + replay tools.

## Setup — bump the satellite to L1

If you're using the simulator:
```bash
KEY=53656d61656f7075734b65795f763031          # 16 bytes hex
python -m sim.virtual_satellite --security 1 --key $KEY
```

If you're on hardware: edit `firmware/satellite/config.py`,
set `SECURITY_LEVEL = 1`, re-upload `config.py`, reset the Pico.

Start the operator the same way:
```bash
python -m groundstation.operator.gs --sim --security 1 --key $KEY
```

## Steps

### 1. Confirm injection without the key now fails

```bash
python -m groundstation.attacker.inject --sim --apid 0xFF
```

In the satellite log you'll see:
```
[sat] rx auth FAIL apid=0x0ff
```

The bare frame is structurally valid but its HMAC tag is missing
(security level 0 frames lack the secondary header). The L1 receiver
demands a tag.

### 2. Have the operator send a legitimate TC the attacker can copy

Start an attacker capture in another terminal:
```bash
python -m groundstation.attacker.capture --sim --out cap_L7.jsonl
```

In the operator session:
```
op> arm
op> safe
```

Both TCs are signed with HMAC-SHA256 (truncated to 8 bytes) over
`body` only. The attacker capture file now contains both frames.

### 3. Replay the ARM command

```bash
python -m groundstation.attacker.replay \
    --sim --in cap_L7.jsonl --apid 0x084
```

The satellite log:
```
[sat] TC apid=0x084 seq=N rssi=-45
```

— **accepted**. The HMAC matched because the body (which is what was
signed) is byte-identical to the original. Replay achieves the same
effect as injection-with-key.

### 4. Replay FORCE_SAFE too

```bash
python -m groundstation.attacker.replay \
    --sim --in cap_L7.jsonl --apid 0xFF
```

Now the operator's mode goes back to SAFE without their consent.

## What went wrong

The L1 HMAC input is:
```
mac_input  = body                          # ← no freshness
tag        = HMAC-SHA256(key, mac_input)[:8]
```

This proves "someone with the key built this body" — which is true
on both the original transmission and the replay. The receiver has
no way to tell two identical frames apart.

Contrast L2 (next lesson):
```
mac_input  = nonce || body                 # ← nonce binds freshness
tag        = HMAC-SHA256(key, mac_input)[:8]
# AND the receiver enforces: incoming nonce must be > last seen
```

## Defensive lab

Patch `protocol/space_packet.py` to make L1 include the nonce in the
MAC input (effectively turning L1 into L2 minus the counter
enforcement). Replay this lesson — what changes? What doesn't?

You should find that signing the nonce alone (without counter
enforcement at the receiver) blocks the *bit-for-bit* replay but
leaves a small window — the attacker can still replay any frame
whose nonce the receiver hasn't yet rejected. The lesson: freshness
binding requires **both** a unique nonce in the MAC input **and**
a strictly monotonic acceptance window. That's L2.

## Questions
- Capture two of the operator's `ping` TCs and compare frames byte
  by byte. Are the HMAC tags identical? Why or why not?
- If you swap the body of frame A with the tag of frame B, will the
  satellite accept it? Try it. Explain.
- A real CubeSat ground station sends the same command 5 times during
  a 4-minute pass to cope with fading. At L1, what attack surface
  does this expand?
