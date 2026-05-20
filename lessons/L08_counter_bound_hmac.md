# L08 — Counter-bound HMAC (security level 2)

## Goal
Move to a freshness-binding MAC. Show that bit-for-bit replay no
longer works. Then probe the *edges* — nonce wraparound, post-reboot
counter behaviour, packet reordering, replay windows — to find where
real spacecraft implementations still leak.

## What L2 changes

- MAC input is now `nonce || body`. A different nonce → a different
  tag, even for the same body.
- The receiver remembers `last_seen_nonce` and rejects any incoming
  frame whose nonce is not strictly greater.

```python
# Satellite, simplified
if security_level >= SEC_L2_HMAC_CTR and incoming.nonce <= last_seen_nonce:
    reject("replay")
```

## You'll need
- L00 build (sim or hardware) at SECURITY_LEVEL = 2.

## Setup
```bash
KEY=53656d61656f7075734b65795f763031
python -m sim.virtual_satellite --security 2 --key $KEY
python -m groundstation.operator.gs --sim --security 2 --key $KEY
```

## Steps

### 1. Capture an authenticated TC from the operator
```bash
python -m groundstation.attacker.capture --sim --out cap_L8.jsonl
```
In the operator:
```
op> arm
```

### 2. Replay it — now rejected
```bash
python -m groundstation.attacker.replay --sim --in cap_L8.jsonl --apid 0x084
```
Satellite log:
```
[sat] rx replay rejected apid=0x084
```

L2 working as advertised: the captured frame's nonce is no longer
strictly greater than `last_seen_nonce`, so it's discarded.

### 3. Try a forged "future" nonce without the key
```bash
python -m groundstation.attacker.inject --sim --apid 0xFF
```
```
[sat] rx auth FAIL apid=0x0ff
```
Authentication blocks the forgery — no key, no valid tag.

### 4. WITH the key, inject from a fresh-looking nonce

(L09 will show how an attacker might obtain the key without
straight-up theft. For now we cheat.)

```bash
python -m groundstation.attacker.inject \
    --sim --apid 0xFF --security 2 --key $KEY \
    --nonce ffffffffffffff00
```
Satellite log:
```
[sat] TC apid=0x0ff ...
```

Accepted — because the nonce is greater than anything the operator
has used. **L2 only protects against passive replay; it offers nothing
once the key is compromised.** That's the L9/L10 lesson.

## Edge cases — where L2 still bleeds in the field

These don't have automatic scripts; they're discussion + exercise.

### 4a. Post-reboot counter reset
In `firmware/satellite/main.py`, the receiver counter
(`state.rx_last_nonce`) is initialised to `\x00 * 8` on boot. A real
CubeSat watchdog might trigger a reboot mid-pass. After reboot, ANY
captured frame the attacker has — even months-old — is now "fresh
again."

**Try it:** capture frames with an active operator. Restart the
virtual satellite. Replay the captured frames. Accepted.

**Defence:** persist `last_seen_nonce` to flash. Move the boot counter
into the nonce's high bits so a new boot session can't collide with
an old one (Semaeopus does this in `next_nonce()` on the TX side but
not on the RX gate).

### 4b. Nonce window vs strict-greater
Some real implementations use a sliding *window* — accept any nonce
within +N of the last seen — to tolerate reordering. That widens the
attack surface to N captured frames at any moment.

**Try it:** patch `protocol/space_packet.py` to accept nonces within
±100 of `last_seen_nonce`. Re-run the simple replay from Step 2.
Discuss the cost/benefit.

### 4c. Counter wraparound
Our nonce is 64-bit (32-bit boot count || 32-bit tx counter). At 100
TCs/second that's 1.3 years before wrap. A small CubeSat fielding a
24-hour pass per day for years CAN hit this. What does the receiver
do when `next_nonce < last_seen_nonce` legitimately?

## Questions
- The MAC input is `nonce || body`. What if it were `body || nonce`?
  Are both equally safe under HMAC-SHA256? (Hint: yes for SHA256
  HMAC; this changes if you use a length-extension-prone primitive.)
- The receiver tracks ONE last-seen nonce. If you parallelise TCs on
  two separate links (e.g. one through Hawaii ground station, one
  through Svalbard), how do you preserve strict-monotonic without
  losing concurrency?
- Why is "throw a random 64-bit nonce per frame" generally a bad
  alternative to a counter? (What does the receiver do with random
  nonces?)
