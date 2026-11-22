/*
  CYD bring-up 06: CC1101 on the CYD's microSD slot (Arduino version).

  Same stages and pass/fail logic as bringup/cyd/06_cc1101_cyd.py, for
  when you want to check the hardware without flashing MicroPython.
  Pins match firmware/shared/cyd_pins.py.

  Board:   "ESP32 Dev Module" (arduino-esp32 core 2.x or 3.x)
  Serial:  115200 baud
  No libraries needed beyond the core's SPI.

  The sketch never transmits. RGB LED at the end of setup():
  green = all PASS, red = at least one FAIL. After that, loop() prints
  a live RSSI meter at 915 MHz (blue LED) if the radio reached RX.
*/

#include <SPI.h>
#include "driver/gpio.h"   // gpio_get_level: reads MISO even while SPI owns the pin

// ---- CYD pins: keep in sync with firmware/shared/cyd_pins.py --------------------
constexpr int PIN_SCK  = 18;   // microSD CLK
constexpr int PIN_MOSI = 23;   // microSD CMD
constexpr int PIN_MISO = 19;   // microSD DAT0
constexpr int PIN_CS   = 5;    // microSD CD/DAT3
constexpr int PIN_GDO0 = 27;   // CN1 IO27
constexpr int PIN_LED_R = 4, PIN_LED_G = 16, PIN_LED_B = 17;   // active low

constexpr uint32_t BAUD_BRINGUP = 1000000;
constexpr uint32_t BAUD_OPERATE = 5000000;
constexpr uint32_t RF_FREQ_HZ   = 915000000UL;
constexpr uint32_t XTAL_HZ      = 26000000UL;

// ---- CC1101 constants ------------------------------------------------------
constexpr uint8_t SRES = 0x30, SCAL = 0x33, SRX = 0x34, SIDLE = 0x36, SFRX = 0x3A;
constexpr uint8_t IOCFG0 = 0x02, SYNC1 = 0x04, SYNC0 = 0x05, PKTLEN = 0x06;
constexpr uint8_t FREQ2 = 0x0D, FREQ1 = 0x0E, FREQ0 = 0x0F;
constexpr uint8_t PARTNUM = 0x30, VERSION = 0x31, RSSI = 0x34, MARCSTATE = 0x35;
constexpr uint8_t GDO0_FORCE_LOW = 0x2F, GDO0_FORCE_HIGH = 0x6F;
constexpr uint8_t MARC_IDLE = 0x01, MARC_RX = 0x0D;

// Same modem registers as the repo driver's configure_default()
const uint8_t MODEM_CONFIG[][2] = {
  {0x02,0x06},{0x00,0x29},{0x03,0x47},{0x06,0xFF},{0x07,0x04},
  {0x08,0x05},{0x0B,0x06},{0x10,0xF8},{0x11,0x83},{0x12,0x13},
  {0x13,0x22},{0x14,0xF8},{0x15,0x35},{0x17,0x30},{0x18,0x18},
  {0x19,0x16},{0x1B,0x43},{0x22,0x10},{0x23,0xE9},{0x24,0x2A},
  {0x25,0x00},{0x26,0x1F},{0x2C,0x81},{0x2D,0x35},{0x2E,0x09},
};

SPIClass radioSpi(VSPI);   // HSPI belongs to the display
uint32_t spiHz = BAUD_BRINGUP;
int failCount = 0;
bool rxOk = false;

// ---- helpers -----------------------------------------------------------------
void led(char c) {
  digitalWrite(PIN_LED_R, c == 'r' ? LOW : HIGH);
  digitalWrite(PIN_LED_G, c == 'g' ? LOW : HIGH);
  digitalWrite(PIN_LED_B, c == 'b' ? LOW : HIGH);
}

char detail[200];   // scratch buffer for report() messages

bool report(const char *stage, bool ok, const char *msg,
            const char *h1 = nullptr, const char *h2 = nullptr, const char *h3 = nullptr) {
  Serial.printf("[%s] %s: %s\n", ok ? "PASS" : "FAIL", stage, msg);
  if (!ok) {
    failCount++;
    for (const char *h : {h1, h2, h3}) if (h) Serial.printf("         - %s\n", h);
  }
  return ok;
}

void csSelect() {
  radioSpi.beginTransaction(SPISettings(spiHz, MSBFIRST, SPI_MODE0));
  digitalWrite(PIN_CS, LOW);
  uint32_t t0 = micros();                       // wait for CHIP_RDYn, bounded
  while (gpio_get_level((gpio_num_t)PIN_MISO) && micros() - t0 < 2000) {}
}

void csDeselect() {
  digitalWrite(PIN_CS, HIGH);
  radioSpi.endTransaction();
}

void strobe(uint8_t cmd) { csSelect(); radioSpi.transfer(cmd); csDeselect(); }

void writeReg(uint8_t addr, uint8_t val) {
  csSelect(); radioSpi.transfer(addr & 0x3F); radioSpi.transfer(val); csDeselect();
}

