# L10 — Encryption + jam-and-replay (security level 3)

## Goal
Move to AES-128-CTR + HMAC. Show that eavesdropping is now blocked
— captured frames look like noise. But also show that **encryption is
not availability**: an attacker who can transmit at all can still
deny the operator's commands by congesting the receiver. And a
captured-but-undecodable frame is still useful for *strategic*
replay timing.

## What L3 changes

```python
ciphertext = AES-128-CTR(key, nonce, plaintext)
mac_input  = nonce || ciphertext
tag        = HMAC-SHA256(key, mac_input)[:8]
```

The receiver decrypts using `key + nonce` after the HMAC verifies
and the nonce passes the L2 strict-monotonic check. The on-wire
user-data field is now random-looking — `xxd` an attacker capture and
you won't see "SEMAEOPUS-1 M0 …".

## You'll need
- `pip install pycryptodome` on the host (CPython needs it; MicroPython
  uses the built-in `ucryptolib`).
- The L00 build at `SECURITY_LEVEL = 3`.

## Setup
```bash
pip install pycryptodome
KEY=53656d61656f7075734b65795f763031
python -m sim.virtual_satellite --security 3 --key $KEY
python -m groundstation.operator.gs --sim --security 3 --key $KEY
```

## Steps

### 1. Confirm eavesdropping is dead

```bash
python -m groundstation.attacker.capture --sim --out cap_L10.jsonl
```

Open `cap_L10.jsonl` and find a `BEACON` record. Its `frame` field is
still readable in hex (the secondary header and ciphertext aren't
hidden from the demodulator), but the `pretty` decode is gibberish
because the attacker has no key.

Compare with what the operator sees at the same instant: their UI
shows the cleartext `SEMAEOPUS-1 M0 B1 …` because they decrypted.

> An attacker who has solved L09's timing side-channel against an L1
> oracle and recovered a key would now decrypt. The L3 lesson assumes
> the key remains secret. L12 chains them.

### 2. Inject still fails without the key

```bash
python -m groundstation.attacker.inject --sim --apid 0xFF
```
```
[sat] rx auth FAIL apid=0x0ff
```

### 3. Replay still fails

```bash
python -m groundstation.attacker.replay --sim --in cap_L10.jsonl --apid 0x083
```

The captured TC's nonce is now older than `last_seen_nonce`:
```
[sat] rx replay rejected apid=0x083
```

### 4. **Strategic replay** — denial of availability

What if the attacker times their interference?

#### 4a. Continuous "noise" jamming

```bash
python -m groundstation.attacker.jam --sim --mode noise --rate 100 --duration 30
```

In a *third* terminal, watch the operator UI. While the jammer is
running, the operator's RX queue fills with CRC-failed junk; every
`req 10` or `safe` they issue still goes out, and the satellite still
processes it — but the operator might miss the EVENT 00 OK response
because their own decoder is busy.

Note this is **not** the same as RF jamming. We're flooding the
operator's *receive* path. To overcome the satellite's analog
front-end you need actual RF power (HackRF + CW tone). The
simulator can't model that.

#### 4b. Targeted denial: flood TCs

```bash
python -m groundstation.attacker.jam --sim --mode flood-tc \
    --rate 50 --duration 30
```

Every junk TC the attacker sends triggers the satellite's HMAC
verify pipeline. With 50 TCs/second of garbage, the satellite spends
substantial CPU per second doing nothing but auth-rejecting. On a
real Pico this delays the legitimate `req_tlm` handler's RX poll —
and on flight hardware with a duty-cycled receiver, you can push the
satellite into perpetual "checking the gate" mode and starve other
subsystems.

#### 4c. Replay-spam an authenticated frame

Even though L2 rejects replays, the receiver still pays auth+nonce
check cost on each one. Grab any frame from your capture:
```bash
TC=$(jq -r 'select(.decoded.type == "TC") | .frame' cap_L10.jsonl | head -1)
python -m groundstation.attacker.jam --sim --mode replay-spam \
    --replay-frame $TC --rate 200 --duration 30
```

200 fps of replay-rejected frames is more efficient for the attacker
than random junk because every frame at least passes CRC.

## With a HackRF — what the simulator can't show

The simulator models the *digital* denial: queueing, auth-rejection
cost. It cannot model RF saturation.

A HackRF transmitting a CW tone at +5 dBm on 433.92 MHz will desense
the satellite's CC1101 front end. The legitimate operator's
transmissions never make it through demodulation, because the
analog-to-digital path is saturated.

```bash
# HackRF: 5 dBm continuous tone, 433.92 MHz, run for 30 s
hackrf_transfer -t /dev/zero -f 433920000 -s 2000000 -x 5
```

That's the gap-filler L10 lesson on real hardware. Quick warning
before you do it: **a CW tone on 433.92 MHz at any meaningful power
is an ISM-band violation in most jurisdictions** if it leaves the
shielded workspace. Use a dummy load (50 Ω terminator) on the HackRF
output for indoor labs, or do this inside a Faraday cage.

## Discussion

- L1 → L2 → L3 are layered. L2 alone is enough for replay resistance;
  L3 adds confidentiality. What kinds of attacks does L3 prevent that
  L2 alone doesn't?
- The encryption is AES-128-CTR. Why CTR rather than CBC? (Hint:
  CTR with a unique nonce is a stream cipher — bit-flips in transit
  produce predictable bit-flips in the plaintext. CBC would garble.
  Both are blocked by the HMAC anyway.)
- L3 frames have a 16-byte security overhead (8 nonce + 8 tag). For a
  CubeSat with a tight downlink budget, that's expensive. Could you
  truncate the tag further? What's the trade?
- The jam-and-replay denial only matters as long as the attacker is
  *near* the operator (or the satellite). What ground-station design
  practices reduce blast radius (directional antennas, geographic
  diversity)?
