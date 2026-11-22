# Satellite firmware

MicroPython for RP2040 (Raspberry Pi Pico / Pico W / Pico 2).

## Deploy

> The recommended satellite is now the CYD build in
> [`../cyd_satellite/`](../cyd_satellite/) (see
> [`../../hardware/cyd-build.md`](../../hardware/cyd-build.md)). It reuses
> this directory's `obc/`, `comms/` and `lib/cc1101.py`, so changes here
> apply to both builds.

1. Flash MicroPython (≥ 1.22) to the Pico — drag a `.uf2` while holding
   BOOTSEL.
2. Copy the firmware, which also brings `protocol/space_packet.py` along:

   ```bash
   tools/deploy.sh pico-satellite /dev/ttyACM0
   ```

3. The Pico resets. The OLED should light up with the call sign and
   beacon counter inside ~2 s; the TX LED blinks every time the radio
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