uint8_t readReg(uint8_t addr) {
  csSelect(); radioSpi.transfer(addr | 0x80); uint8_t v = radioSpi.transfer(0); csDeselect();
  return v;
}

uint8_t readStatus(uint8_t addr) {
  csSelect(); radioSpi.transfer(addr | 0xC0); uint8_t v = radioSpi.transfer(0); csDeselect();
  return v;
}

void resetChip() {
  digitalWrite(PIN_CS, HIGH); delayMicroseconds(40);
  digitalWrite(PIN_CS, LOW);  delayMicroseconds(40);
  digitalWrite(PIN_CS, HIGH); delayMicroseconds(40);
  strobe(SRES);
  delay(5);
}

uint32_t freqWord(uint32_t hz) { return (uint32_t)(((uint64_t)hz << 16) / XTAL_HZ); }

float rssiDbm(uint8_t raw) { return (raw >= 128 ? ((int)raw - 256) / 2.0f : raw / 2.0f) - 74; }

// ---- stages ---------------------------------------------------------------------
bool checkId(const char *stage, uint32_t hz, bool slowOk) {
  spiHz = hz;
  resetChip();
  uint8_t part = readStatus(PARTNUM), ver = readStatus(VERSION);
  char d[120];
  snprintf(d, sizeof d, "PARTNUM=0x%02X (expect 0x00), VERSION=0x%02X (expect 0x04 or 0x14) at %lu kHz",
           part, ver, (unsigned long)(hz / 1000));
  if (part == 0x00 && ver != 0x00 && ver != 0xFF) return report(stage, true, d);
  const char *speed = slowOk ? "passed at 1 MHz but not here: shorten leads or lower BAUD_OPERATE" : nullptr;
  if (part == 0xFF && ver == 0xFF)
    return report(stage, false, d, "all ones: MISO floating or no chip; recheck VCC, CSN, MISO", speed);
  if (part == ver)
    return report(stage, false, d, "same byte twice (likely the status byte): chip is not receiving commands;",
                  "check MOSI/SI to sniffer CMD (GPIO23), then SCK (GPIO18) and GND", speed);
  return report(stage, false, d, "unexpected values: check SCK and MOSI, keep leads short",
                "possibly a clone or a different module; note the values", speed);
}

bool checkReadback(const char *stage) {
  uint32_t fw = freqWord(RF_FREQ_HZ);
  const uint8_t pattern[][2] = {
    {SYNC1,0xA5},{SYNC0,0x5A},{PKTLEN,0x3C},{SYNC1,0xFF},{SYNC0,0x00},
    {FREQ2,(uint8_t)(fw >> 16)},{FREQ1,(uint8_t)(fw >> 8)},{FREQ0,(uint8_t)fw},
  };
  const int n = sizeof(pattern) / sizeof(pattern[0]);
  int bad = 0, allFF = 1, sameByte = 1, firstGot = -1, firstIdx = -1;
  for (int i = 0; i < n; i++) {
    writeReg(pattern[i][0], pattern[i][1]);
    uint8_t got = readReg(pattern[i][0]);
    if (got != pattern[i][1]) {
      if (firstIdx < 0) { firstIdx = i; firstGot = got; }
      if (got != 0xFF) allFF = 0;
      if (got != firstGot) sameByte = 0;
      bad++;
    }
  }
  char d[120];
  if (!bad) {
    snprintf(d, sizeof d, "%d register writes read back correctly (FREQ set to %.3f MHz)", n, RF_FREQ_HZ / 1e6);
    return report(stage, true, d);
  }
  snprintf(d, sizeof d, "%d of %d mismatched; first: reg 0x%02X wrote 0x%02X, read 0x%02X",
           bad, n, pattern[firstIdx][0], pattern[firstIdx][1], firstGot);
  if (allFF) return report(stage, false, d, "every read returned 0xFF: chip not answering; fix stages 2-3 first");
  if (sameByte) return report(stage, false, d, "every read returned the same byte: chip not receiving commands; check MOSI (GPIO23)");
  return report(stage, false, d, "intermittent bit errors: check MOSI and SCK, shorten leads, keep the sniffer seated");
}

uint8_t configureRx() {
  for (auto &r : MODEM_CONFIG) writeReg(r[0], r[1]);
  uint32_t fw = freqWord(RF_FREQ_HZ);
  writeReg(FREQ2, fw >> 16); writeReg(FREQ1, fw >> 8); writeReg(FREQ0, fw);
  strobe(SIDLE); strobe(SCAL);
  uint32_t t0 = millis();
  while ((readStatus(MARCSTATE) & 0x1F) != MARC_IDLE && millis() - t0 < 20) {}
  strobe(SFRX); strobe(SRX);
  t0 = millis();
  uint8_t st = readStatus(MARCSTATE) & 0x1F;
  while (st != MARC_RX && millis() - t0 < 20) st = readStatus(MARCSTATE) & 0x1F;
  return st;
}

