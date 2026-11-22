# GNU Radio flowgraphs

Use these to **see** the link from the SDR side. The Pico and CYD modems
are a convenient way to *send* frames, but they hide the modulation. To
do lessons L01 to L03 properly, learners should demodulate from raw IQ
with an RTL-SDR or HackRF.

> **Why recipes, not `.grc` files?** GNU Radio Companion's `.grc`
> format changes between minor releases (3.10.x to 3.11.x broke several
> block IDs), so a `.grc` that works for one user is often broken for
> another. The recipes below pin block names and parameter values that
> are stable across versions; build them in your local GRC.
>
> Both recipes are also run as scripts, block for block, by
> `tests/gnuradio/test_recipes.py` (it needs GNU Radio's Python
> bindings, e.g. `python3.12 -m pytest tests/gnuradio` on a distro
> install; it is skipped otherwise).

| File                                            | What it is                               |
|-------------------------------------------------|------------------------------------------|
| [`gfsk_rx_recipe.md`](gfsk_rx_recipe.md)        | RX: SDR or IQ file to decoded frames     |
| [`gfsk_tx_recipe.md`](gfsk_tx_recipe.md)        | TX: HackRF sends a frame a CC1101 accepts |
| [`semaeopus_deframer.py`](semaeopus_deframer.py) | Embedded Python Block used by the RX recipe |
| `tools/air_frame.py`                            | Builds the exact on-air bytes (and IQ) for TX |

Tested with GNU Radio 3.10.9 and its built-in Soapy blocks; gr-osmosdr
blocks work the same way.

## What the radios actually send

These come from the CC1101 registers in `firmware/satellite/lib/cc1101.py`,
which every Semaeopus board uses. A flowgraph has to match them.

| Parameter    | Value                                                    |
|--------------|----------------------------------------------------------|
| Frequency    | **915.000 MHz** (US default); 433.920 MHz for EU builds  |
| Modulation   | 2-GFSK, BT = 0.5, no whitening, no Manchester            |
| Bit rate     | 9600 bit/s (9595.9 exactly)                              |
| Deviation    | **about 20.6 kHz** (DEVIATN 0x35; not the 4.8 kHz the synthetic captures use) |
| Preamble     | `AA AA AA AA`                                            |
| Sync         | `D3 91 D3 91`: the 16-bit sync word is **sent twice** (30/32 sync mode) |
| Frame        | `LEN` + CCSDS space packet + CRC-16-CCITT (what the modems print as `RX <hex>`) |
| Radio CRC    | 2 more bytes: CRC-16, poly 0x8005, init 0xFFFF, over `LEN` through the CCSDS CRC. A receiving CC1101 drops frames without it. |
| Signal width | about 51 kHz (Carson: 2 x (20.6 + 4.8) kHz)               |

## 915 MHz notes

- **Tune off centre.** Both SDRs have a DC spike at the tuned frequency.
  Tune 200 kHz low (914.8 MHz) and let the Frequency Xlating filter shift
  the signal back.
- **Crystal offset doubles.** A CC1101 module's crystal is good to about
  10 to 20 ppm, which is 9 to 18 kHz at 915 MHz (half that at 433). The RX
  recipe has a `cfo` slider to trim it out; set it once per board.
- **Antennas.** A quarter wave at 915 MHz is 82 mm. On an RTL-SDR
  telescopic dipole, pull each element out to about 8 cm.
- **Keep the gain low.** On the bench the satellite is loud. RTL-SDR RF
  gain around 20, HackRF amp off.

## Block outlines

RX (details in [`gfsk_rx_recipe.md`](gfsk_rx_recipe.md)):

```
  Soapy RTLSDR / HackRF Source   (2 Msps, tuned to 914.8 MHz)
       │       or File Source (complex .cfile)
       ▼
  Frequency Xlating FIR Filter   (shift +200 kHz + cfo, low-pass 40 kHz, decim 20 -> 100 ksps)
       ▼
  Quadrature Demod               (gain = 100e3 / (2π · 20630))
       ▼
  Symbol Sync                    (Zero Crossing TED, sps = 100e3 / 9600, loop BW 0.02)
       ▼
  Binary Slicer
       ▼
  Correlate Access Code - Tag    (D391 D391 as 32 bits, threshold 3)
       ▼
  Embedded Python Block          (semaeopus_deframer.py: checks both CRCs, prints frames)
```

TX (details in [`gfsk_tx_recipe.md`](gfsk_tx_recipe.md)):

```
  python -m tools.air_frame ...  ->  /tmp/tc_air.bin  (preamble, sync x2, frame, radio CRC)
       ▼
  File Source (byte)
       ▼
  GFSK Mod                       (sps 210, sensitivity 2π · 20630 / 2.016e6, BT 0.5)
       ▼
  Multiply Const 0.7
       ▼
  Soapy HackRF Sink              (2.016 Msps, 915 MHz, amp off, VGA 20)
```

The TX flowgraph is the reference for exactly what a CC1101 transmits.
Record the satellite with the RX recipe and compare: the bytes should
match the ones `tools/air_frame.py` prints for the same frame.
