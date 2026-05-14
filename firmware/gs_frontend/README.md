# GS Front-end firmware

Both the **operator** Pico and the **attacker** Pico run this same
firmware. It exposes the CC1101 radio over USB-CDC as a tiny ASCII
modem; all decoding and command building happens on the laptop.

## Deploy

Copy `lib/cc1101.py` from `firmware/satellite/lib/cc1101.py` into this
directory's `lib/` (or symlink), then upload:

```
mpremote connect /dev/ttyACM0 cp main.py :main.py
mpremote cp -r lib :/lib
```

## Wire protocol

ASCII, newline-terminated.

| Host → Pico                            | Meaning                                |
|----------------------------------------|----------------------------------------|
| `PING`                                 | Returns `PONG <ticks_ms>`              |
| `TX <hex>`                             | Pushes raw bytes to CC1101 TX FIFO     |
| `CFG <freq_hz> <sync_hex> <bitrate>`   | Reconfigure radio                      |

| Pico → host                                              | Meaning            |
|----------------------------------------------------------|--------------------|
| `RX <hex> RSSI=<dbm> LQI=<n>`                            | Received frame     |
| `EVT <text>`                                             | Status / log       |
| `ERR <text>`                                             | Error              |

Frames pushed via `TX` must already include the variable-length packet
header byte. The host-side helpers in `protocol/space_packet.py` produce
exactly that format.
