"""
Decoder facade: takes a frame off the link, runs `space_packet.decode`,
and produces a friendly dict for the UI.
"""

import struct

# Re-export the protocol module so callers don't need their own import.
from protocol import space_packet as sp


APID_NAME = {
    sp.APID_BEACON:       "BEACON",
    sp.APID_HK_TLM:       "HK_TLM",
    sp.APID_ADCS_TLM:     "ADCS_TLM",
    sp.APID_EPS_TLM:      "EPS_TLM",
    sp.APID_EVENT:        "EVENT",
    sp.APID_PAYLOAD_DATA: "PAYLOAD_DATA",
    sp.APID_PING:         "PING",
    sp.APID_PONG:         "PONG",
    sp.APID_REQ_TLM:      "REQ_TLM",
    sp.APID_SET_MODE:     "SET_MODE",
    sp.APID_ARM_PAYLOAD:  "ARM_PAYLOAD",
    sp.APID_FIRE_PAYLOAD: "FIRE_PAYLOAD",
    sp.APID_UPLOAD_TLE:   "UPLOAD_TLE",
    sp.APID_TIME_SET:     "TIME_SET",
    sp.APID_KEY_ROTATE:   "KEY_ROTATE",
    sp.APID_FORCE_SAFE:   "FORCE_SAFE",
}


def pretty_telemetry(apid, user_data):
    if apid == sp.APID_BEACON:
        try:
            return user_data.decode("ascii", "replace")
        except Exception:
            return user_data.hex()
    if apid == sp.APID_HK_TLM and len(user_data) >= 14:
        uptime, boot, t_q8, p_hpa, h_q8, mode, flags = \
            struct.unpack(">IHhHHBB", user_data[:14])
        return ("up=%ds boot=%d T=%.2f°C P=%dhPa RH=%.1f%% mode=%d flg=0x%02x"
                % (uptime // 1000, boot, t_q8 / 256.0, p_hpa, h_q8 / 256.0, mode, flags))
    if apid == sp.APID_EPS_TLM and len(user_data) >= 10:
        vbat, ibat, vbus, ibus, soc, day = struct.unpack(">HhHHBB", user_data[:10])
        return ("Vbus=%dmV I=%dmA SoC=%d%% %s"
                % (vbus, ibus, soc, "DAY" if day else "ECL"))
    if apid == sp.APID_ADCS_TLM and len(user_data) >= 12:
        gx, gy, gz = struct.unpack(">hhh", user_data[:6])
        return "ω=(%.1f, %.1f, %.1f) dps" % (gx / 256.0, gy / 256.0, gz / 256.0)
    return user_data.hex()


def decode_rx(rx, security_level=0, key=None, last_nonce=None):
    """Return a dict ready for display, or None on hard parse error."""
    try:
        d = sp.decode(rx["frame"], security_level=security_level,
                      key=key, last_seen_nonce=last_nonce)
    except sp.DecodeError as e:
        return {"error": str(e), "frame": rx["frame"].hex(),
                "rssi": rx["rssi"], "lqi": rx["lqi"]}
    return {
        "ts":        rx["ts"],
        "rssi":      rx["rssi"],
        "lqi":       rx["lqi"],
        "type":      "TM" if d["type"] == sp.TYPE_TM else "TC",
        "apid":      d["apid"],
        "apid_name": APID_NAME.get(d["apid"], "0x%03x" % d["apid"]),
        "seq":       d["seq_count"],
        "auth_ok":   d["auth_ok"],
        "replay_ok": d["replay_ok"],
        "nonce":     d["nonce"].hex() if d["nonce"] else None,
        "pretty":    pretty_telemetry(d["apid"], d["user_data"]),
        "raw":       d["user_data"].hex(),
    }
