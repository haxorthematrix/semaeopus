"""
Semaeopus satellite: CYD (ESP32-2432S028R) build.

Same flight logic as firmware/satellite/main.py (mode state machine,
housekeeping, ADCS, EPS, beacon, TC dispatch, security levels L0-L3),
with the CYD's hardware in place of the breadboard sensors:

  CC1101 radio      microSD slot (VSPI) + CN1 IO27 for GDO0
  Screen            live status: mode, power, counters, recent commands
  RGB LED           blue = TX, green = TC accepted, red = TC rejected
  LDR               sun sensor feeding EPS telemetry
  BOOT button       press any time to tumble the satellite for 10 s

To stop the firmware (for example to get a REPL), press BOOT during the
first two seconds after reset, or press Ctrl-C in a serial terminal.
"""

from machine import Pin
import time
import sys

import config
from lib import cc1101
from lib import cyd_display as disp
from lib.cyd_sensors import LightSensor, PowerSensor, EnvSensor, ImuSensor, SoftRtc
from obc.scheduler import Scheduler
from obc.modes import ModeState
from obc.housekeeping import Housekeeping
from obc.adcs import ADCS
from obc.eps import EPS
from comms.beacon import Beacon
from comms.handlers import dispatch
from protocol import space_packet as sp


MODE_NAMES = {0: "NOMINAL", 1: "SAFE", 2: "PAYLOAD", 3: "IDLE"}
MODE_COLORS = {0: disp.GREEN, 1: disp.RED, 2: disp.AMBER, 3: disp.GREY}
TC_NAMES = {
    sp.APID_PING: "PING", sp.APID_REQ_TLM: "REQ_TLM", sp.APID_SET_MODE: "SET_MODE",
    sp.APID_ARM_PAYLOAD: "ARM", sp.APID_FIRE_PAYLOAD: "FIRE",
    sp.APID_FORCE_SAFE: "FORCE_SAFE", sp.APID_TIME_SET: "TIME_SET",
    sp.APID_KEY_ROTATE: "KEY_ROTATE", sp.APID_UPLOAD_TLE: "UPLOAD_TLE",
}


# ---------------------------------------------------------------------------
# LEDs (active low) and the early-stop window
# ---------------------------------------------------------------------------

led_r = Pin(config.PIN_LED_R, Pin.OUT, value=1)
led_g = Pin(config.PIN_LED_G, Pin.OUT, value=1)
led_b = Pin(config.PIN_LED_B, Pin.OUT, value=1)


def led(r=0, g=0, b=0):
    led_r.value(0 if r else 1)
    led_g.value(0 if g else 1)
    led_b.value(0 if b else 1)


boot_btn = Pin(config.PIN_BOOT_BTN, Pin.IN, Pin.PULL_UP)
print("[boot] press BOOT within 2 s to stop the satellite firmware")
led(r=1, g=1)                                   # amber while waiting
_t0 = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), _t0) < 2000:
    if boot_btn.value() == 0:
        led()
        print("[boot] stopped by BOOT button; REPL is available")
        sys.exit()
    time.sleep_ms(20)
led()


# ---------------------------------------------------------------------------
# Boot counter (persisted in flash)
# ---------------------------------------------------------------------------

BOOT_COUNT_FILE = "boot_count.txt"


def next_boot_count():
    try:
        with open(BOOT_COUNT_FILE) as f:
            n = int(f.read().strip())
    except (OSError, ValueError):
        n = 0
    n += 1
    try:
        with open(BOOT_COUNT_FILE, "w") as f:
            f.write(str(n))
    except OSError:
        pass
    return n


# ---------------------------------------------------------------------------
# State shared with the TC handlers
# ---------------------------------------------------------------------------

class State:
    pass


