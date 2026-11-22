# L00 — Build & first beacon

## Goal
By the end of this lesson you have:
- A satellite FlatSat humming on the bench, transmitting a beacon every 10 s.
- An operator ground station that decodes the beacon and shows live telemetry.

## You'll need
- The satellite parts from `hardware/satellite-bom.md`.
- The operator GS parts from `hardware/ground-station-bom.md`.
- A laptop with Python 3.11+ and `pyserial`.

## Steps

### 1. Build the hardware
**CYD build (recommended):** follow `hardware/cyd-build.md` (two CYDs:
satellite and ground station). **Pico build:** follow
`hardware/wiring-satellite.md` and `hardware/wiring-ground-station.md`.
Use 915 MHz antennas (82 mm wire) and keep the boards 1 to 3 m apart on
the bench.

### 2. Flash MicroPython
CYDs: `ESP32_GENERIC` with esptool (see `hardware/cyd-build.md`).
Picos: hold BOOTSEL, plug USB, drag the `RPI_PICO` `.uf2` onto the
mass-storage device that appears.

### 3. Deploy firmware
```bash
# CYD build
tools/deploy.sh cyd-satellite  /dev/cu.usbserial-AAAA
tools/deploy.sh cyd-ground     /dev/cu.usbserial-BBBB

# Pico build
tools/deploy.sh pico-satellite /dev/ttyACM0
tools/deploy.sh pico-modem     /dev/ttyACM1
```

### 4. Run the operator app
```bash
pip install pyserial
python -m groundstation.operator.gs --port <ground station port>
```

### Expected outcome
Within ~10 s you'll see lines like:
```
[    1 BEACON] TM  RSSI=-32  SEMAEOPUS-1 M0 B1 U10 SOC60
[    2 EPS_TLM] TM RSSI=-32  Vbus=3300mV I=15mA SoC=60% DAY
[    3 HK_TLM] TM RSSI=-32   up=10s boot=1 T=22.34°C P=1013hPa RH=42.1% mode=0 flg=0x00
```

The satellite's OLED shows the current mode and boot count. The TX LED
flashes on each transmission.

### Try it
At the `op>` prompt:
```
op> ping
[    7 PONG] TM ...
op> req 12
[    8 EPS_TLM] TM ...
op> mode 1            ← go to SAFE
op> mode 0            ← back to NOMINAL
```

### Troubleshooting
| Symptom                       | Likely cause                                       |
|-------------------------------|----------------------------------------------------|
| Nothing on the OLED           | I²C wiring wrong, or OLED at 0x3D not 0x3C         |
| RSSI ≈ -120 / no packets      | sync word mismatch, frequency mismatch             |
| `ERR cfg: parse`              | Bad CFG line — check `gs.py --freq` and `--sync`   |
| OBC reboots every few seconds | Power brown-out — use a powered USB hub            |
