# Ground Station — Bill of Materials

Semaeopus uses **two** ground stations: the "operator" (who legitimately
flies the satellite) and the "attacker" (who interferes with the link).
Both can run from the same laptop, with separate USB devices.

---

## Operator Ground Station (~ $20)

| # | Part                                | Role                              | Qty | Approx $ |
|---|-------------------------------------|-----------------------------------|-----|---------:|
| 1 | Raspberry Pi Pico                   | Radio front-end + USB-serial      | 1   | 4–6      |
| 2 | CC1101 433/915 MHz module           | UHF transceiver (match satellite) | 1   | 3–6      |
| 3 | SSD1306 0.96" I²C OLED              | At-a-glance link status           | 1   | 3–5      |
| 4 | Half-size breadboard                | Build substrate                   | 1   | 4–6      |
| 5 | Dupont wires                        | Wiring                            | 20  | 2–3      |
| 6 | 17 cm wire (433 MHz) or 8.2 cm (915)| ¼-wave antenna                    | 1   | <1       |
| 7 | USB cable                           | Pico → laptop                     | 1   | 2–4      |

The Pico runs a tiny firmware (`firmware/gs_frontend/`) that exposes the
CC1101 over USB-CDC: send a TX framing command, receive bytes-with-RSSI
for each RX'd packet. All decoding happens in the Python application on
the laptop (`groundstation/operator/gs.py`).

---

## Attacker Ground Station (two tiers)

### Tier 1 — "Minimum" (~ $45)

Sufficient for lessons L00–L09.

| # | Part                                    | Role                                | Qty | Approx $ |
|---|-----------------------------------------|-------------------------------------|-----|---------:|
| 1 | RTL-SDR v3 dongle + telescopic antenna  | Wideband RX (24 MHz – 1.7 GHz)      | 1   | 25–35    |
| 2 | Raspberry Pi Pico                       | Active-TX front-end (replay/inject) | 1   | 4–6      |
| 3 | CC1101 433/915 MHz module               | Active-TX transceiver               | 1   | 3–6      |
| 4 | Breadboard + Dupont + antenna wire      | As per operator GS                  | —   | 6–10     |

### Tier 2 — "Recommended" — add a HackRF One (~ $330 more)

Unlocks lessons L10 (jamming), an optional **GPS-spoofing lab**, and the
"build your own GFSK TX in GNU Radio" path. The HackRF transmits, the
RTL-SDR continues to receive (HackRF is half-duplex).

| # | Part         | Role                                  | Qty | Approx $ |
|---|--------------|---------------------------------------|-----|---------:|
| 1 | HackRF One   | Full-duplex-ish 1 MHz – 6 GHz SDR     | 1   | 320–360  |
| 2 | ANT500 ant.  | Telescopic antenna for HackRF         | 1   | 15       |

---

## Common laptop-side software

The instructions assume a Linux laptop (or WSL2 / Linux VM under macOS or
Windows). Versions are minimums.

| Package                | Why                                          |
|------------------------|----------------------------------------------|
| Python 3.11+           | All ground-station code                      |
| `pyserial`             | USB-serial to Pico front-ends                |
| `numpy`, `scipy`, `matplotlib` | Demod + plotting                     |
| `textual` or `rich`    | Operator TUI                                 |
| `gnuradio` ≥ 3.10      | Spectrum / demod flowgraphs                  |
| `gr-satellites`        | Reference CCSDS / AX.25 decoder for compare  |
| `rtl-sdr` + drivers    | RTL-SDR dongle                               |
| `hackrf` + drivers     | (if using HackRF)                            |
| `gqrx` or `SDR++`      | Visual spectrum exploration                  |
| `inspectrum`           | Offline IQ-capture inspection                |

Install on Debian/Ubuntu:

```
sudo apt install python3 python3-pip gnuradio gr-satellites \
    rtl-sdr hackrf gqrx-sdr inspectrum
pip install pyserial numpy scipy matplotlib textual rich
```
