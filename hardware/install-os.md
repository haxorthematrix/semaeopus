# OS install — from blank Pico to ready-to-deploy

This is the one-time setup. Do it once per Pico (you have at least
two: one for the satellite, one for the ground-station front-end).

## 1. Install MicroPython on each Pi Pico

Identify which Pico you have:

| Board                 | Look for                       | UF2 file                                                                                  |
|-----------------------|--------------------------------|-------------------------------------------------------------------------------------------|
| **Raspberry Pi Pico** | "Pico" in white silkscreen     | `RPI_PICO-*.uf2` — https://micropython.org/download/RPI_PICO/                             |
| **Raspberry Pi Pico W** | adds "W" + tiny shielded module | `RPI_PICO_W-*.uf2` — https://micropython.org/download/RPI_PICO_W/                       |
| **Raspberry Pi Pico 2** | RP2350 chip, USB-C            | `RPI_PICO2-*.uf2` — https://micropython.org/download/RPI_PICO2/                           |
| **Raspberry Pi Pico 2 W** | RP2350 + wifi                | `RPI_PICO2_W-*.uf2` — https://micropython.org/download/RPI_PICO2_W/                       |

Semaeopus is tested against MicroPython **v1.22** and newer. Either
grab the latest stable release or download a known-good build:
[1.24.1 RPI_PICO_W.uf2](https://micropython.org/resources/firmware/RPI_PICO_W-20241129-v1.24.1.uf2).

### Flash

1. Hold the **BOOTSEL** button on the Pico while plugging it in (or
   while pressing **RESET** if you wired one).
2. The Pico mounts as a USB mass-storage device called `RPI-RP2`
   (Pico/Pico W) or `RP2350` (Pico 2).
3. Drag the `.uf2` file onto that drive. The drive unmounts and the
   Pico reboots into MicroPython.

### Verify

Plug the Pico in (no BOOTSEL this time) and look for a new serial
device. **Don't drop into the REPL yet — your shell needs to know how.**

| OS                  | What you'll see                                  |
|---------------------|--------------------------------------------------|
| macOS               | `/dev/tty.usbmodem*` and `/dev/cu.usbmodem*`     |
| Linux               | `/dev/ttyACM0` (rises by 1 for each extra Pico)  |
| Windows             | A new COM port; check Device Manager             |

---

## 2. Install host-side tooling

You need Python 3.11+ and `mpremote` to push code to the Picos. You
also want `pyserial` and `pytest` for the ground-station apps and the
test suite.

### macOS

```bash
brew install python@3.11
python3.11 -m pip install --user mpremote pyserial pytest
# Optional but useful:
brew install gnu-radio gqrx inspectrum rtl-sdr
```

### Linux (Debian / Ubuntu / similar)

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
python3 -m pip install --user mpremote pyserial pytest

# Serial ports require dialout/uucp/plugdev group membership — log out
# and back in after running:
sudo usermod -a -G dialout "$USER"

# Optional:
sudo apt install -y gnuradio gr-satellites rtl-sdr gqrx-sdr inspectrum
```

### Windows

1. Install **Python 3.11+** from python.org (tick "Add Python to
   PATH" in the installer).
2. Open PowerShell (or Command Prompt):
   ```powershell
   py -3 -m pip install --user mpremote pyserial pytest
   ```
3. Windows assigns each Pico a COM port (e.g. `COM5`). Open Device
   Manager → "Ports (COM & LPT)" to find it. The `mpremote` syntax
   becomes `mpremote connect COM5` instead of `mpremote connect /dev/ttyACM0`.
4. (Optional) Install **WSL2** with Ubuntu and follow the Linux path
   if you want GNU Radio.

### Confirm `mpremote` can see your Pico

Plug a flashed Pico in and run:

```bash
mpremote devs
# expected output, one line per attached Pico:
#   /dev/ttyACM0 e6614c775b8b6a25 2e8a:0005 MicroPython Board in FS mode
```

If you see your Pico, you're done with the OS install. Next:
[`hardware/bringup-checks.md`](bringup-checks.md) walks the
post-wiring sanity checks.

---

## 3. Clone Semaeopus

```bash
git clone https://github.com/haxorthematrix/semaeopus.git
cd semaeopus
```

Run the software-only tests first — they need no hardware and confirm
your Python environment is sound:

```bash
python3 -m pytest tests/ -q
# expect: 35 passed, 1 skipped in ~22s
```

If those pass, you have a known-good base. The hardware bring-up
scripts in `bringup/` will run from the same checkout via
`mpremote run bringup/<script>.py`.

---

## Common install problems

| Symptom                                     | Fix                                                         |
|---------------------------------------------|-------------------------------------------------------------|
| `mpremote: command not found`               | `--user` install isn't on PATH — add `~/.local/bin` or use `pipx install mpremote` |
| `Permission denied: /dev/ttyACM0` (Linux)   | Not in `dialout`. `sudo usermod -a -G dialout "$USER"` then re-login          |
| Pico mounts as `RPI-RP2` but file copy hangs| The Pico's mass-storage driver is slow on Windows — wait 30 s, don't unplug   |
| Pico isn't seen in `mpremote devs`          | Did you flash MicroPython? In BOOTSEL mode the Pico shows only as mass storage |
| `ImportError: no module named usocket`      | You're on CircuitPython, not MicroPython — different firmware. Re-flash       |
| Two Picos show as `/dev/ttyACM0` and `…1` but you can't tell which is which | `mpremote devs` shows the serial number; or unplug one |
