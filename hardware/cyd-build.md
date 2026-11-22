# CYD build: satellite, ground station and attacker

The recommended hardware build. Two ESP32-2432S028R "Cheap Yellow
Display" (CYD) boards become the satellite and the operator ground
station; a Raspberry Pi Pico becomes the attacker's USB radio modem.
Everything runs MicroPython at 915 MHz.

| Board  | Role                          | MicroPython image       | Deploy target   |
|--------|-------------------------------|-------------------------|-----------------|
| CYD #1 | Satellite                     | `ESP32_GENERIC` (`.bin`) | `cyd-satellite` |
| CYD #2 | Operator ground station modem | `ESP32_GENERIC` (`.bin`) | `cyd-ground`    |
| Pico   | Attacker modem                | `RPI_PICO` (`.uf2`)      | `pico-modem`    |

## Parts

Per CYD node (about US$30):

* **ESP32-2432S028R CYD.** The USB-C "CYD2USB" revision works too.
* **CC1101 868/915 MHz module.** Buy the band-matched version, such as
  the Ebyte E07-900M10S. Many "315/433/868/915" listings are 433 MHz
  boards and perform poorly at 915.
* **microSD sniffer / breakout.** It plugs into the CYD's SD slot and
  breaks the pins out to a 0.1″ header.
* **JST 1.25 mm 4-pin pigtail** for the CN1 header.
* **About 7 female-female Dupont jumpers.**
* **A 915 MHz SMA antenna, or 82 mm of 22 AWG solid wire.**

For the attacker: a Raspberry Pi Pico, a 915 MHz CC1101 and jumpers.
A HackRF One covers the spectrum and jamming lessons.

## Wiring

### CYD ↔ CC1101 (both CYDs, identical)

| CC1101 pin | CYD source              | ESP32 GPIO |
|------------|-------------------------|------------|
| SCK        | microSD sniffer CLK     | 18         |
| MOSI (SI)  | microSD sniffer CMD     | 23         |
| MISO (SO)  | microSD sniffer DAT0    | 19         |
| CSN        | microSD sniffer CD/DAT3 | 5          |
| GDO0       | CN1 IO27                | 27         |
| VCC        | CN1 3.3V                | —          |
| GND        | CN1 GND                 | —          |

* **3.3 V only.** Never connect the CC1101 to 5 V.
* **Leave the sniffer's own microSD socket empty.** A card in it shares
  the SPI bus with the radio.
* **Wire by the labels on the CC1101.** Module pinouts vary by vendor,
  so don't go by pin position.
* **Check CN1's pin order on your board's silkscreen.** It's usually
  GND, IO22, IO27, 3.3V. If yours has no IO27, use IO22 and change
  `PIN_CC1101_GDO0` in `firmware/shared/cyd_pins.py`.

### Pico ↔ CC1101 (attacker)

| CC1101 pin | Pico pin          |
|------------|-------------------|
| SCK        | GP18 (pin 24)     |
| MOSI (SI)  | GP19 (pin 25)     |
| MISO (SO)  | GP16 (pin 21)     |
| CSN        | GP13 (pin 17)     |
| GDO0       | GP10 (pin 14)     |
| VCC        | 3V3 OUT (pin 36)  |
| GND        | GND (pin 38)      |

MISO must be GP16. SPI0 cannot use GP12, which the original pin map used.

## 1. Tools (laptop)

```bash
python3 -m pip install esptool mpremote pyserial
```

`tools/deploy.sh` finds mpremote whether or not its folder is on your
PATH (macOS user installs often aren't). A standalone `esptool`
executable works in place of `python3 -m esptool`.

**Finding ports:** plug in **one board at a time** and run `ls /dev/cu.*`.
* A CYD shows up as `/dev/cu.usbserial-*` (Linux: `/dev/ttyUSB*`).
* A Pico running MicroPython shows up as `/dev/cu.usbmodem*`
  (Linux: `/dev/ttyACM*`).

## 2. Flash MicroPython

Download the latest stable images from
https://micropython.org/download/ESP32_GENERIC/ and
https://micropython.org/download/RPI_PICO/ (`RPI_PICO_W` or `RPI_PICO2`
for those boards).

**Each CYD:**

```bash
python3 -m esptool --port /dev/cu.usbserial-XXXX erase_flash
python3 -m esptool --port /dev/cu.usbserial-XXXX --baud 460800 write_flash -z 0x1000 ESP32_GENERIC-<version>.bin
```

(esptool v5 also accepts `erase-flash` / `write-flash`.) If esptool
can't connect, put the ESP32 in its ROM bootloader: hold **BOOT**, tap
**RST**, then release BOOT. The bootloader lives in ROM, so no flash can
brick it.

