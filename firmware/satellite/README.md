# Satellite firmware

MicroPython for RP2040 (Raspberry Pi Pico / Pico W / Pico 2).

## Deploy

1. Flash MicroPython (≥ 1.22) to the Pico — drag a `.uf2` while holding
   BOOTSEL.
2. Copy the contents of this directory **plus** `protocol/space_packet.py`
   onto the Pico's filesystem. Recommended layout on the Pico:

   ```
   /
   ├── main.py
   ├── config.py
   ├── boot_count.txt        ← created on first boot
   ├── lib/
   │   ├── cc1101.py
   │   ├── ssd1306.py
   │   ├── bme280.py
   │   ├── mpu6050.py
   │   ├── ina219.py
   │   ├── ds3231.py
   │   └── __init__.py
   ├── obc/
   │   └── …
   ├── comms/
   │   └── …
   └── protocol/
       ├── __init__.py
       └── space_packet.py   ← copy of project-root protocol/space_packet.py
   ```

   With Thonny: open the project directory, right-click each → "Upload to
   /". With `mpremote`:

   ```
   mpremote connect /dev/ttyACM0 cp -r firmware/satellite/. :/
   mpremote cp protocol/space_packet.py :/protocol/space_packet.py
   ```

3. Hard-reset the Pico. The OLED should light up with the call sign and
   beacon counter inside ~2 s; a green LED blinks every time the radio
   transmits.

## Configuration

All build-time knobs live in `config.py`. Change `RF_FREQ_HZ`,
`SECURITY_LEVEL`, the call sign, or sync word and re-upload `config.py`
only — the rest of the firmware doesn't need a re-flash.

## Lesson level cheat-sheet

| `SECURITY_LEVEL` | What it enables                   | Used in lessons |
|------------------|-----------------------------------|-----------------|
| 0 (default)      | Cleartext, no auth                | L00 – L06       |
| 1                | HMAC over body only               | L07             |
| 2                | HMAC over (nonce ‖ body), nonce monotonic | L08 – L09 |
| 3                | + AES-128-CTR on user data        | L10 +           |
