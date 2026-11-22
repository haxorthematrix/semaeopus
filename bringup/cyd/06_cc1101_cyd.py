"""
CYD bring-up 06: CC1101 on the CYD's microSD slot.

Runs on an ESP32-2432S028R ("Cheap Yellow Display") with MicroPython.
Standalone, like the other bring-up scripts: it does not import any
Semaeopus firmware. Keep the pin values below in sync with
firmware/shared/cyd_pins.py.

    mpremote connect /dev/ttyUSB0 run bringup/cyd/06_cc1101_cyd.py

Each stage adds one more wire to what it proves, so the first FAIL
points at the fault:

  1  LED self-test            RGB LED steps R, G, B (MicroPython + GPIO alive)
  2  Chip ready (before SPI)  CSN low makes MISO go low (VCC, GND, CSN, MISO)
  3  ID @ 1 MHz               PARTNUM / VERSION read back (adds SCK)
  4  Write / read back        patterns written, then read (adds MOSI)
  5  GDO0 wire                GDO0 forced low, then high (CN1 IO27)
  6  ID + read back @ 5 MHz   stages 3-4 at operating speed
  7  RX at 915 MHz            PLL calibrates and locks into RX

Then a live RSSI meter runs for LISTEN_SECONDS. Key a 915 MHz source
nearby (for example a HackRF CW carrier at minimum gain) and watch it
rise. Ctrl-C ends it early.

The script never transmits. RGB LED at the end: green = all PASS,
red = at least one FAIL (details on the console).
"""

from machine import Pin, SPI
import time

# ---- CYD pins: keep in sync with firmware/shared/cyd_pins.py ---------------------
CC1101_SPI_ID = 2          # VSPI. SPI(1)/HSPI is the display.
PIN_SCK  = 18              # microSD CLK
PIN_MOSI = 23              # microSD CMD
PIN_MISO = 19              # microSD DAT0
PIN_CS   = 5               # microSD CD/DAT3
PIN_GDO0 = 27              # CN1 IO27
PIN_LED_R, PIN_LED_G, PIN_LED_B = 4, 16, 17     # active low

BAUD_BRINGUP = 1_000_000
BAUD_OPERATE = 5_000_000
RF_FREQ_HZ = 915_000_000
LISTEN_SECONDS = 20

# ---- CC1101 constants (subset of firmware/satellite/lib/cc1101.py) --------
SRES, SCAL, SRX, SIDLE, SFRX = 0x30, 0x33, 0x34, 0x36, 0x3A
IOCFG0, SYNC1, SYNC0, PKTLEN = 0x02, 0x04, 0x05, 0x06
FREQ2, FREQ1, FREQ0 = 0x0D, 0x0E, 0x0F
PARTNUM, VERSION, RSSI, MARCSTATE = 0x30, 0x31, 0x34, 0x35
XTAL_HZ = 26_000_000

GDO0_FORCE_LOW  = 0x2F     # IOCFG0 setting: GDO0 driven low
GDO0_FORCE_HIGH = 0x6F     # same, inverted: GDO0 driven high
MARC_IDLE, MARC_RX = 0x01, 0x0D

# Registers from the repo driver's configure_default() (9.6 kBaud 2-GFSK,
# 4.8 kHz deviation, 58 kHz RX bandwidth). Frequency is set separately.
MODEM_CONFIG = (
    (0x02, 0x06), (0x00, 0x29), (0x03, 0x47), (0x06, 0xFF), (0x07, 0x04),
    (0x08, 0x05), (0x0B, 0x06), (0x10, 0xF8), (0x11, 0x83), (0x12, 0x13),
    (0x13, 0x22), (0x14, 0xF8), (0x15, 0x35), (0x17, 0x30), (0x18, 0x18),
    (0x19, 0x16), (0x1B, 0x43), (0x22, 0x10), (0x23, 0xE9), (0x24, 0x2A),
    (0x25, 0x00), (0x26, 0x1F), (0x2C, 0x81), (0x2D, 0x35), (0x2E, 0x09),
)

