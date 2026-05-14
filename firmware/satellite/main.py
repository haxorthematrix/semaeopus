"""
Satellite main entry point.

Wires up the radio, sensors, OBC subsystems and scheduler, then loops
forever dispatching periodic tasks and servicing the CC1101 RX FIFO.

Boot order intentionally matches a real CubeSat:
  1. self-test + boot counter increment
  2. bring up power telemetry FIRST so we can decide whether to enter
     SAFE on low SoC
  3. bring up time, environment, attitude
  4. configure comms, listen
  5. enter main loop
"""

from machine import Pin, I2C
import time
import os

import config
from lib import cc1101, ssd1306, bme280, mpu6050, ina219, ds3231
from obc.scheduler   import Scheduler
from obc.modes       import ModeState
from obc.housekeeping import Housekeeping
from obc.adcs        import ADCS
from obc.eps         import EPS
from comms.beacon    import Beacon
from comms.handlers  import dispatch
from protocol import space_packet as sp


# ---------------------------------------------------------------------------
# Boot-counter (persisted in flash file)
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
# State holder — passed to handlers so they can mutate subsystems.
# ---------------------------------------------------------------------------

class State:
    pass

state = State()
state.callsign     = config.CALLSIGN
state.boot_count   = next_boot_count()
state.mode         = ModeState(config.START_MODE)
state.tx_seq       = 0
state.rx_last_nonce = b"\x00" * sp.NONCE_LEN
state.session_key  = config.SHARED_KEY
state.security     = config.SECURITY_LEVEL


# ---------------------------------------------------------------------------
# Peripheral bring-up
# ---------------------------------------------------------------------------

i2c0 = I2C(0, sda=Pin(config.I2C0_SDA), scl=Pin(config.I2C0_SCL), freq=400_000)
i2c1 = I2C(1, sda=Pin(config.I2C1_SDA), scl=Pin(config.I2C1_SCL), freq=400_000)

led_rx = Pin(config.PIN_LED_RX, Pin.OUT, value=0)
led_tx = Pin(config.PIN_LED_TX, Pin.OUT, value=0)

oled  = ssd1306.SSD1306_I2C(128, 64, i2c0, addr=0x3C)
bme   = bme280.BME280(i2c0, addr=0x76)
mpu   = mpu6050.MPU6050(i2c0, addr=0x68)
ina   = ina219.INA219(i2c0, addr=0x40)
rtc   = ds3231.DS3231(i2c1, addr=0x68)

state.bme = bme
state.mpu = mpu
state.ina = ina
state.rtc = rtc

state.eps          = EPS(ina)
state.adcs         = ADCS(mpu)
state.housekeeping = Housekeeping(bme, state.mode, state.boot_count)
state.beacon       = Beacon(state)

radio = cc1101.make_default(config)
radio.listen()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _next_nonce():
    """64-bit monotonic; persists across boots via boot_count high bits."""
    state.tx_seq = (state.tx_seq + 1) & 0xFFFFFFFF
    high = state.boot_count & 0xFFFFFFFF
    return high.to_bytes(4, "big") + state.tx_seq.to_bytes(4, "big")


def transmit(apid, payload):
    nonce = _next_nonce() if state.security > 0 else None
    key   = state.session_key if state.security > 0 else None
    frame = sp.encode(
        sp.TYPE_TM, apid, state.tx_seq & 0x3FFF, payload,
        security_level=state.security, key=key, nonce=nonce,
    )
    led_tx.value(1)
    radio.transmit(frame)
    led_tx.value(0)
    radio.listen()


def show_status():
    oled.fill(0)
    oled.text("Semaeopus", 0, 0)
    oled.text("M%d B%d" % (state.mode.current, state.boot_count), 0, 12)
    oled.text("SOC %d%%" % int(state.eps.soc), 0, 24)
    oled.text("TX#%d" % state.tx_seq, 0, 36)
    oled.show()


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

def task_status():
    show_status()


def task_rx():
    if not radio.packet_available():
        return
    frame, rssi, lqi = radio.read_packet()
    if frame is None:
        return
    led_rx.value(1)
    try:
        dec = sp.decode(
            frame,
            security_level=state.security,
            key=state.session_key if state.security > 0 else None,
            last_seen_nonce=state.rx_last_nonce if state.security >= sp.SEC_L2_HMAC_CTR else None,
        )
    except sp.DecodeError as e:
        led_rx.value(0)
        return

    # Security gate (L1+)
    if state.security >= sp.SEC_L1_HMAC and not dec["auth_ok"]:
        led_rx.value(0)
        return
    if state.security >= sp.SEC_L2_HMAC_CTR and not dec["replay_ok"]:
        led_rx.value(0)
        return
    if dec["nonce"] is not None:
        state.rx_last_nonce = dec["nonce"]

    # Only TCs are actioned
    if dec["type"] != sp.TYPE_TC:
        led_rx.value(0)
        return

    response = dispatch(state, dec["apid"], dec["user_data"])
    if response is not None:
        transmit(*response)
    led_rx.value(0)


sched = Scheduler()
sched.add(config.BEACON_PERIOD_MS,   task_beacon,  "beacon")
sched.add(config.HK_TLM_PERIOD_MS,   task_hk,      "hk")
sched.add(config.ADCS_TLM_PERIOD_MS, task_adcs,    "adcs")
sched.add(config.EPS_TLM_PERIOD_MS,  task_eps,     "eps")
sched.add(1000,                      task_status,  "oled")
sched.add(config.RX_POLL_PERIOD_MS,  task_rx,      "rx")


print("[boot] Semaeopus", state.callsign, "boot#", state.boot_count,
      "sec-level", state.security)

while True:
    sched.tick()
    time.sleep_ms(5)