state = State()
state.callsign = config.CALLSIGN
state.boot_count = next_boot_count()
state.mode = ModeState(config.START_MODE)
state.tx_seq = 0
state.rx_last_nonce = b"\x00" * sp.NONCE_LEN
state.session_key = config.SHARED_KEY
state.security = config.SECURITY_LEVEL
state.tx_count = 0
state.tc_ok = 0
state.tc_rejected = 0
state.events = []          # newest last: (text, colour)


def log_event(text, color=disp.WHITE):
    print("[event]", text)
    state.events.append((text, color))
    if len(state.events) > 5:
        state.events.pop(0)


# ---------------------------------------------------------------------------
# Peripherals
# ---------------------------------------------------------------------------

screen = disp.Display(
    spi_id=config.TFT_SPI_ID, sck=config.PIN_TFT_SCK, mosi=config.PIN_TFT_MOSI,
    miso=config.PIN_TFT_MISO, cs=config.PIN_TFT_CS, dc=config.PIN_TFT_DC,
    bl=config.PIN_TFT_BL, madctl=config.DISPLAY_MADCTL, invert=config.DISPLAY_INVERT,
)

light = LightSensor(config.PIN_LDR, bright_is_low=config.LDR_BRIGHT_IS_LOW)
imu = ImuSensor(config.PIN_BOOT_BTN)

state.light = light
state.ina = PowerSensor(light)
state.bme = EnvSensor()
state.mpu = imu
state.rtc = SoftRtc()

state.eps = EPS(state.ina)
state.adcs = ADCS(imu)
state.housekeeping = Housekeeping(state.bme, state.mode, state.boot_count)
state.beacon = Beacon(state)

radio = cc1101.make_default(config)
radio.listen()


# ---------------------------------------------------------------------------
# Radio helpers
# ---------------------------------------------------------------------------

def _next_nonce():
    """64-bit monotonic: boot count in the high word, TX sequence in the low."""
    state.tx_seq = (state.tx_seq + 1) & 0xFFFFFFFF
    high = state.boot_count & 0xFFFFFFFF
    return high.to_bytes(4, "big") + state.tx_seq.to_bytes(4, "big")


def transmit(apid, payload):
    # radio.transmit() lets an arriving packet finish and keeps it for task_rx.
    nonce = _next_nonce() if state.security > 0 else None
    if nonce is None:
        state.tx_seq = (state.tx_seq + 1) & 0xFFFFFFFF
    key = state.session_key if state.security > 0 else None
    frame = sp.encode(
        sp.TYPE_TM, apid, state.tx_seq & 0x3FFF, payload,
        security_level=state.security, key=key, nonce=nonce,
    )
    led(b=1)
    radio.transmit(frame)
    led()
    radio.listen()
    state.tx_count += 1


def reject(reason):
    state.tc_rejected += 1
    log_event("REJECT " + reason, disp.RED)
    led(r=1)


# ---------------------------------------------------------------------------
# Scheduled tasks
# ---------------------------------------------------------------------------

def task_beacon():
    apid, payload = state.beacon.build()
    transmit(apid, payload)


def task_hk():
    transmit(sp.APID_HK_TLM, state.housekeeping.encode())


def task_adcs():
    transmit(sp.APID_ADCS_TLM, state.adcs.encode())


def task_eps():
    transmit(sp.APID_EPS_TLM, state.eps.encode())


