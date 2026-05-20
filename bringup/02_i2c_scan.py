"""
Bring-up 02 — I²C bus scan.

Sweeps both I²C buses for devices. The Semaeopus FlatSat puts most
sensors on bus 0 and the RTC alone on bus 1 (to avoid the
MPU6050 ↔ DS3231 0x68 collision).

Expected addresses:

    bus 0 (SDA=GP4, SCL=GP5):
        0x3C  SSD1306 OLED   (sometimes 0x3D — check the silk)
        0x40  INA219
        0x68  MPU6050        (or 0x69 if you tied AD0 high)
        0x76  BME280         (or 0x77 on some breakouts)

    bus 1 (SDA=GP20, SCL=GP21):
        0x68  DS3231

If you see fewer devices than expected, FAIL prints which subsystem is
missing and what to check.
"""

from machine import Pin, I2C


EXPECT_BUS0 = {
    0x3C: "SSD1306 OLED",
    0x40: "INA219 (power)",
    0x68: "MPU6050 (IMU)",
    0x76: "BME280 (env)",
}
EXPECT_BUS1 = {
    0x68: "DS3231 (RTC)",
}


def scan(name, sda, scl, expect):
    print(f"--- {name}  (SDA=GP{sda}  SCL=GP{scl}) ---")
    try:
        bus = I2C(0 if name.endswith("0") else 1, sda=Pin(sda), scl=Pin(scl), freq=100_000)
        found = bus.scan()
    except OSError as e:
        print(f"  bus error: {e}  (check pull-ups and wiring)")
        return False, []
    if not found:
        print("  no devices responded")
        return False, []
    found_set = set(found)
    for addr in sorted(found_set):
        tag = expect.get(addr, "??? unknown — extra device?")
        print(f"  0x{addr:02X}  {tag}")
    missing = set(expect.keys()) - found_set
    if missing:
        for addr in sorted(missing):
            print(f"  MISSING  0x{addr:02X}  {expect[addr]}")
        return False, found
    return True, found


ok0, _ = scan("bus 0", 4,  5,  EXPECT_BUS0)
ok1, _ = scan("bus 1", 20, 21, EXPECT_BUS1)
if ok0 and ok1:
    print("PASS: all expected I2C devices present")
else:
    print("FAIL: see MISSING lines above — check 3V3 rail, GND, SDA/SCL pull-ups, and address-select jumpers")
