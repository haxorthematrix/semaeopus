# L07 – L12 — outline

Detailed lesson files for these will land in subsequent iterations. The
outline below is the curriculum spine.

## L07 — HMAC bypass via replay (security level 1)
- `config.py`: `SECURITY_LEVEL = 1`; same `SHARED_KEY`.
- Show that an HMAC over body-only still permits a perfect replay:
  the tag is unchanged when you retransmit the exact same body.
- Conclusion: integrity ≠ freshness.

## L08 — Counter-bound HMAC (security level 2)
- `SECURITY_LEVEL = 2`. HMAC = `HMAC_k(nonce || body)`; receiver
  enforces strictly increasing nonce.
- Replay fails. Inject still fails (no key).
- Edge-case lab: nonce wraparound, post-boot nonce reset, packet
  reordering across short outages.

## L09 — Timing side-channel
- `space_packet._ct_eq` was written constant-time; switch it to a naive
  byte-by-byte comparison and show the byte-by-byte MAC recovery
  attack against an offline oracle.
- Compare against your own Pico-based oracle — the RP2040 has a 125 MHz
  clock and >µs response jitter, so this is more an "explain & simulate"
  lesson than a real-time recovery attack.

## L10 — Encryption + jam-and-replay (security level 3)
- `SECURITY_LEVEL = 3`. User data is AES-128-CTR encrypted under the
  nonce.
- Eavesdropping yields gibberish. **But** an attacker with a HackRF can
  still:
  - drop legitimate TCs (jam during operator transmissions),
  - replay an authenticated TC at a moment of operator's choosing
    (still blocked by counter, but you can sabotage *timing*).
- The lesson tunes a CW tone at +5 dBm on 433.92 MHz from the HackRF
  to demonstrate the denial-of-service tradeoff. **HackRF only —
  reminder of legal limits.**

## L11 — Beacon spoofing
- The BEACON has no auth even at L3 (it's a public service ad). Show
  how an attacker can forge `SEMAEOPUS-1 M0 B999 U0 SOC100` and
  confuse the operator's UI (and any tracking station that ID's by
  callsign).
- Defensive lab: add an HMAC suffix to the beacon string (visible but
  optional), and update the operator UI to highlight unsigned beacons.

## L12 — Capstone
- Setup: the satellite is freshly powered, at L3. The attacker has:
  - 10 minutes of pre-captured frames from a previous operator session.
  - One known TC from that session that the satellite accepted at the
    time but won't accept now (due to counter advance).
  - No key.
- Goal: drive the satellite into SAFE mode without operator coop.
- Possible solution paths: timing side-channel + nonce window collision
  (only works under specific replay-window settings); social-engineering
  the operator into KEY_ROTATE; or just demonstrating that DoS via
  jamming is sufficient for many real-world objectives.
- Instructor notes will walk through the intended solution and rate
  alternate approaches.
