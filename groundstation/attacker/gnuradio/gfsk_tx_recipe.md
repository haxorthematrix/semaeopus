# GFSK TX recipe: GNU Radio Companion

Transmit a forged or replayed Semaeopus frame from a HackRF so the
satellite's CC1101 accepts it. Useful for the L05/L06 attacks without a
Pico + CC1101 attacker modem, and needed for L10's RF jamming lab.

Every block and value below is exercised by
`tests/gnuradio/test_recipes.py` (with a File Sink in place of the
HackRF).

> **Legality.** In the US, 902 to 928 MHz is a Part 15 band, but a
> HackRF is not a certified Part 15 transmitter. Run this into a dummy
> load or through an attenuator and coax to the satellite, or inside a
> shielded box. The 902 to 928 MHz band is also the 33 cm amateur band,
> so a licensed amateur may transmit under Part 97 instead, with the
> station's call sign identified and without encryption: do not send
> L3 (AES) frames under amateur rules. Outside the US, 915 MHz is not an
> ISM band in most of Europe; use an EU (433.92 MHz) build there. Keep the
> HackRF's amp off.

## What a CC1101 will accept

The receiving CC1101 only keeps a frame that has, at 915 MHz, 9600 bit/s,
about 20.6 kHz deviation:

1. at least 4 bytes of `AA` preamble,
2. the sync word **twice** (`D3 91 D3 91`), because the radios run in
   30/32 sync mode,
3. `LEN`, the space packet and its CCSDS CRC (the frame as `sp.encode`
   builds it and the modems print it),
4. the radio's own CRC-16 (poly 0x8005, init 0xFFFF) over all of step 3.
   Without it the CC1101 discards the frame before the firmware sees it.

`tools/air_frame.py` builds exactly that.

## Inputs

```bash
# A FORCE_SAFE telecommand (accepted at security level 0)
python -m tools.air_frame --apid FORCE_SAFE --out /tmp/tc_air.bin

# Or replay a frame you captured: paste the hex from cap.jsonl ("frame")
python -m tools.air_frame --frame 0810ffc001ffffd7a0 --out /tmp/tc_air.bin
```

It prints the frame and the on-air bytes, for example:

```
frame   : 0810ffc001ffffd7a0
on air  : aaaaaaaaaaaaaaaad391d3910810ffc001ffffd7a062c50000
```

(8 preamble bytes to give the HackRF time to settle, 2 zero bytes at the
end so the radio CRC is not cut off. `--repeat 3` sends it three times.)

## Variables

| ID           | Value                     | Notes                                    |
|--------------|---------------------------|------------------------------------------|
| `samp_rate`  | `2.016e6`                 | 210 x 9600, so the bit rate is exact     |
| `bit_rate`   | `9600`                    |                                          |
| `sps`        | `int(samp_rate / bit_rate)` | 210                                    |
| `deviation`  | `20630`                   | match the CC1101 (DEVIATN 0x35)          |
| `rf_freq`    | `915e6`                   | `433.92e6` for an EU build               |

In the **Options** block set Generate Options to `No GUI` and Run Options
to `Run to Completion`, so the flowgraph stops after the file is sent.

## Blocks

### Block 1: File Source

| Property      | Value              |
|---------------|--------------------|
| File          | `/tmp/tc_air.bin`  |
| Output Type   | `byte`             |
| Repeat        | `No`               |

### Block 2: GFSK Mod

| Property          | Value                               |
|-------------------|-------------------------------------|
| Samples/Symbol    | `sps`                               |
| Sensitivity       | `2 * math.pi * deviation / samp_rate` |
| BT                | `0.5`                               |
| Unpack            | `On`                                |

GFSK Mod takes packed bytes and unpacks them itself, most significant
bit first, which is the CC1101's bit order. Do not put a Packed to
Unpacked block in front of it.

### Block 3: Multiply Const

Constant `0.7` (complex), to keep the HackRF's DAC out of clipping.

### Block 4: Soapy HackRF Sink

| Property            | Value        |
|---------------------|--------------|
| Sample Rate         | `samp_rate`  |
| Center Freq (Hz)    | `rf_freq`    |
| Amp On (+14 dB)     | `False`      |
| VGA Gain            | `20`         |
| Bandwidth           | `0` (auto)   |

With gr-osmosdr instead: **osmocom Sink**, device `hackrf=0`, same rate
and frequency, RF Gain `0` (amp off), IF Gain `20`, BB Gain `0`.

Start with VGA 20 and raise it a few dB at a time only if the satellite
does not hear you.

## Without GNU Radio

`tools/air_frame.py` can write the same signal as IQ for `hackrf_transfer`:

```bash
python -m tools.air_frame --apid FORCE_SAFE --out /tmp/tc_air.bin --iq /tmp/tc.cs8
hackrf_transfer -t /tmp/tc.cs8 -f 915000000 -s 2016000 -x 20
```

(`-x` is the TX VGA gain; the amp stays off unless you add `-a 1`.)

## Sanity check

A FORCE_SAFE takes about 21 ms on the air. The satellite should switch
to SAFE mode and list the accepted command on its screen, and the
operator ground station hears the frame too.

If nothing happens:

- Run the [RX recipe](gfsk_rx_recipe.md) on an RTL-SDR while you
  transmit. You should see `radio-crc=ok` for your frame. If you do not,
  the problem is on the TX side.
- Check the frequency. A HackRF's crystal can be off by about 20 ppm
  (18 kHz at 915 MHz). Put a **QT GUI Waterfall Sink** on the RX recipe's
  source and look at your transmission next to the satellite's beacon; if
  they are more than about 15 kHz apart, move `rf_freq` to close the gap.
- Make sure `deviation` is 20630, not the 4.8 kHz the synthetic captures
  use. The satellite's 58 kHz receive filter is set for the wide signal.
- At L1 and above, a forged frame also needs a valid HMAC (and at L2, a
  fresh nonce). The satellite then logs it as rejected, which means the
  RF side worked.