def task_rx():
    if not radio.packet_available():
        return
    frame, rssi, lqi = radio.read_packet()
    if frame is None:
        return
    try:
        dec = sp.decode(
            frame,
            security_level=state.security,
            key=state.session_key if state.security > 0 else None,
            last_seen_nonce=state.rx_last_nonce if state.security >= sp.SEC_L2_HMAC_CTR else None,
        )
    except sp.DecodeError as e:
        reject("bad frame: %s" % e)
        led()
        return

    if dec["type"] != sp.TYPE_TC:               # our own TM echoed back, etc.
        return
    name = TC_NAMES.get(dec["apid"], "APID 0x%03X" % dec["apid"])

    # At L1+ an unauthenticated frame decodes with auth_ok = None, so it fails here too.
    if state.security >= sp.SEC_L1_HMAC and not dec["auth_ok"]:
        reject("%s: bad HMAC" % name)
        led()
        return
    if state.security >= sp.SEC_L2_HMAC_CTR and not dec["replay_ok"]:
        reject("%s: replayed nonce" % name)
        led()
        return
    if dec["nonce"] is not None:
        state.rx_last_nonce = dec["nonce"]

    led(g=1)
    before = state.mode.current
    response = dispatch(state, dec["apid"], dec["user_data"])
    state.tc_ok += 1
    if response is not None and response[0] == sp.APID_EVENT and response[1][:1] != b"\x00":
        log_event("TC %s: %s" % (name, response[1][1:].decode()), disp.AMBER)
    elif state.mode.current != before:
        log_event("TC %s: %s -> %s" % (name, MODE_NAMES.get(before, "?"),
                                       MODE_NAMES.get(state.mode.current, "?")), disp.GREEN)
    else:
        log_event("TC %s ok (%d dBm)" % (name, rssi), disp.GREEN)
    if response is not None:
        transmit(*response)
    led()


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------

def draw_static():
    screen.text(state.callsign, 8, 6, disp.CYAN, scale=2)
    screen.text("%.3f MHz  SEC L%d  BOOT %d" % (config.RF_FREQ_HZ / 1e6, state.security,
                                                 state.boot_count), 8, 28, disp.GREY)
    screen.text("MODE", 8, 48, disp.GREY)
    screen.text("POWER", 8, 92, disp.GREY)
    screen.text("SUN", 8, 112, disp.GREY)
    screen.text("RECENT COMMANDS", 8, 168, disp.GREY)


def task_screen():
    m = state.mode.current
    screen.text(MODE_NAMES.get(m, "?"), 8, 60, MODE_COLORS.get(m, disp.WHITE), scale=3, width=9)
    if imu.tumbling():
        screen.text("TUMBLING", 224, 66, disp.AMBER, width=8)
    else:
        screen.text("", 224, 66, width=8)
    soc = state.eps.soc
    screen.bar(56, 90, 180, 12, soc / 100, disp.GREEN if soc > 30 else disp.RED)
    screen.text("%3d%%" % int(soc), 244, 92, disp.WHITE, width=5)
    sun = light.level()
    screen.bar(56, 110, 180, 12, sun, disp.AMBER)
    screen.text("%3d%%" % int(sun * 100), 244, 112, disp.WHITE, width=5)
    up = time.ticks_ms() // 1000
    screen.text("TX %-5d TC %-4d REJ %-4d UP %02d:%02d:%02d" % (
        state.tx_count % 100000, state.tc_ok % 10000, state.tc_rejected % 10000,
        up // 3600 % 100, up // 60 % 60, up % 60), 8, 140, disp.WHITE, width=39)
    for i in range(5):
        if i < len(state.events):
            text, color = state.events[-1 - i]
        else:
            text, color = "", disp.WHITE
        screen.text(text, 8, 182 + i * 11, color, width=38)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

draw_static()
log_event("boot %d, listening at %.3f MHz" % (state.boot_count, config.RF_FREQ_HZ / 1e6), disp.CYAN)

sched = Scheduler()
sched.add(config.RX_POLL_PERIOD_MS, task_rx, "rx")          # first: service RX before any TX
sched.add(config.BEACON_PERIOD_MS, task_beacon, "beacon")
sched.add(config.HK_TLM_PERIOD_MS, task_hk, "hk")
sched.add(config.ADCS_TLM_PERIOD_MS, task_adcs, "adcs")
sched.add(config.EPS_TLM_PERIOD_MS, task_eps, "eps")
sched.add(config.SCREEN_PERIOD_MS, task_screen, "screen")

print("[boot] Semaeopus", state.callsign, "boot#", state.boot_count,
      "sec-level", state.security, "freq", config.RF_FREQ_HZ)

while True:
    sched.tick()
    time.sleep_ms(5)
