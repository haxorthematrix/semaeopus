# GFSK RX recipe: GNU Radio Companion

A from-scratch flowgraph that receives the satellite at 915 MHz (or
reads a recorded IQ file) and prints every frame with its CRC verdicts.
It does what `tools/demod_iq.py` does, but with proper symbol-timing
recovery, so it works on the BT = 0.5 signal from a real CC1101.

Every block and value below is exercised by
`tests/gnuradio/test_recipes.py`.

## Inputs

One of:

- **Live:** an RTL-SDR or HackRF near the satellite.
- **Recording:** capture 10 s with an RTL-SDR, then convert to GNU
  Radio's complex float format:
  ```bash
  rtl_sdr -f 914800000 -s 2000000 -g 20 -n 20000000 captures/live.cu8
  python -m tools.cu8_to_cfile captures/live.cu8 captures/live.cfile
  ```
- **No hardware:** the synthetic capture (see
  [Synthetic capture settings](#synthetic-capture-settings)):
  ```bash
  python -m tools.cu8_to_cfile captures/baseline.iq captures/baseline.cfile
  ```

## Variables

| ID           | Value                         | Notes                                        |
|--------------|-------------------------------|----------------------------------------------|
| `rf_freq`    | `915e6`                       | `433.92e6` for an EU build                   |
| `lo_offset`  | `200e3`                       | SDR is tuned this far below `rf_freq`        |
| `samp_rate`  | `2e6`                         |                                              |
| `decim`      | `20`                          | channel rate 100 ksps                        |
| `chan_rate`  | `samp_rate / decim`           |                                              |
| `deviation`  | `20630`                       | the CC1101's actual deviation (DEVIATN 0x35) |
| `bit_rate`   | `9600`                        |                                              |

Add a **QT GUI Range** with ID `cfo`: default `0`, start `-30e3`, stop
`30e3`, step `250`. It trims out the satellite's crystal offset (step 3).

## Blocks

### Block 1: Source

**Soapy RTLSDR Source**

| Property          | Value                     |
|-------------------|---------------------------|
| Sample Rate       | `samp_rate`               |
| Center Freq (Hz)  | `rf_freq - lo_offset`     |
| AGC               | `False`                   |
| RF Gain           | `20` (bench; raise if weak) |

or **Soapy HackRF Source**: same rate and frequency, Amp `Off`, IF Gain
`16`, VGA Gain `16`.

or **File Source** for a recording: Type `complex`, Repeat `No`, File
`captures/live.cfile`. (gr-osmosdr's osmocom Source also works: same
rate and frequency.)

### Block 2: Frequency Xlating FIR Filter

Shifts the signal from `lo_offset` down to 0 Hz, low-pass filters it,
and drops the rate to 100 ksps.

| Property          | Value                                       |
|-------------------|---------------------------------------------|
| Type              | Complex->Complex (Complex Taps)             |
| Decimation        | `decim`                                     |
| Taps              | `firdes.low_pass(1, samp_rate, 40e3, 10e3)` |
| Center Frequency  | `lo_offset + cfo`                           |
| Sample Rate       | `samp_rate`                                 |

The 40 kHz cutoff passes the about 51 kHz wide signal (plus or minus
25 kHz) with room for 15 kHz of crystal offset. Narrow filters that suit
a 4.8 kHz deviation cut this signal in half.

### Block 3: Quadrature Demod

| Gain | `chan_rate / (2 * math.pi * deviation)`  (about 0.77) |

Output is the instantaneous frequency scaled so a full deviation is
plus or minus 1. The alternating preamble reaches about plus or minus 0.88.

**Set `cfo` once.** Add a **QT GUI Time Sink** (Type Float, Sample Rate
`chan_rate`, Number of Points `2000`, Trigger Mode `Normal`, Trigger
Level `0.5`) on this block's output and run. The preamble should swing
evenly around 0. If it is shifted (say +0.6 / -1.1, a mean of -0.25),
add `mean x deviation` to `cfo` (here about -5 kHz) and check again. A
board's offset stays put to within a kHz or two, so note it and make it
the slider's default.

> **Automatic alternative:** a **DC Blocker** (Length
> `int(chan_rate * 0.02)`, Long Form `True`) after this block removes the
> offset without tuning, but frames with long runs of 0x00 or 0xFF bytes
> (housekeeping telemetry, some commands) then lose bits. Trimming `cfo`
> is more reliable.

### Block 4: Symbol Sync

Recovers bit timing with fractional samples per symbol and tracks clock
drift between the satellite's crystal and the SDR's.

| Property                    | Value                                  |
|-----------------------------|----------------------------------------|
| I/O Type                    | Float                                  |
| Timing Error Detector       | Zero Crossing                          |
| Samples per Symbol          | `chan_rate / bit_rate`  (about 10.42)  |
| Expected TED Gain           | `1.0`                                  |
| Loop Bandwidth              | `0.02`                                 |
| Damping Factor              | `1.0`                                  |
| Maximum Deviation           | `1.5`                                  |
| Output Samples/Symbol       | `1`                                    |
| Interpolating Resampler     | MMSE, 8 tap FIR                        |
| TED Slicer Constellation    | `digital.constellation_bpsk().base()`  |

Output is one float per bit: positive for 1, negative for 0.

### Block 5: Binary Slicer

No parameters. Positive becomes 1, negative becomes 0.

### Block 6: Correlate Access Code - Tag Stream

The CC1101 sends the sync word twice, so match all 32 bits, as the
receiving CC1101 does.

| Property      | Value                                         |
|---------------|-----------------------------------------------|
| IO Type       | Byte                                          |
| Access Code   | `11010011100100011101001110010001` (D391 D391) |
| Threshold     | `3`  (bits allowed wrong)                      |
| Tag Name      | `sync`                                        |

### Block 7: Embedded Python Block (deframer)

Add an **Embedded Python Block**, open its code in the editor, replace
the template with the contents of
[`semaeopus_deframer.py`](semaeopus_deframer.py), and save. Set its
parameters:

| Tag Name   | `'sync'`                                    |
| Radio Crc  | `True` (live or recorded hardware)          |
| Jsonl      | `''`, or a path such as `'gr_frames.jsonl'` |

It reads the length byte, collects the frame, checks the CCSDS CRC and
the CC1101's own CRC, and prints:

```
frame apid=0x001 seq=12 len=34 ccsds-crc=ok radio-crc=ok : 220001c00c0019...
```

The `frames` message port carries each frame as a PDU if you want to
wire it to a **Message Debug** or **Socket PDU** block.

### Block 8: Verify against the wire

Run the attacker modem's capture at the same time:

```bash
python -m groundstation.attacker.capture --port /dev/ttyACM1 --out cap.jsonl
```

and set the deframer's `jsonl` to `'gr_frames.jsonl'`. Both files use
the `frame` key with the same hex (`LEN` through the CCSDS CRC), so
every frame the CC1101 caught should appear in both. A frame the modem
caught but GNU Radio did not is usually timing (step 4) or offset
(step 3).

## Synthetic capture settings

`captures/baseline.iq` from `tools/generate_iq.py` is not what the
hardware sends: it is already at 0 Hz, sent at 1 Msps with a 4.8 kHz
deviation, has the sync word once and no radio CRC, and uses 104
samples per bit (9615 bit/s). Change these and leave the rest:

| Setting                    | Synthetic value                  |
|----------------------------|----------------------------------|
| Source                     | File Source, `captures/baseline.cfile` |
| `samp_rate`                | `1e6`                            |
| `lo_offset`, `cfo`         | `0`                              |
| `decim`                    | `10`                             |
| `deviation`                | `4800`                           |
| `bit_rate`                 | `1e6 / 104`                      |
| Access Code / Threshold    | `1101001110010001` / `2`         |
| Deframer Radio Crc         | `False`                          |

Expect 10 or 11 of the 11 frames in `captures/baseline.jsonl`.

## Sanity check

If you skip Symbol Sync and slice the Quadrature Demod output with a
fixed integrate-and-dump (a Decimating FIR of `int(chan_rate/bit_rate)`
ones), you get the behaviour of `tools/demod_iq.py`: fine on the
synthetic capture, unreliable on a real CC1101, whose clock is never
exactly 9600 bit/s.
