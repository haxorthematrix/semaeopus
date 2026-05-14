"""
TC (uplink) command dispatch.

Each handler takes (state, user_data) and returns an optional TM
response (apid, payload). The OBC main loop transmits the response if
present.
"""

import struct
from protocol import space_packet as sp


def _ok():
    return (sp.APID_EVENT, b"\x00OK")

def _err(msg):
    return (sp.APID_EVENT, b"\x01" + msg.encode())


def handle_ping(state, data):
    return (sp.APID_PONG, data[:8])  # echo at most 8 bytes


def handle_req_tlm(state, data):
    if not data:
        return _err("req_tlm: missing apid")
    target = data[0]
    if target == sp.APID_HK_TLM:
        return (sp.APID_HK_TLM, state.housekeeping.encode())
    if target == sp.APID_ADCS_TLM:
        return (sp.APID_ADCS_TLM, state.adcs.encode())
    if target == sp.APID_EPS_TLM:
        return (sp.APID_EPS_TLM, state.eps.encode())
    return _err("req_tlm: unknown apid")


def handle_set_mode(state, data):
    if not data:
        return _err("set_mode: missing mode byte")
    requested = data[0]
    if state.mode.request(requested):
        return _ok()
    return _err("set_mode: illegal transition")


def handle_arm_payload(state, data):
    return _ok() if state.mode.arm_payload() else _err("arm: bad mode")


def handle_fire_payload(state, data):
    if state.mode.fire_payload():
        # Return a synthetic 32-byte "image header" — payload data
        # transmission would follow in real life.
        return (sp.APID_PAYLOAD_DATA,
                b"IMG" + struct.pack(">I", state.boot_count) + b"\x00" * 25)
    return _err("fire: not armed")


def handle_force_safe(state, data):
    state.mode.request(state.mode.SAFE)
    return _ok()


def handle_time_set(state, data):
    if len(data) < 4:
        return _err("time_set: need u32 epoch")
    epoch = struct.unpack(">I", data[:4])[0]
    try:
        state.rtc.set_epoch(epoch)
    except Exception as e:
        return _err("time_set: rtc error")
    return _ok()


def handle_key_rotate(state, data):
    if len(data) != 16:
        return _err("key_rotate: need 16 bytes")
    state.session_key = bytes(data)
    return _ok()


DISPATCH = {
    sp.APID_PING:         handle_ping,
    sp.APID_REQ_TLM:      handle_req_tlm,
    sp.APID_SET_MODE:     handle_set_mode,
    sp.APID_ARM_PAYLOAD:  handle_arm_payload,
    sp.APID_FIRE_PAYLOAD: handle_fire_payload,
    sp.APID_FORCE_SAFE:   handle_force_safe,
    sp.APID_TIME_SET:     handle_time_set,
    sp.APID_KEY_ROTATE:   handle_key_rotate,
}


def dispatch(state, apid, user_data):
    fn = DISPATCH.get(apid)
    if fn is None:
        return _err("unknown apid")
    return fn(state, user_data)
