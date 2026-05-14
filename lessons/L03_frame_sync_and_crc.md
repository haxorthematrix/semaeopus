# L03 — Frame sync & CRC

## Goal
Take a raw bitstream (e.g. the GFSK demod output from L02) and recover
*space packets* in pure Python — no CC1101, no GNU Radio packet
deframer. Verify the CRC.

## You'll need
- A bitstream file `bits.bin` (one bit per byte, 0 or 1) from the L02
  flowgraph's Binary Slicer.
- Python.

## The exercise

Write `find_packets.py`:

```python
import sys
from protocol.space_packet import crc16_ccitt

SYNC = 0xD391  # 16 bits, MSB first

def bits_to_bytes(bits, start_bit):
    out = bytearray()
    for i in range(start_bit, len(bits) - 7, 8):
        b = 0
        for j in range(8):
            b = (b << 1) | bits[i + j]
        out.append(b)
    return bytes(out)

bits = bytes(int(c) for c in open(sys.argv[1], "rb").read() if c in (0, 1))

# Sliding sync-word search
search = 0
for i in range(len(bits) - 16):
    word = 0
    for j in range(16):
        word = (word << 1) | bits[i + j]
    if word == SYNC:
        # next bytes are LEN, then frame, then CRC
        frame = bits_to_bytes(bits, i + 16)
        length = frame[0]
        body = frame[1:1 + length]
        if len(body) < length:
            continue
        space = body[:-2]
        crc = int.from_bytes(body[-2:], "big")
        ok = crc16_ccitt(space) == crc
        print(f"@bit {i}: len={length} crc_ok={ok} {body.hex()}")
```

Run against your capture, you should see most frames decode with
`crc_ok=True`. Frames that fail typically have one bit error from the
demod — increase RTL-SDR gain or shorten the distance and re-capture.

## Questions
- The CRC catches 1-bit errors with probability 1. What about 17-bit
  errors? (Hint: see *CCSDS 232.0-B-3* §5.4.)
- The sync word `0xD391` was chosen for its autocorrelation
  properties — pick a worse sync (say `0xAAAA`) and re-flash the
  satellite. What happens to your packet-recovery rate at the same
  RSSI?
