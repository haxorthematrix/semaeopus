# L05 — Replay attack

## Goal
Capture a legitimate command (an `ARM_PAYLOAD` TC from the operator)
and retransmit it from the attacker station, observing the satellite
react as if the operator had sent it.

This is the canonical "no auth + no anti-replay = anyone can fly your
spacecraft" lesson.

## You'll need
- Satellite (SECURITY_LEVEL = 0).
- Operator GS.
- Attacker Pico front-end **plus** the attacker laptop tools.

## Steps

### 1. Start the attacker capture
```bash
python -m groundstation.attacker.capture \
    --port /dev/ttyACM1 --out captures/replay-prep.jsonl
```

### 2. From the operator station, send a legitimate ARM
```
op> arm
```
You should see the satellite reply `EVENT  00 OK` and the OLED `flg`
field flip a bit (payload armed). The attacker's capture now contains
both your TC and the response.

### 3. Identify the TC
In `captures/replay-prep.jsonl`, find the record where
`decoded.apid_name == "ARM_PAYLOAD"`. Note its index.

### 4. Disarm
On the operator: `op> safe` (or wait — `arm` is cleared on mode change).

### 5. Replay
```bash
python -m groundstation.attacker.replay \
    --port /dev/ttyACM1 \
    --in captures/replay-prep.jsonl \
    --apid 0x084 --count 1
```

### Expected outcome
The satellite responds with `EVENT 00 OK` again — but the operator
never sent the command. The operator UI shows an unexplained PONG /
event with a sequence-counter consistent with the satellite's own
counter (the receiver doesn't care about TC seq numbers at L0).

### Try variants
- Replay `FORCE_SAFE` (APID 0x0FF). The satellite drops to safe mode
  with no operator action.
- Replay `KEY_ROTATE` with a captured TC — at L0 there's no key, so
  this is essentially a no-op. The lesson lands harder once we move to
  L1.

## Questions
- What logs (if any) does the satellite produce that the operator could
  use to detect this? (Hint: nothing yet — fix it!)
- How would a sequence-number window on the receiver close this hole?
  Why is that *not* the same as cryptographic anti-replay?
