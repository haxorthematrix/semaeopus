"""
Semaeopus CCSDS-lite Space Packet codec.

Shared between the satellite firmware (under MicroPython), the operator
ground station, and the attacker tooling. Keep this file
MicroPython-compatible: standard-library `struct`, `hashlib`, and
optionally `os.urandom`. No f-strings of dynamic widths, no `typing`
imports.

Frame layout
------------

    [ Preamble + Sync handled by CC1101 PHY ]
    [ LEN byte ][ Space Packet ][ CRC16-CCITT ]

Space Packet primary header (48 b):

      bit  0       3 4  5 6        16 17     18 19           32 33           48
          +--------+--+--+----------+--------+----------------+----------------+
          |Version |TY|SH|  APID    | SeqFlg |  SeqCount(14b) |  PktDataLen-1  |
          | 0b000  |  |  | (11 bit) |  0b11  |                |                |
          +--------+--+--+----------+--------+----------------+----------------+

If SH (secondary-header flag) is 1, an 8-byte nonce + 8-byte HMAC tag
precede the user data (security level >= 1). At security level >= 3 the
user data is AES-128-CTR encrypted with the nonce as the IV.

CRC: CRC-16-CCITT (poly 0x1021, init 0xFFFF, no reflect, no xorout)
     computed over the entire space packet (primary header + secondary
     header if any + user data).
"""

import struct
import hashlib

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TYPE_TM = 0
TYPE_TC = 1

# Application Process IDs — see specification.md §4.4
APID_BEACON       = 0x001
APID_HK_TLM       = 0x010
APID_ADCS_TLM     = 0x011
APID_EPS_TLM      = 0x012
APID_EVENT        = 0x020
APID_PAYLOAD_DATA = 0x030
APID_PING         = 0x080
APID_PONG         = 0x081
APID_REQ_TLM      = 0x082
APID_SET_MODE     = 0x083
APID_ARM_PAYLOAD  = 0x084
APID_FIRE_PAYLOAD = 0x085
APID_UPLOAD_TLE   = 0x086
APID_TIME_SET     = 0x087
APID_KEY_ROTATE   = 0x088
APID_FORCE_SAFE   = 0x0FF

SEC_L0_NONE       = 0   # plaintext, no auth
SEC_L1_HMAC       = 1   # HMAC-truncated, no counter binding
SEC_L2_HMAC_CTR   = 2   # HMAC over (nonce || packet); strict monotonic nonce
SEC_L3_AES_HMAC   = 3   # AES-128-CTR + HMAC

NONCE_LEN = 8
TAG_LEN   = 8

# ---------------------------------------------------------------------------
# CRC-16-CCITT
# ---------------------------------------------------------------------------

def crc16_ccitt(data):
    """CRC-16-CCITT (poly=0x1021, init=0xFFFF). Returns 16-bit int."""
    crc = 0xFFFF
    for b in data:
        crc ^= (b << 8) & 0xFFFF
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


# ---------------------------------------------------------------------------
# Primary header encode / decode
# ---------------------------------------------------------------------------

def _pack_primary(pkt_type, sh_flag, apid, seq_count, payload_len):
    """Return 6-byte primary header."""
    # Word 0: version(3)|type(1)|sh(1)|apid(11)
    w0 = ((0 & 0x7) << 13) | ((pkt_type & 1) << 12) | ((sh_flag & 1) << 11) | (apid & 0x7FF)
    # Word 1: seq_flags(2)|seq_count(14)
    w1 = (0b11 << 14) | (seq_count & 0x3FFF)
    # Word 2: payload_len - 1 (CCSDS quirk)
    w2 = (payload_len - 1) & 0xFFFF
    return struct.pack(">HHH", w0, w1, w2)


def _unpack_primary(buf):
    w0, w1, w2 = struct.unpack(">HHH", buf[:6])
    version    = (w0 >> 13) & 0x7
    pkt_type   = (w0 >> 12) & 0x1
    sh_flag    = (w0 >> 11) & 0x1
    apid       =  w0        & 0x7FF
    seq_flags  = (w1 >> 14) & 0x3
    seq_count  =  w1        & 0x3FFF
    payload_len = w2 + 1
    return {
        "version":    version,
        "type":       pkt_type,
        "sh":         sh_flag,
        "apid":       apid,
        "seq_flags":  seq_flags,
        "seq_count":  seq_count,
        "payload_len": payload_len,
    }


# ---------------------------------------------------------------------------
# Security helpers (HMAC-SHA256 truncated; AES via PyCryptodome on host,
# `ucryptolib` on MicroPython)
# ---------------------------------------------------------------------------

def hmac_sha256(key, msg):
    """HMAC-SHA256. MicroPython hashlib lacks hmac, so implement here."""
    block = 64
    if len(key) > block:
        key = hashlib.sha256(key).digest()
    key = key + b"\x00" * (block - len(key))
    o_pad = bytes((b ^ 0x5C) for b in key)
    i_pad = bytes((b ^ 0x36) for b in key)
    inner = hashlib.sha256(i_pad + msg).digest()
    return hashlib.sha256(o_pad + inner).digest()


def _aes_ctr(key, nonce8, data):
    """AES-128-CTR. nonce8 is 8 bytes; counter is 8 bytes starting at 0."""
    try:
        # MicroPython: ucryptolib.aes mode 6 = CTR (where available)
        import ucryptolib
        iv = nonce8 + b"\x00" * 8
        cipher = ucryptolib.aes(key, 6, iv)
        return cipher.encrypt(data)
    except ImportError:
        from Crypto.Cipher import AES
        from Crypto.Util import Counter
        ctr = Counter.new(64, prefix=nonce8, initial_value=0)
        return AES.new(key, AES.MODE_CTR, counter=ctr).encrypt(data)


