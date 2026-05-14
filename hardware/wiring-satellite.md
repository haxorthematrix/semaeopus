# Satellite Wiring

All voltages on the satellite are 3V3. **The CC1101 is not 5 V tolerant
on any pin** — driving it from a 5 V MCU will destroy it. The Pi Pico
is natively 3V3, so we're safe; double-check if you substitute a
different MCU.

## Pi Pico pin map

```
                  ┌─────── USB ───────┐
              GP0 │ 1               40│ VBUS         (5 V from USB — unused)
              GP1 │ 2               39│ VSYS         (1.8–5.5 V battery in)
              GND │ 3               38│ GND
              GP2 │ 4               37│ 3V3 EN
   SDA0 ◀── GP4   │ 6               36│ 3V3 OUT  ──▶ to all 3V3 rails
   SCL0 ◀── GP5   │ 7               35│ ADC_VREF
              GND │ 8               33│ GND
   MISO ◀── GP12  │16               25│ GP19  ─▶ MOSI    (CC1101 SI)
   CSn  ◀── GP13  │17               24│ GP18  ─▶ SCK     (CC1101 SCK)
              GP14│19               22│ GP17  ─▶ TX-LED
              GP15│20               21│ GP16  ─▶ RX-LED
   GDO0  ◀── GP10 │14               26│ GP20  ─▶ SDA1   (DS3231)
                                    27│ GP21  ─▶ SCL1   (DS3231)
                  └───────────────────┘

   SPI0:    SCK=GP18  MOSI=GP19  MISO=GP16↦GP12  CS=GP13  (we use GP12 for MISO via SPI0 RX)
   I²C0:    SDA=GP4   SCL=GP5     ← SSD1306, BME280, MPU6050, INA219
   I²C1:    SDA=GP20  SCL=GP21    ← DS3231 (separate bus avoids 0x68 collision)
   CC1101:  GDO0=GP10 (RX'd-packet interrupt)
```

> The pin assignments above are *chosen for the wiring diagram below*.
> The firmware reads them all from `config.py`, so feel free to
> rearrange — just keep SPI on SPI0 pins and I²C on I²C0/I²C1 pins.

## CC1101 pinout

Generic 8-pin "E07-style" module, looking at the pin side:

```
   ┌──────────────┐
   │ GND   VCC    │  VCC = 3V3
   │ SCK   MOSI   │
   │ MISO  GDO2   │  GDO2 unused
   │ GDO0  CSN    │
   └──────────────┘
```

Connections to Pi Pico:

| CC1101 | Pi Pico        | Notes                                  |
|--------|----------------|----------------------------------------|
| VCC    | 3V3 OUT (36)   | **Never 5 V**                          |
| GND    | GND            | Any GND pin                            |
| CSN    | GP13           | SPI chip-select, active-low            |
| SCK    | GP18           | SPI clock                              |
| MOSI   | GP19           | SPI MOSI                               |
| MISO   | GP12           | SPI MISO                               |
| GDO0   | GP10           | Packet-end interrupt input             |
| GDO2   | (unused)       | Leave floating                         |

## I²C bus 0 — sensors + display

All four devices share SDA=GP4 / SCL=GP5, plus 3V3 and GND.

| Device   | Addr | SDA  | SCL  | VCC  | GND |
|----------|------|------|------|------|-----|
| SSD1306  | 0x3C | GP4  | GP5  | 3V3  | GND |
| BME280   | 0x76 | GP4  | GP5  | 3V3  | GND |
| MPU6050  | 0x68 | GP4  | GP5  | 3V3  | GND |
| INA219   | 0x40 | GP4  | GP5  | 3V3  | GND |

The SSD1306, BME280, and MPU6050 all have on-board pull-ups, so no
external resistors are needed. The INA219 typically does too — if you
see flaky reads, add 4.7 kΩ pull-ups from SDA and SCL to 3V3.

## I²C bus 1 — RTC

| Device   | Addr | SDA  | SCL  | VCC  | GND |
|----------|------|------|------|------|-----|
| DS3231   | 0x68 | GP20 | GP21 | 3V3  | GND |

## LEDs

```
   3V3 OUT ──┬── 220 Ω ──[RED LED  TX]── GP17  (sinks: GP17 LOW = ON)
             └── 220 Ω ──[GRN LED  RX]── GP16
```