**Pico:** hold **BOOTSEL** while plugging it in, then drag the `.uf2`
onto the `RPI-RP2` drive.

## 3. Radio bring-up test

```bash
tools/deploy.sh bringup-cyd  /dev/cu.usbserial-XXXX   # each CYD
tools/deploy.sh bringup-pico /dev/cu.usbmodemXXXX     # the Pico
```

The CYD test runs seven stages, and each one checks one more wire than
the last. Fix the first FAIL; its message names the wire to check. See
[`bringup/cyd/README.md`](../bringup/cyd/README.md).

## 4. Deploy

```bash
tools/deploy.sh cyd-satellite /dev/cu.usbserial-AAAA
tools/deploy.sh cyd-ground    /dev/cu.usbserial-BBBB
tools/deploy.sh pico-modem    /dev/cu.usbmodemCCCC
```

Each board resets into its firmware.

**Satellite.** It runs from any USB power source and needs no laptop.
It beacons every 10 s and sends housekeeping, ADCS and EPS telemetry
every 2 to 5 s.
* **Screen:** mode, battery, sun level, counters, and the last five
  commands accepted or rejected.
* **LED:** blue = transmit, green = command accepted, red = command
  rejected.
* **Inputs:** the light sensor beside the screen drives the power
  telemetry; cover it and shine a light on it once to calibrate.
  **BOOT** tumbles the satellite for 10 s.
* **To stop it** for a REPL, press BOOT within 2 s of reset.

**Ground station.** A USB modem with a status screen: frequency,
packet counters, signal strength, and the decoded header of the last
packet heard.

**Attacker.** A USB modem whose on-board LED flashes on every packet.

## 5. First end-to-end test

Keep the boards **1 to 3 m apart**. Closer than about 30 cm, the
receivers overload (RSSI around -20 dBm).

```bash
python3 -m groundstation.operator.gs --port /dev/cu.usbserial-BBBB
op> ping      # PONG; the satellite screen logs "TC PING ok"
op> req 12    # EPS telemetry (APID in hex)
op> safe      # satellite screen turns red: SAFE
op> mode 0    # back to NOMINAL
```

Then attack it (lessons L05 and L06):

```bash
python3 -m groundstation.attacker.capture --port /dev/cu.usbmodemCCCC --out cap.jsonl
python3 -m groundstation.attacker.replay  --port /dev/cu.usbmodemCCCC --in cap.jsonl --apid 0xFF
python3 -m groundstation.attacker.inject  --port /dev/cu.usbmodemCCCC --apid 0xFF
```

The laptop tools default to 915 MHz. Opening the ground station's port
resets the CYD (its USB adapter does this); it is ready again in about
2 s.

## Settings

Edit these, then redeploy:

* **`SECURITY_LEVEL`** (0 to 3) in `firmware/cyd_satellite/config.py`.
  Run the operator to match, e.g.
  `--security 2 --key 53656d61656f7075734b65795f763031` for the default
  key.
* **`DISPLAY_MADCTL`**, in both CYD `config.py` files: screen
  orientation.
  * Upside down: use `0xE8`.
  * Mirrored: try `0x68` or `0xA8`.
  * Red and blue swapped: clear the `0x08` bit.
* **`DISPLAY_INVERT = True`**: for USB-C CYD2USB boards with inverted
  colours.
* **`LDR_BRIGHT_IS_LOW`**: flip it if the sun gauge reads backwards.

## Modem commands

The CYD ground station and Pico modem speak the same line protocol as
before (`PING`, `TX`, `CFG`), so every tool in `groundstation/` works
unchanged. Two commands are new:
* **`BW <hz>`**: receive filter bandwidth, 58 kHz to 812 kHz. A narrow
  filter lets the attacker hear a command right beside a jammer in L10.
* **`PWR <dbm>`**: transmit power, -30 to +10 dBm.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `mpremote: command not found` | `python3 -m pip install mpremote`; `tools/deploy.sh` also finds it as `python3 -m mpremote` |
| `failed to access <port> (it may be in use)` | Check the port name (`ls /dev/cu.*`). Close `gs.py`, serial monitors and other `mpremote` sessions; `lsof <port>` shows who holds it |
| `RX (bad): bad CRC` at strong RSSI | Move the boards further apart |
| Board missing from `ls /dev/cu.*` | Disconnect the CC1101, try another cable or port, and check CN1's 3.3 V with a meter. Firmware can't make the USB chip disappear |
| Screen dark after flashing MicroPython | Normal; the backlight comes on once the satellite or ground firmware runs |
