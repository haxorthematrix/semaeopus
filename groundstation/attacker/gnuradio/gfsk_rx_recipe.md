# GFSK RX recipe — GNU Radio Companion

A from-scratch flowgraph that reproduces what `tools/demod_iq.py` does
in 80 lines of Python, but with proper symbol-timing recovery so it
will work on BT=0.5 signals from a real CC1101.

## Inputs

- `captures/baseline.cfile` — convert from `.cu8` first:
  ```bash
  python -m tools.cu8_to_cfile captures/baseline.iq captures/baseline.cfile
  ```
- OR an RTL-SDR live source.

## Open `gnuradio-companion` and build

### Block 1: File Source  (or RTL-SDR Source for live)

| Property      | Value                              |
|---------------|------------------------------------|
| Type          | `complex`                          |
| File          | `captures/baseline.cfile`          |
| Repeat        | `No`                               |
| Vec. Length   | `1`                                |
| ID            | `blocks_file_source_0`             |

For live RTL-SDR replace with **RTL-SDR Source**:
| Sample rate   | `samp_rate` (variable = 2e6)       |
| Centre freq   | 433920000                          |
| RF Gain       | 30                                 |

### Variable: `samp_rate`
Set to **1e6** for the synthetic baseline, or **2e6** for an RTL-SDR.

### Variable: `bit_rate`
Set to **9600**.

### Block 2: Frequency Xlating FIR Filter (live RX only)

Centres the signal at 0 Hz baseband. Skip for the synthetic capture
(it's already at baseband).

| Decimation    | `int(samp_rate / 200000)`          |
| Taps          | `firdes.low_pass(1, samp_rate, 25000, 5000)` |
| Centre Freq   | 0                                  |
| Sample Rate   | `samp_rate`                        |

### Block 3: Quadrature Demod

| Gain          | `samp_rate / (2 * pi * deviation)` (~33 for sr=1e6, dev=4800) |

This block takes complex baseband and outputs instantaneous
frequency as float — exactly what `tools/demod_iq.quadrature_demod`
computes.

### Block 4: Symbol Sync (PFB MF Resampler)

This is the crucial block that `demod_iq.py` lacks. It recovers
symbol timing even with fractional samples-per-symbol and corrects
for clock drift.

| Sample rate / symbol rate | `samp_rate / bit_rate`           |
| Loop bandwidth            | `0.045`                          |
| Damping factor            | `1.0`                            |
| TED gain                  | `1.0`                            |
| Filter taps               | `firdes.root_raised_cosine(1.0, samp_rate, bit_rate, 0.35, 11*int(samp_rate/bit_rate))` |
| Output samples / symbol   | `1`                              |
| TED                       | `Mueller and Müller`             |

The output is one float per symbol — positive for bit=1, negative
for bit=0.

### Block 5: Binary Slicer

No parameters. Maps positive floats → 1, negative → 0.

### Block 6: Correlate Access Code

Finds the sync word at the bit level.

| Access Code   | `1101001110010001`   (= 0xD391, MSB-first)         |
| Threshold     | `2`   (Hamming distance tolerance for sync match)  |
| Tag Name      | `corr_est`                                         |

### Block 7: Tagged Stream Align  +  Packet Deframer

Once the sync is found you need a length-prefix frame deframer. GNU
Radio doesn't ship a clean one for variable-length packets; the
common workaround is an **Embedded Python Block** that reads:

```python
import pmt
import numpy as np
from gnuradio import gr

class semaeopus_deframer(gr.sync_block):
    def __init__(self):
        gr.sync_block.__init__(self,
            name='semaeopus_deframer',
            in_sig=[np.uint8], out_sig=None)
        self.tag_key = pmt.intern('corr_est')

    def work(self, input_items, output_items):
        in0 = input_items[0]
        tags = self.get_tags_in_window(0, 0, len(in0))
        for tag in tags:
            offset = tag.offset - self.nitems_read(0)
            # Skip past the 16-bit sync
            start = offset + 16
            if start + 8 > len(in0): continue
            length = int(''.join(str(b) for b in in0[start:start+8]), 2)
            need = start + 8 + length * 8
            if need > len(in0): continue
            payload = bytearray()
            for k in range(0, length * 8, 8):
                b = 0
                for j in range(8):
                    b = (b << 1) | int(in0[start + 8 + k + j])
                payload.append(b)
            print(f"frame len={length}: {bytes(payload).hex()}")
        return len(in0)
```

### Block 8: Verify against the oracle

Run the flowgraph and confirm the recovered hex frames match
`captures/baseline.jsonl`. Any frame that's in the oracle but not in
your output is one your demod chain dropped — usually a
symbol-timing problem.

## Sanity check

If you skip Symbol Sync and just feed Binary Slicer's output
straight from Quadrature Demod (with an "integrate-and-dump" via
Decimating FIR), you get the same behaviour as `tools/demod_iq.py`:
fine for the synthetic BT=1.0 capture, broken at BT=0.5.
