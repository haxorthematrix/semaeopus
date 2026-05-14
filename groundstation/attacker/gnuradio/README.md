# GNU Radio flowgraphs

Use these to **see** the link from the SDR side — the Pico front-end is
a convenient way to *send* frames, but it abstracts away the
modulation. To do lessons L01–L03 properly, learners should demodulate
from raw IQ with an RTL-SDR or HackRF.

## `gfsk_rx.grc` (build outline)

Block chain — assemble in `gnuradio-companion`:

```
  RTL-SDR Source        (samp_rate = 2 Msps, freq = 433.92 MHz, gain ~30)
       │
       ▼
  Frequency Xlating FIR Filter
       │  (centre on 0 Hz, cutoff = 25 kHz, decim = 50  →  40 ksps)
       ▼
  Quadrature Demod
       │  (gain = samp_rate / (2π * deviation_hz))
       ▼
  Symbol Sync (PFB MF)  or  Clock Recovery MM
       │  (sps = 40000/9600 ≈ 4.17)
       ▼
  Binary Slicer
       │
       ▼
  Correlate Access Code  (sync = 1101001110010001 ↔ 0xD391, threshold 1)
       │
       ▼
  Packet Deframer        (length field length=8, includes-crc=false)
       │
       ▼
  File Sink              (writes raw space packets to disk)
       │
       ▼
  Embedded Python Block  (calls `protocol.space_packet.decode` and prints)
```

## `gfsk_tx.grc` (HackRF only)

```
  File Source / Vector Source  (already-framed bytes from the host)
       │
       ▼
  Packet Encoder           (preamble 0xAA*4, sync 0xD391, no FEC)
       │
       ▼
  GFSK Mod                  (sps = 4, BT = 0.5, deviation = 4.8 kHz)
       │
       ▼
  Rational Resampler         (to HackRF native 2 Msps)
       │
       ▼
  Osmocom Sink               (HackRF, 433.92 MHz, gain ~30)
```

The TX flowgraph is the canonical reference for *exactly* what the
satellite is transmitting at the PHY layer. Compare the bytes it sends
on the wire to what the Pico+CC1101 emits — they should match.
