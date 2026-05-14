# L04 — Telemetry decode

## Goal
Map APIDs to subsystem meanings; live-plot the housekeeping & power
telemetry from the **attacker** side. No special access — just
listening.

## You'll need
- The L00 build.
- The attacker Pico (or RTL-SDR + L02 flowgraph) producing a stream of
  frames.

## Steps

### 1. Capture a few minutes
```bash
python -m groundstation.attacker.capture \
    --port /dev/ttyACM1 --out captures/baseline.jsonl
```

### 2. Open the capture
Each line is a JSON record with the decoded fields. Spot the cadence:
- APID 0x001 (BEACON) every 10 s
- APID 0x011 (ADCS_TLM) every 2 s
- APID 0x010 (HK_TLM) every 5 s
- APID 0x012 (EPS_TLM) every 5 s

### 3. Plot it
```python
import json, matplotlib.pyplot as plt, struct
records = [json.loads(l) for l in open("captures/baseline.jsonl")]

# HK telemetry: T (°C) over time
ts, temps = [], []
for r in records:
    if r["decoded"].get("apid") != 0x010:
        continue
    body = bytes.fromhex(r["frame"])
    # Strip [LEN][primary header 6][secondary 0]... user data starts at byte 7
    ud = body[7:7+14]
    if len(ud) < 14: continue
    _, _, t_q8, *_ = struct.unpack(">IHhHHBB", ud[:14])
    ts.append(r["ts"]); temps.append(t_q8 / 256.0)

plt.plot(ts, temps)
plt.xlabel("time"); plt.ylabel("°C"); plt.title("Onboard temp"); plt.show()
```

### 4. Sanity-check against `op>`
On the operator's side, request HK with `req 10`. The values should
match what you decoded from the captured frame within one sample.

## Questions
- The EPS frame contains an `is_daylight` flag — can you derive the
  satellite's orbital phase from the timestamp series alone?
- A nation-state attacker has a ground antenna with much better SNR
  than yours. What kinds of telemetry are most sensitive — i.e. what
  would you encrypt first?