# ---------------------------------------------------------------------------

results = []


def report(stage, ok, detail, hints=()):
    results.append((stage, ok))
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {stage}: {detail}")
    if not ok:
        for h in hints:
            print("         - " + h)
    return ok


leds = {"r": Pin(PIN_LED_R, Pin.OUT, value=1),
        "g": Pin(PIN_LED_G, Pin.OUT, value=1),
        "b": Pin(PIN_LED_B, Pin.OUT, value=1)}


def led(color=None):
    for name, pin in leds.items():
        pin.value(0 if name == color else 1)


def freq_word(hz):
    return int((hz << 16) / XTAL_HZ)


def rssi_dbm(raw):
    return (raw - 256) / 2 - 74 if raw >= 128 else raw / 2 - 74


# ---- 1. LED self-test -----------------------------------------------------
print("\nSemaeopus CYD bring-up 06: CC1101 on the microSD slot\n")
for c in ("r", "g", "b"):
    led(c)
    time.sleep_ms(250)
led()
report("1 LED self-test", True,
       "RGB LED should have stepped red, green, blue (if not, the LED, not the radio, is suspect)")

# ---- 2. Chip ready, before SPI owns the pins ------------------------------
# With CSN high the CC1101's SO pin is high-impedance, so the pull-up reads 1.
# Pulling CSN low makes SO drive CHIP_RDYn, which goes low once the crystal runs.
cs = Pin(PIN_CS, Pin.OUT, value=1)
miso_probe = Pin(PIN_MISO, Pin.IN, Pin.PULL_UP)
time.sleep_ms(2)
idle_level = miso_probe.value()
cs.value(0)
ready = False
t0 = time.ticks_us()
while time.ticks_diff(time.ticks_us(), t0) < 10_000:
    if miso_probe.value() == 0:
        ready = True
        break
cs.value(1)

if idle_level == 0:
    report("2 Chip ready", False, "MISO is low even with CSN high",
           ("remove any microSD card from the sniffer's socket",
            "MISO (sniffer DAT0) may be shorted to GND"))
elif not ready:
    report("2 Chip ready", False, "MISO never went low after CSN low (no CHIP_RDYn)",
           ("VCC to CN1 3.3V, GND to CN1 GND (3.3 V only, never 5 V)",
            "CSN to sniffer CD/DAT3 (GPIO5)",
            "MISO/SO to sniffer DAT0 (GPIO19)",
            "sniffer fully seated in the CYD's SD slot"))
else:
    report("2 Chip ready", True, "CHIP_RDYn seen (power, GND, CSN and MISO look connected)")

# ---- SPI helpers ------------------------------------------------------------
spi = None


def open_spi(baud):
    global spi
    if spi is not None:
        spi.deinit()
    spi = SPI(CC1101_SPI_ID, baudrate=baud, polarity=0, phase=0,
              sck=Pin(PIN_SCK), mosi=Pin(PIN_MOSI), miso=Pin(PIN_MISO))


def strobe(cmd):
    cs.value(0)
    spi.write(bytes([cmd]))
    cs.value(1)


def write_reg(addr, val):
    cs.value(0)
    spi.write(bytes([addr & 0x3F, val & 0xFF]))
    cs.value(1)


def read_reg(addr):
    cs.value(0)
    spi.write(bytes([addr | 0x80]))
    v = spi.read(1)[0]
    cs.value(1)
    return v


def read_status(addr):
    cs.value(0)
    spi.write(bytes([addr | 0xC0]))
    v = spi.read(1)[0]
    cs.value(1)
    return v


def reset_chip():
    # Manual reset per CC1101 datasheet section 19.1.2
    cs.value(1); time.sleep_us(40)
    cs.value(0); time.sleep_us(40)
    cs.value(1); time.sleep_us(40)
    strobe(SRES)
    time.sleep_ms(5)


