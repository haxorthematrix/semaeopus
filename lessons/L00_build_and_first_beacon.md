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
Follow `hardware/wiring-satellite.md` and `hardware/wiring-ground-station.md`.
Power both Picos from the same laptop via USB. Antennas are the
included 17 cm wires (433 MHz) — keep them ~30 cm apart on the bench.

### 2. Flash MicroPython
On both Picos: hold BOOTSEL, plug USB, drag `rp2-pico-v1.22.x.uf2`
onto the mass-storage device that appears.

### 3. Deploy firmware
```bash
# Satellite
mpremote connect /dev/ttyACM0 cp -r firmware/satellite/. :/
mpremote connect /dev/ttyACM0 cp -r protocol :/protocol

# Ground-station front-end (the other Pico)
mpremote connect /dev/ttyACM1 cp -r firmware/gs_frontend/. :/
mpremote connect /dev/ttyACM1 cp firmware/satellite/lib/cc1101.py :/lib/cc1101.py
```

### 4. Run the operator app
```bash
pip install pyserial
python -m groundstation.operator.gs --port /dev/ttyACM1
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
