"""
Virtual satellite.

Reuses every OBC module from firmware/satellite/obc and the comms
handlers/beacon directly — no duplication. The only swaps are:
  - sensors → sim.fakes.FakeBME280/MPU6050/INA219/DS3231/FakeOLED
  - radio   → sim.radio_bus.RadioNode (UDP)
  - time    → handled inside obc.compat

This means the simulator and the flight build run the *same logic*.

Run:
    python -m sim.virtual_satellite

Then in another shell:
    python -m groundstation.operator.gs --sim
"""

import argparse
import os
import sys
import time

# Make firmware modules importable as top-level packages.
# Order matters: project ROOT must come BEFORE firmware/satellite so the
# real protocol/space_packet.py wins over the placeholder package under
# firmware/satellite/protocol/.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware", "satellite"))
sys.path.insert(0, ROOT)

from obc.scheduler    import Scheduler          # noqa: E402
from obc.modes        import ModeState          # noqa: E402
from obc.housekeeping import Housekeeping       # noqa: E402
from obc.adcs         import ADCS               # noqa: E402
from obc.eps          import EPS                # noqa: E402
from comms.beacon     import Beacon             # noqa: E402
from comms.handlers   import dispatch           # noqa: E402
from protocol import space_packet as sp         # noqa: E402

from sim.fakes        import (                  # noqa: E402
    FakeBME280, FakeMPU6050, FakeINA219, FakeDS3231, FakeOLED,
)
from sim.radio_bus    import RadioNode          # noqa: E402


class State:
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--callsign", default="SEMAEOPUS-SIM")
    ap.add_argument("--security", type=int, default=0, choices=[0, 1, 2, 3])
    ap.add_argument("--key", default="53656d61656f707573_4b65795f763031".replace("_", ""),
                    help="16-byte hex key for sec>=1")
    ap.add_argument("--node-id", default="SAT0")
    ap.add_argument("--tx-power", type=int, default=10)
    ap.add_argument("--mode", type=int, default=ModeState.NOMINAL)
    args = ap.parse_args()

    state = State()
    state.callsign     = args.callsign
    state.boot_count   = 1
    state.mode         = ModeState(args.mode)
    state.tx_seq       = 0
    state.rx_last_nonce = b"\x00" * sp.NONCE_LEN
    state.session_key  = bytes.fromhex(args.key)
    state.security     = args.security

    state.bme = FakeBME280()
    state.mpu = FakeMPU6050()
    state.ina = FakeINA219()
    state.rtc = FakeDS3231()
    state.oled = FakeOLED()

    state.eps          = EPS(state.ina)
    state.adcs         = ADCS(state.mpu)
    state.housekeeping = Housekeeping(state.bme, state.mode, state.boot_count)
    state.beacon       = Beacon(state)

    radio = RadioNode(args.node_id, tx_power_dbm=args.tx_power)
    radio.listen()

    def next_nonce():
        state.tx_seq = (state.tx_seq + 1) & 0xFFFFFFFF
        high = state.boot_count & 0xFFFFFFFF
        return high.to_bytes(4, "big") + state.tx_seq.to_bytes(4, "big")

    def transmit(apid, payload):
        nonce = next_nonce() if state.security > 0 else None
        key   = state.session_key if state.security > 0 else None
        frame = sp.encode(
            sp.TYPE_TM, apid, state.tx_seq & 0x3FFF, payload,
            security_level=state.security, key=key, nonce=nonce,
        )
        radio.transmit(frame)

    def task_beacon():
        apid, payload = state.beacon.build()
        transmit(apid, payload)
        print("[sat] BEACON tx#%d  M%d  SOC%d" % (state.tx_seq, state.mode.current, int(state.eps.soc)))

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
            print("[sat] rx bad:", e)
            return

        if state.security >= sp.SEC_L1_HMAC and not dec["auth_ok"]:
            print("[sat] rx auth FAIL apid=0x%03x" % dec["apid"])
            return
        if state.security >= sp.SEC_L2_HMAC_CTR and not dec["replay_ok"]:
            print("[sat] rx replay rejected apid=0x%03x" % dec["apid"])
            return
        if dec["nonce"] is not None:
            state.rx_last_nonce = dec["nonce"]
        if dec["type"] != sp.TYPE_TC:
            return

        print("[sat] TC apid=0x%03x seq=%d rssi=%d" % (dec["apid"], dec["seq_count"], rssi))
        response = dispatch(state, dec["apid"], dec["user_data"])
        if response is not None:
            transmit(*response)

    sched = Scheduler()
    sched.add(10_000, task_beacon, "beacon")
    sched.add( 5_000, task_hk,     "hk")
    sched.add( 2_000, task_adcs,   "adcs")
    sched.add( 5_000, task_eps,    "eps")
    sched.add(    20, task_rx,     "rx")

    # Force one immediate beacon at startup so an attached GS sees life
    # within seconds.
    task_beacon()

    print("[sat] virtual satellite '%s' up, sec=%d, key=%s" % (
        args.callsign, args.security, state.session_key.hex()))
    try:
        while True:
            sched.tick()
            time.sleep(0.005)
    except KeyboardInterrupt:
        print("\n[sat] shutdown")


if __name__ == "__main__":
    main()