# ---------------------------------------------------------------------------
# Encode
# ---------------------------------------------------------------------------

def encode(pkt_type, apid, seq_count, user_data,
           security_level=SEC_L0_NONE, key=None, nonce=None):
    """
    Build a complete on-wire frame: [LEN][space packet][CRC16].

    Returns: bytes ready to push into the CC1101 TX FIFO.
    """
    if security_level == SEC_L0_NONE:
        sh_flag = 0
        secondary = b""
        body = user_data
    else:
        if key is None:
            raise ValueError("security_level > 0 requires key")
        if nonce is None:
            raise ValueError("security_level > 0 requires nonce")
        if len(nonce) != NONCE_LEN:
            raise ValueError("nonce must be 8 bytes")
        sh_flag = 1

        if security_level == SEC_L3_AES_HMAC:
            body = _aes_ctr(key, nonce, user_data)
        else:
            body = user_data

        # MAC input depends on level — by design, L1 omits the nonce so the
        # learner can later spot why replay still works.
        if security_level == SEC_L1_HMAC:
            mac_input = body
        else:
            mac_input = nonce + body
        tag = hmac_sha256(key, mac_input)[:TAG_LEN]
        secondary = nonce + tag

    payload = secondary + body
    primary = _pack_primary(pkt_type, sh_flag, apid, seq_count, len(payload))
    space_packet = primary + payload
    crc = crc16_ccitt(space_packet)
    framed = space_packet + struct.pack(">H", crc)
    return bytes([len(framed)]) + framed


# ---------------------------------------------------------------------------
# Decode
# ---------------------------------------------------------------------------

class DecodeError(Exception):
    pass


def decode(frame, security_level=SEC_L0_NONE, key=None,
           last_seen_nonce=None):
    """
    Parse a [LEN][packet][CRC] frame as received from CC1101.

    Returns a dict with keys: type, apid, seq_count, user_data, nonce,
    auth_ok, replay_ok. `replay_ok` is True if last_seen_nonce is None or
    if the new nonce is lexicographically strictly greater (L2+ rule).
    """
    if len(frame) < 1 + 6 + 2:
        raise DecodeError("frame too short")
    length = frame[0]
    body = frame[1:1 + length]
    if len(body) != length:
        raise DecodeError("truncated frame")

    space_packet = body[:-2]
    rx_crc = struct.unpack(">H", body[-2:])[0]
    if crc16_ccitt(space_packet) != rx_crc:
        raise DecodeError("bad CRC")

    hdr = _unpack_primary(space_packet[:6])
    payload = space_packet[6:6 + hdr["payload_len"]]

    nonce = None
    auth_ok = None
    replay_ok = None

    if hdr["sh"] == 0:
        user_data = payload
    else:
        if len(payload) < NONCE_LEN + TAG_LEN:
            raise DecodeError("secondary header truncated")
        nonce = payload[:NONCE_LEN]
        tag   = payload[NONCE_LEN:NONCE_LEN + TAG_LEN]
        body_enc = payload[NONCE_LEN + TAG_LEN:]

        if key is None:
            raise DecodeError("secured packet but no key supplied")

        if security_level == SEC_L1_HMAC:
            mac_input = body_enc
        else:
            mac_input = nonce + body_enc
        expected = hmac_sha256(key, mac_input)[:TAG_LEN]
        auth_ok = _ct_eq(tag, expected)

        if security_level == SEC_L3_AES_HMAC:
            user_data = _aes_ctr(key, nonce, body_enc)
        else:
            user_data = body_enc

        if security_level >= SEC_L2_HMAC_CTR:
            replay_ok = (last_seen_nonce is None) or (nonce > last_seen_nonce)
        else:
            replay_ok = True  # L1 has no replay defence

    return {
        "type":      hdr["type"],
        "apid":      hdr["apid"],
        "seq_count": hdr["seq_count"],
        "user_data": user_data,
        "nonce":     nonce,
        "auth_ok":   auth_ok,
        "replay_ok": replay_ok,
    }


def _ct_eq(a, b):
    """Constant-time-ish comparison. *Intentionally* non-constant in L0/L1
    so lesson L09 (timing side-channel) has a target. Used here for the
    *secure* path only — security-level docs note the contrast."""
    if len(a) != len(b):
        return False
    acc = 0
    for x, y in zip(a, b):
        acc |= x ^ y
    return acc == 0


# ---------------------------------------------------------------------------
# Tiny self-test (host-only — guarded for MicroPython)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # L0 round-trip
    frame = encode(TYPE_TM, APID_BEACON, 1, b"SEMAEOPUS HELLO")
    dec = decode(frame)
    assert dec["apid"] == APID_BEACON
    assert dec["user_data"] == b"SEMAEOPUS HELLO"
    print("L0 round-trip OK, frame =", frame.hex())

    # L2 round-trip
    key = b"0123456789abcdef"
    nonce = b"\x00" * 7 + b"\x01"
    frame = encode(TYPE_TC, APID_FORCE_SAFE, 42, b"",
                   security_level=SEC_L2_HMAC_CTR, key=key, nonce=nonce)
    dec = decode(frame, security_level=SEC_L2_HMAC_CTR, key=key,
                 last_seen_nonce=b"\x00" * 8)
    assert dec["auth_ok"] and dec["replay_ok"]
    print("L2 round-trip OK, frame =", frame.hex())