def check_id(stage, baud, slow_ok=False):
    open_spi(baud)
    reset_chip()
    part, ver = read_status(PARTNUM), read_status(VERSION)
    detail = f"PARTNUM=0x{part:02X} (expect 0x00), VERSION=0x{ver:02X} (expect 0x04 or 0x14) at {baud // 1000} kHz"
    if part == 0x00 and ver not in (0x00, 0xFF):
        return report(stage, True, detail)
    if part == 0xFF and ver == 0xFF:
        hints = ("all ones: MISO floating or no chip; recheck VCC, CSN, MISO",)
    elif part == ver:
        hints = ("both reads returned the same byte (likely the chip status byte), so the",
                 "chip is not receiving the commands: check MOSI/SI to sniffer CMD (GPIO23),",
                 "then SCK to sniffer CLK (GPIO18) and GND")
    else:
        hints = ("unexpected values: check SCK and MOSI, keep leads short",
                 "possibly a clone or a different module; note the values")
    if slow_ok:
        hints = hints + ("passed at 1 MHz but not here: shorten leads or lower SPI_BAUD",)
    return report(stage, False, detail, hints)


READBACK = ((SYNC1, 0xA5), (SYNC0, 0x5A), (PKTLEN, 0x3C), (SYNC1, 0xFF), (SYNC0, 0x00))
RESET_DEFAULTS = {SYNC1: 0xD3, SYNC0: 0x91, PKTLEN: 0xFF,
                  FREQ2: 0x1E, FREQ1: 0xC4, FREQ0: 0xEC}


def check_readback(stage):
    fw = freq_word(RF_FREQ_HZ)
    pattern = READBACK + ((FREQ2, (fw >> 16) & 0xFF), (FREQ1, (fw >> 8) & 0xFF), (FREQ0, fw & 0xFF))
    bad = []
    for addr, val in pattern:
        write_reg(addr, val)
        got = read_reg(addr)
        if got != val:
            bad.append((addr, val, got))
    if not bad:
        return report(stage, True, f"{len(pattern)} register writes read back correctly (FREQ set to {RF_FREQ_HZ / 1e6:.3f} MHz)")
    addr, val, got = bad[0]
    detail = f"{len(bad)} of {len(pattern)} mismatched; first: reg 0x{addr:02X} wrote 0x{val:02X}, read 0x{got:02X}"
    reads = set(g for _, _, g in bad)
    if reads == {0xFF}:
        hints = ("every read returned 0xFF: the chip is not answering; fix stages 2-3 first",)
    elif all(RESET_DEFAULTS.get(a) == g for a, _, g in bad):
        hints = ("reads return reset defaults, so writes never arrive: check MOSI/SI to sniffer CMD (GPIO23)",)
    elif len(reads) == 1:
        hints = ("every read returned the same byte: the chip is not receiving commands; check MOSI (GPIO23)",)
    else:
        hints = ("intermittent bit errors: check MOSI and SCK, shorten leads, keep the sniffer seated",)
    return report(stage, False, detail, hints)


# ---- 3-4. ID and register read back at bring-up speed -----------------------
id_ok = check_id("3 ID @ 1 MHz", BAUD_BRINGUP)
rb_ok = check_readback("4 Write / read back")

# ---- 5. GDO0 wire -------------------------------------------------------------
gdo0 = Pin(PIN_GDO0, Pin.IN, Pin.PULL_DOWN)
write_reg(IOCFG0, GDO0_FORCE_LOW)
time.sleep_us(50)
lo = gdo0.value()
write_reg(IOCFG0, GDO0_FORCE_HIGH)
time.sleep_us(50)
hi = gdo0.value()
write_reg(IOCFG0, GDO0_FORCE_LOW)
if lo == 0 and hi == 1:
    report("5 GDO0 wire", True, "GPIO27 followed GDO0 low then high")