(Equally valid: GPIO → resistor → LED anode → cathode → GND, with
GPIO HIGH = ON. Match the convention in `firmware/satellite/config.py`.)

## Antenna

For 433 MHz, a single piece of 22 AWG solid-core wire **170 mm long**
soldered or screwed onto the CC1101's ANT pad / SMA pigtail is the full
¼-wave. For 915 MHz, use **82 mm**. Keep the wire vertical and at least
5 cm clear of the breadboard for sensible RF.

## Power

For bench operation, USB to the Pico (5 V → on-board buck to 3V3) is
fine for the whole rail. The Pico's 3V3 reg is good for ~300 mA, more
than enough for everything on the BOM (CC1101 peaks ~35 mA in TX, OLED
~20 mA, sensors all sub-mA).

## ASCII breadboard view

```
                                          ┌──────────────────────────────────┐
                                          │              Pi Pico             │
                                          │                                  │
   ┌────────┐                              ├──┐                          ┌──┤
   │ CC1101 │── VCC ─────────── 3V3 ───────│36│                          │ 1│ GP0
   │        │── GND ─────────── GND ───────│38│                          │ 2│ GP1
   │        │── CSN ─── GP13 ──────────────│17│                          │ 3│ GND
   │        │── SCK ─── GP18 ──────────────│24│                          │ 4│ GP2
   │        │── MOSI ── GP19 ──────────────│25│                          │ 5│ GP3
   │        │── MISO ── GP12 ──────────────│16│                          │ 6│ GP4 ─── SDA0 ─── bus
   │        │── GDO0 ── GP10 ──────────────│14│                          │ 7│ GP5 ─── SCL0 ─── bus
   │   ANT  │── (whip 170 mm)              │  │                          │ 8│ GND
   └────────┘                              │  │                          │  │
                                           │  │                          │21│ GP16 ── (220Ω) ── RX LED ── GND
                                           │  │                          │22│ GP17 ── (220Ω) ── TX LED ── GND
   ┌──────────┐                            │  │                          │26│ GP20 ─── SDA1
   │ SSD1306  │── VCC ─── 3V3              │  │                          │27│ GP21 ─── SCL1
   │ 0x3C     │── GND ─── GND              │  │                          └──┤
   │          │── SDA ─── SDA0 (GP4)       │  │
   │          │── SCL ─── SCL0 (GP5)       │  │
   └──────────┘                            │  │
                                           │  │
   ┌──────────┐                            │  │
   │ BME280   │── VCC ─── 3V3              │  │
   │ 0x76     │── GND ─── GND              │  │
   │          │── SDA ─── SDA0 (GP4)       │  │
   │          │── SCL ─── SCL0 (GP5)       │  │
   └──────────┘                            │  │
                                           │  │
   ┌──────────┐                            │  │
   │ MPU6050  │── VCC ─── 3V3              │  │
   │ 0x68     │── GND ─── GND              │  │
   │          │── SDA ─── SDA0 (GP4)       │  │
   │          │── SCL ─── SCL0 (GP5)       │  │
   └──────────┘                            │  │
                                           │  │
   ┌──────────┐                            │  │
   │ INA219   │── VCC ─── 3V3              │  │
   │ 0x40     │── GND ─── GND              │  │
   │          │── SDA ─── SDA0 (GP4)       │  │
   │          │── SCL ─── SCL0 (GP5)       │  │
   │          │ Vin+/Vin− across "battery" load (any 0.1 Ω–10 Ω resistor) │
   └──────────┘                            │  │
                                           │  │
   ┌──────────┐                            │  │
   │ DS3231   │── VCC ─── 3V3              │  │
   │ 0x68     │── GND ─── GND              │  │
   │          │── SDA ─── SDA1 (GP20)      │  │
   │          │── SCL ─── SCL1 (GP21)      │  │
   └──────────┘                            └──┘
```

All five I²C breakouts (SSD1306, BME280, MPU6050, INA219, DS3231) sit
along the same two power rails on the breadboard. Bring a single 3V3
rail across the top, a single GND rail across the bottom, and drop the
two I²C buses across the middle. Final layout in `docs/photo_build.png`
once the prototype is photographed.