// ---------------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println("\nSemaeopus CYD bring-up 06: CC1101 on the microSD slot (Arduino)\n");

  // 1. LED self-test
  pinMode(PIN_LED_R, OUTPUT); pinMode(PIN_LED_G, OUTPUT); pinMode(PIN_LED_B, OUTPUT);
  for (char c : {'r', 'g', 'b'}) { led(c); delay(250); }
  led(0);
  report("1 LED self-test", true, "RGB LED should have stepped red, green, blue");

  // 2. Chip ready, before SPI owns the pins
  pinMode(PIN_CS, OUTPUT); digitalWrite(PIN_CS, HIGH);
  pinMode(PIN_MISO, INPUT_PULLUP);
  delay(2);
  int idle = digitalRead(PIN_MISO);
  digitalWrite(PIN_CS, LOW);
  bool ready = false;
  uint32_t t0 = micros();
  while (micros() - t0 < 10000) if (!digitalRead(PIN_MISO)) { ready = true; break; }
  digitalWrite(PIN_CS, HIGH);
  if (!idle)
    report("2 Chip ready", false, "MISO is low even with CSN high",
           "remove any microSD card from the sniffer's socket", "MISO (sniffer DAT0) may be shorted to GND");
  else if (!ready)
    report("2 Chip ready", false, "MISO never went low after CSN low (no CHIP_RDYn)",
           "VCC to CN1 3.3V, GND to CN1 GND (3.3 V only, never 5 V)",
           "CSN to sniffer CD/DAT3 (GPIO5), MISO/SO to sniffer DAT0 (GPIO19)",
           "sniffer fully seated in the CYD's SD slot");
  else
    report("2 Chip ready", true, "CHIP_RDYn seen (power, GND, CSN and MISO look connected)");

  radioSpi.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);   // CS driven manually

  // 3-4. ID and read back at bring-up speed
  bool idOk = checkId("3 ID @ 1 MHz", BAUD_BRINGUP, false);
  checkReadback("4 Write / read back");

  // 5. GDO0 wire
  pinMode(PIN_GDO0, INPUT_PULLDOWN);
  writeReg(IOCFG0, GDO0_FORCE_LOW);  delayMicroseconds(50); int lo = digitalRead(PIN_GDO0);
  writeReg(IOCFG0, GDO0_FORCE_HIGH); delayMicroseconds(50); int hi = digitalRead(PIN_GDO0);
  writeReg(IOCFG0, GDO0_FORCE_LOW);
  if (lo == 0 && hi == 1) report("5 GDO0 wire", true, "GPIO27 followed GDO0 low then high");
  else {
    snprintf(detail, sizeof detail, "forced low read %d, forced high read %d", lo, hi);
    report("5 GDO0 wire", false, detail,
              "GDO0 to CN1 IO27; confirm your CN1 pin order on the silkscreen",
              "if your board has no IO27 on CN1, use IO22 and change PIN_GDO0");
  }

  // 6. Same checks at operating speed
  checkId("6a ID @ 5 MHz", BAUD_OPERATE, idOk);
  checkReadback("6b Write / read back @ 5 MHz");

  // 7. RX at 915 MHz
  if (idOk) {
    uint8_t st = configureRx();
    if (st == MARC_RX) {
      float sum = 0;
      for (int i = 0; i < 16; i++) { sum += rssiDbm(readStatus(RSSI)); delay(5); }
      snprintf(detail, sizeof detail, "in RX (MARCSTATE 0x0D), noise floor about %.0f dBm "
               "(expect roughly -100 to -110 with nothing transmitting)", sum / 16);
      rxOk = report("7 RX at 915 MHz", true, detail);
    } else {
      snprintf(detail, sizeof detail, "MARCSTATE 0x%02X, expected 0x0D (RX)", st);
      report("7 RX at 915 MHz", false, detail,
             "PLL did not lock: the module's crystal or RF section may be faulty",
             "confirm the module is a 868/915 MHz variant, not a 433 MHz one");
    }
  } else {
    report("7 RX at 915 MHz", false, "skipped because the chip ID check failed");
  }

  Serial.println();
  if (failCount) {
    Serial.printf("RESULT: %d stage(s) failed. Fix the FIRST failure above; later stages depend on it.\n", failCount);
    led('r');
  } else {
    Serial.println("RESULT: all stages PASS. The CC1101 is ready for the satellite firmware.");
    led('g');
  }
  if (rxOk) {
    Serial.println("\nLive RSSI at 915.000 MHz (reset the board to stop).");
    Serial.println("Key a 915 MHz source nearby and the bar should jump.\n");
    delay(1500);
  }
}

void loop() {
  if (!rxOk) { delay(1000); return; }
  static float peak = -200;
  led('b');
  float dbm = rssiDbm(readStatus(RSSI));
  if (dbm > peak) peak = dbm;
  int cells = constrain((int)((dbm + 110) / 2), 0, 40);   // -110 dBm .. -30 dBm
  char bar[41];
  for (int i = 0; i < 40; i++) bar[i] = i < cells ? '#' : ' ';
  bar[40] = 0;
  Serial.printf("%7.1f dBm |%s| peak %.1f\n", dbm, bar, peak);
  delay(250);
}