else:
    report("5 GDO0 wire", False, f"forced low read {lo}, forced high read {hi}",
           ("GDO0 to CN1 IO27; confirm your CN1 pin order on the silkscreen",
            "if your board has no IO27 on CN1, use IO22 and change PIN_GDO0"))

# ---- 6. Same checks at operating speed ----------------------------------------
fast_ok = check_id("6a ID @ 5 MHz", BAUD_OPERATE, slow_ok=id_ok)
fast_ok = check_readback("6b Write / read back @ 5 MHz") and fast_ok


# ---- 7. RX at 915 MHz ----------------------------------------------------------
def configure_rx():
    for addr, val in MODEM_CONFIG:
        write_reg(addr, val)
    fw = freq_word(RF_FREQ_HZ)
    write_reg(FREQ2, (fw >> 16) & 0xFF)
    write_reg(FREQ1, (fw >> 8) & 0xFF)
    write_reg(FREQ0, fw & 0xFF)
    strobe(SIDLE)
    strobe(SCAL)
    t0 = time.ticks_ms()
    while (read_status(MARCSTATE) & 0x1F) != MARC_IDLE and time.ticks_diff(time.ticks_ms(), t0) < 20:
        pass
    strobe(SFRX)
    strobe(SRX)
    t0 = time.ticks_ms()
    state = read_status(MARCSTATE) & 0x1F
    while state != MARC_RX and time.ticks_diff(time.ticks_ms(), t0) < 20:
        state = read_status(MARCSTATE) & 0x1F
    return state


rx_ok = False
if id_ok:
    state = configure_rx()
    if state == MARC_RX:
        samples = []
        for _ in range(16):
            samples.append(rssi_dbm(read_status(RSSI)))
            time.sleep_ms(5)
        avg = sum(samples) / len(samples)
        rx_ok = report("7 RX at 915 MHz", True,
                       f"in RX (MARCSTATE 0x0D), noise floor about {avg:.0f} dBm (expect roughly -100 to -110 with nothing transmitting)")
    else:
        report("7 RX at 915 MHz", False, f"MARCSTATE 0x{state:02X}, expected 0x0D (RX)",
               ("PLL did not lock: the module's crystal or RF section may be faulty",
                "confirm the module is a 868/915 MHz variant, not a 433 MHz one"))
else:
    report("7 RX at 915 MHz", False, "skipped because the chip ID check failed")

# ---- Summary ---------------------------------------------------------------------
fails = [s for s, ok in results if not ok]
print()
if fails:
    names = ", ".join(fails)
    print(f"RESULT: {len(fails)} stage(s) failed: {names}")
    print("Fix the FIRST failure above; later stages depend on it.")
    led("r")
else:
    print("RESULT: all stages PASS. The CC1101 is ready for the satellite firmware.")

# ---- Live RSSI meter ---------------------------------------------------------------
if rx_ok:
    print(f"\nLive RSSI at {RF_FREQ_HZ / 1e6:.3f} MHz for {LISTEN_SECONDS} s (Ctrl-C to stop).")
    print("Key a 915 MHz source nearby and the bar should jump.\n")
    led("b")
    peak = -200
    t0 = time.ticks_ms()
    try:
        while time.ticks_diff(time.ticks_ms(), t0) < LISTEN_SECONDS * 1000:
            dbm = rssi_dbm(read_status(RSSI))
            peak = max(peak, dbm)
            cells = int(max(0, min(40, (dbm + 110) / 2)))   # -110 dBm .. -30 dBm
            bar = "#" * cells + " " * (40 - cells)
            print(f"{dbm:7.1f} dBm |{bar}| peak {peak:.1f}")
            time.sleep_ms(250)
    except KeyboardInterrupt:
        pass
    strobe(SIDLE)
    print(f"\nPeak RSSI during the meter: {peak:.1f} dBm")

led("r" if fails else "g")
