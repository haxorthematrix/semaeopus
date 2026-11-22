# GS front-end firmware (Pico USB modem)

A Raspberry Pi Pico + CC1101 that exposes the radio over USB-CDC as a
tiny ASCII modem; all decoding and command building happens on the
laptop. In the CYD build this is the **attacker** radio. A Pico built
this way can also serve as an operator ground station, though the CYD
ground station (`firmware/cyd_ground/`) is the recommended operator
station.

The modem logic is shared with the CYD ground station:
[`../shared/modem.py`](../shared/modem.py). This directory only holds the
Pico's pin map and LED.

## Wiring

| CC1101 | Pico            |
|--------|-----------------|
| SCK    | GP18 (pin 24)   |
| MOSI   | GP19 (pin 25)   |
| MISO   | GP16 (pin 21)   |
| CSN    | GP13 (pin 17)   |
| GDO0   | GP10 (pin 14)   |
| VCC    | 3V3 OUT (pin 36)|
| GND    | GND (pin 38)    |

MISO is GP16: SPI0 cannot use GP12, which earlier versions of this
README listed.

## Deploy

```bash
tools/deploy.sh pico-modem /dev/ttyACM0      # macOS: /dev/cu.usbmodem*
```

The modem powers up on 915 MHz; the host tools send `CFG` on connect
(default `--freq 915000000`).

## Wire protocol

ASCII, newline-terminated.

| Host → modem                           | Meaning                                         |
|----------------------------------------|-------------------------------------------------|
| `PING`                                 | Returns `PONG <ticks_ms>`                       |
| `TX <hex>`                             | Transmit a complete frame (LEN byte first, max 62 bytes) |
| `CFG <freq_hz> <sync_hex> <bitrate>`   | Retune (902–928 MHz or 433.05–434.79 MHz); bit rate stays 9600 |
| `BW <hz>`                              | Receive filter bandwidth, 58–812 kHz (lesson L10) |
| `PWR <dbm>`                            | Transmit power, -30 to +10 dBm                  |

| Modem → host                                             | Meaning            |
|----------------------------------------------------------|--------------------|
| `RX <hex> RSSI=<dbm> LQI=<n>`                            | Received frame     |
| `EVT <text>`                                             | Status / log       |
| `ERR <text>`                                             | Error (bad input is refused rather than wedging the radio) |

Frames pushed via `TX` must already include the variable-length packet
header byte. The host-side helpers in `protocol/space_packet.py` produce
exactly that format.
