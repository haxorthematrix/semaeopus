# L02 — Demod in GNU Radio

## Goal
Demodulate the satellite's GFSK downlink from raw IQ all the way to a
stream of bits, using GNU Radio Companion.

## You'll need
- **Option A — with hardware:** the satellite still transmitting, an RTL-SDR, and `gnuradio` ≥ 3.10.
- **Option B — software only:** the pre-generated `captures/baseline.iq` (regenerate with `python -m tools.generate_iq`) and `gnuradio` ≥ 3.10. Skip the live capture step below and feed `baseline.iq` directly into your flowgraph's File Source.

## Steps

### 1. Capture a sample (Option A — hardware)
```bash
rtl_sdr -f 433920000 -s 2000000 -g 30 -n 10000000 capture.iq
```
That's 5 seconds of 2 Msps IQ ≈ 40 MB. Plenty of beacons.

### 1b. Use the synthetic capture (Option B — software only)
```bash
python -m tools.generate_iq                  # produces captures/baseline.iq
```
The synthetic capture is 1 Msps, so set the sample rate in your
flowgraph accordingly (1 Msps → sps = 1_000_000 / 9600 ≈ 104.17).

### 2. Build the demod flowgraph
See `groundstation/attacker/gnuradio/README.md` for the block list.
Save as `gfsk_rx.grc`.

Key parameters:
- Quadrature Demod gain = `samp_rate / (2 * π * deviation)` — for 40 ksps
  and 4.8 kHz, that's ~1.32.
- Symbol Sync block, `sps = 40000 / 9600`.
- Correlate Access Code: `1101001110010001` (= 0xD391), threshold 1.

### 3. Watch bits flow
Drop a "File Sink" after the Binary Slicer and after the Packet
Deframer. With a hex dump, you should see frames that begin with
`AA AA AA AA D3 91 …` (preamble + sync) and end with two CRC bytes.

### 4. Compare against the wire
```bash
python -m groundstation.attacker.capture --port /dev/ttyACM1 --out cap.jsonl
```
The frames in `cap.jsonl` (Pico-decoded) and the bytes coming out of
your GNU Radio Packet Deframer should match exactly. **This is the
proof that you've fully recovered the link.**
