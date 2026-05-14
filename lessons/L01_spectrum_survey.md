# L01 — Spectrum survey

## Goal
Find the satellite's downlink from scratch using only an RTL-SDR, the
way you would for an unknown CubeSat whose downlink parameters aren't
published.

## You'll need
- The satellite running L00 firmware (security level 0).
- RTL-SDR v3 + the antenna it ships with.
- `rtl_power`, `rtl_test`, `gqrx` or `SDR++`.

## Steps

### 1. Sanity check
```bash
rtl_test -t
```
You should see your dongle identified and tuner info. Then plug the
telescopic dipole in. For 433 MHz, set each arm to ~17 cm.

### 2. Sweep
```bash
rtl_power -f 430M:435M:5k -i 5 -g 30 -e 60 sweep.csv
```
Plot with `heatmap.py` (from `keenerd/rtl-sdr-misc`) or your tool of
choice. You should see a stripe of activity right around **433.92 MHz**
that appears once every 10 s (the beacon).

### 3. Zoom in with gqrx
- Centre 433.92 MHz, sample 2 Msps, mode "Raw I/Q".
- The waveform shows a short burst with ~9.6 kbps GFSK-shaped energy
  and ~4.8 kHz deviation. Notice the **two clear tones** at ±~4.8 kHz
  off centre — that's the FSK mark/space.

### 4. Estimate parameters
- **Frequency**: read off gqrx — should land within ~5 kHz of 433.920 MHz.
- **Bitrate**: count cycles in a single burst → ≈ 9600 bps.
- **Modulation**: two discrete tones → 2-FSK family (GFSK if shaped).
- **Length**: a beacon burst ≈ 32 ms long (preamble + sync + ~40 B
  frame at 9600 bps).

### Questions for the learner
- How would you tell GFSK from MSK in this view?
- The beacon is the most common transmission, but you'll occasionally
  see longer bursts every 2 s — what are those?
- What does the FSK deviation tell you about the maximum useful
  bitrate?
