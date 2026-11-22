"""
Semaeopus operator ground station: CYD as a USB radio modem with a status screen.

The laptop runs the operator software and talks to this board over USB:
    python -m groundstation.operator.gs --port <CYD serial port> --freq 915000000

The modem speaks the same line protocol as the original gs_frontend, so
every operator and attacker tool works unchanged. The screen shows link
activity and decodes the header of each packet it hears.

Opening the serial port resets the CYD (its USB adapter's auto-reset
lines); the board is ready again in about two seconds.
"""

from machine import Pin, SPI

import config
from lib import cc1101
from lib import cyd_display as disp
from lib.modem import Modem

APID_NAMES = {
    0x001: "BEACON", 0x010: "HK_TLM", 0x011: "ADCS_TLM", 0x012: "EPS_TLM",
    0x020: "EVENT", 0x030: "PAYLOAD", 0x080: "PING", 0x081: "PONG",
    0x082: "REQ_TLM", 0x083: "SET_MODE", 0x084: "ARM", 0x085: "FIRE",
    0x086: "UPLOAD_TLE", 0x087: "TIME_SET", 0x088: "KEY_ROTATE", 0x0FF: "FORCE_SAFE",
}

led_r = Pin(config.PIN_LED_R, Pin.OUT, value=1)
led_g = Pin(config.PIN_LED_G, Pin.OUT, value=1)
led_b = Pin(config.PIN_LED_B, Pin.OUT, value=1)


def leds(r=0, g=0, b=0):
    led_r.value(0 if r else 1)
    led_g.value(0 if g else 1)
    led_b.value(0 if b else 1)


screen = disp.Display(
    spi_id=config.TFT_SPI_ID, sck=config.PIN_TFT_SCK, mosi=config.PIN_TFT_MOSI,
    miso=config.PIN_TFT_MISO, cs=config.PIN_TFT_CS, dc=config.PIN_TFT_DC,
    bl=config.PIN_TFT_BL, madctl=config.DISPLAY_MADCTL, invert=config.DISPLAY_INVERT,
)

status = {"last": None, "rssi": 0, "lqi": 0, "event": "waiting for host", "dirty": True}


def describe(frame):
    """Header-only decode: works at every security level without the key."""
    if len(frame) < 7:
        return "short frame", ""
    w0 = (frame[1] << 8) | frame[2]
    is_tc = (w0 >> 12) & 1
    secured = (w0 >> 11) & 1
    apid = w0 & 0x7FF
    name = APID_NAMES.get(apid, "APID 0x%03X" % apid)
    head = "%s %s%s" % ("TC" if is_tc else "TM", name, " [auth]" if secured else "")
    body = frame[7:-2]
    if secured:
        body = body[16:]                     # skip nonce + HMAC tag
    printable = len(body) > 0 and all(32 <= b < 127 for b in body)
    if apid == 0x001:                        # beacon: show its text unless encrypted (L3)
        detail = body.decode() if printable else "(encrypted)"
    else:
        detail = body[:16].hex()
    return head, detail


def on_rx(frame, rssi, lqi):
    status["last"] = describe(frame)
    status["rssi"], status["lqi"] = rssi, lqi
    status["dirty"] = True
    leds(g=1)


def on_tx(frame):
    status["event"] = "sent %s" % describe(frame)[0]
    status["dirty"] = True
    leds(b=1)


def on_event(text):
    status["event"] = text
    status["dirty"] = True


def draw_static():
    screen.text("GROUND STATION", 8, 6, disp.CYAN, scale=2)
    screen.text("LAST PACKET HEARD", 8, 100, disp.GREY)
    screen.text("HOST", 8, 190, disp.GREY)


def refresh():
    leds()
    m = modem
    screen.text("%.3f MHz  BW %d kHz  %d dBm" % (m.freq_hz / 1e6, m.bw_hz // 1000, m.power_dbm),
                8, 28, disp.GREY, width=38)
    screen.text("RX %-6d TX %-6d" % (m.rx_count % 1000000, m.tx_count % 1000000),
                8, 48, disp.WHITE, scale=2, width=18)
    if status["last"]:
        screen.text("RSSI %d dBm  LQI %d" % (status["rssi"], status["lqi"]), 8, 74, disp.WHITE, width=38)
    if not status["dirty"]:
        return
    status["dirty"] = False
    if status["last"]:
        head, detail = status["last"]
        screen.text(head, 8, 114, disp.GREEN, scale=2, width=19)
        screen.text(detail[:38], 8, 138, disp.WHITE, width=38)
        screen.text(detail[38:76], 8, 150, disp.WHITE, width=38)
    screen.text(status["event"][:38], 8, 204, disp.AMBER, width=38)


c = config
spi = SPI(c.CC1101_SPI_ID, baudrate=c.SPI_BAUD, polarity=0, phase=0,
          sck=Pin(c.PIN_SPI_SCK), mosi=Pin(c.PIN_SPI_MOSI), miso=Pin(c.PIN_SPI_MISO))
radio = cc1101.CC1101(spi, c.PIN_CC1101_CS, c.PIN_CC1101_GDO0)

draw_static()
modem = Modem(radio, c.RF_FREQ_HZ, tx_power_dbm=c.RF_TX_POWER_DBM, name="ground",
              on_rx=on_rx, on_tx=on_tx, on_event=on_event)
refresh()
modem.run(idle_hook=refresh, hook_period_ms=250)
