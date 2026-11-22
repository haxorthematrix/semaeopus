# L02 — Demod in GNU Radio

## Goal
Demodulate the satellite's GFSK downlink from raw IQ all the way to a
stream of bits, using GNU Radio Companion.

## You'll need
- **Option A — with hardware:** the satellite still transmitting (915 MHz by default), an RTL-SDR or HackRF, and `gnuradio` ≥ 3.10.
- **Option B — software only:** the pre-generated `captures/baseline.iq` (regenerate with `python -m tools.generate_iq`) and `gnuradio` ≥ 3.10. Skip the live capture step below, convert `baseline.iq` to a `.cfile` (step 1b) and feed it to your flowgraph's File Source.

## Steps

### 1. Capture a sample (Option A — hardware)
```bash
rtl_sdr -f 914800000 -s 2000000 -g 20 -n 10000000 capture.cu8
python -m tools.cu8_to_cfile capture.cu8 capture.cfile
```
That's 5 seconds of 2 Msps IQ, about 20 MB as `.cu8`. Plenty of beacons.
The SDR is tuned 200 kHz below the satellite's 915 MHz so its DC spike
stays off the signal; the flowgraph shifts it back. (EU build: use
`-f 433720000`.)

### 1b. Use the synthetic capture (Option B — software only)
```bash
python -m tools.generate_iq                  # produces captures/baseline.iq
python -m tools.cu8_to_cfile captures/baseline.iq captures/baseline.cfile
```
The synthetic capture is 1 Msps, so set the sample rate in your
flowgraph accordingly. The generator rounds to a whole 104 samples per
bit, so use `bit_rate = 1e6 / 104` (about 9615) for it.

> **BT note.** The synthetic capture uses `--bt 1.0` (wide Gaussian,
> minimal ISI) by default so a beginner's integrate-and-dump
> demodulator can recover it. Real CC1101 typically transmits at
> BT=0.5 (sharper spectral occupancy, more ISI). To practice
> matched-filter receiver design, regenerate with `python -m
> tools.generate_iq --bt 0.5` and you'll need GNU Radio's
> Symbol Sync (PFB MF) block to recover the bits.

### 1c. Reference demodulator (sanity check before GNU Radio)
```bash
python -m tools.demod_iq                # reads captures/baseline.iq
# expect: "recovered 11 CRC-OK frames" and "matched 11"
```
The pure-Python reference demod uses an energy detector + per-burst
integrate-and-dump + Hamming-2-tolerant sync correlator. It works
for BT=1.0 (the default) only. Use it as the ground truth your GNU
Radio chain must reach.

### 2. Build the demod flowgraph
Follow `groundstation/attacker/gnuradio/gfsk_rx_recipe.md` block by
block. Save as `gfsk_rx.grc`.

Key parameters for the hardware:
- Frequency Xlating FIR Filter: centre `200e3 + cfo`, decimate by 20 to
  100 ksps, low-pass 40 kHz. The real CC1101 deviation is about 20.6 kHz,
  so the signal is about 51 kHz wide.
- Quadrature Demod gain = `chan_rate / (2 * π * deviation)`: for 100 ksps
  and 20.6 kHz, that's about 0.77.
- Trim `cfo` until the preamble swings evenly around zero. At 915 MHz a
  CC1101 module's crystal can put it 10 kHz or more off frequency.
- Symbol Sync (Zero Crossing TED), `sps = 100000 / 9600`.
- Correlate Access Code: `11010011100100011101001110010001` (0xD391 sent
  twice; the CC1101 repeats its sync word), threshold 3.

The synthetic capture differs (1 Msps, 4.8 kHz deviation, one sync word,
no radio CRC); the recipe's last section lists its settings.

### 3. Watch bits flow
Drop a "File Sink" after the Binary Slicer and after the Packet
Deframer. With a hex dump, you should see frames that begin with
`AA AA AA AA D3 91 D3 91` (preamble + sync twice) and end with four CRC
bytes: the CCSDS CRC-16 inside the frame, then the CC1101's own CRC-16.

### 4. Compare against the wire
```bash
python -m groundstation.attacker.capture --port /dev/ttyACM1 --out cap.jsonl
```
The frames in `cap.jsonl` (Pico-decoded) and the bytes coming out of
your GNU Radio Packet Deframer should match exactly. **This is the
proof that you've fully recovered the link.**
