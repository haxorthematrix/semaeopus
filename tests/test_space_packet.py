"""Codec tests for protocol/space_packet.py."""

import os
import random

import pytest

from protocol import space_packet as sp


KEY = bytes(range(16))                 # arbitrary 16-byte test key


# ---------------------------------------------------------------------------
# CRC
# ---------------------------------------------------------------------------

def test_crc_known_vector():
    # CRC-16-CCITT(0xFFFF) of "123456789" → 0x29B1
    assert sp.crc16_ccitt(b"123456789") == 0x29B1


def test_crc_empty_is_init():
    assert sp.crc16_ccitt(b"") == 0xFFFF


# ---------------------------------------------------------------------------
# L0 — cleartext round-trip
# ---------------------------------------------------------------------------

def test_l0_roundtrip_beacon():
    frame = sp.encode(sp.TYPE_TM, sp.APID_BEACON, 7, b"hello sat")
    d = sp.decode(frame)
    assert d["type"] == sp.TYPE_TM
    assert d["apid"] == sp.APID_BEACON
    assert d["seq_count"] == 7
    assert d["user_data"] == b"hello sat"
    assert d["auth_ok"] is None
    assert d["nonce"] is None


def test_l0_empty_payload():
    frame = sp.encode(sp.TYPE_TC, sp.APID_FORCE_SAFE, 1, b"")
    d = sp.decode(frame)
    assert d["apid"] == sp.APID_FORCE_SAFE
    assert d["user_data"] == b""


@pytest.mark.parametrize("apid", [0x001, 0x010, 0x080, 0x0FF, 0x123, 0x7FF])
def test_l0_apid_preserved(apid):
    frame = sp.encode(sp.TYPE_TC, apid, 1, b"x")
    assert sp.decode(frame)["apid"] == apid


@pytest.mark.parametrize("seq", [0, 1, 8191, 16383])
def test_l0_seq_preserved(seq):
    frame = sp.encode(sp.TYPE_TM, sp.APID_HK_TLM, seq, b"")
    assert sp.decode(frame)["seq_count"] == seq


def test_l0_long_payload():
    payload = bytes(range(256)) * 4   # 1024 B — well past one CC1101 FIFO
    frame = sp.encode(sp.TYPE_TM, sp.APID_PAYLOAD_DATA, 0, payload[:200])
    assert sp.decode(frame)["user_data"] == payload[:200]


# ---------------------------------------------------------------------------
# CRC detects corruption
# ---------------------------------------------------------------------------

def test_bit_flip_anywhere_fails_crc():
    frame = sp.encode(sp.TYPE_TM, sp.APID_BEACON, 1, b"ABCDEFGH")
    for idx in range(1, len(frame)):     # skip the LEN byte
        bad = bytearray(frame)
        bad[idx] ^= 0x01
        with pytest.raises(sp.DecodeError):
            sp.decode(bytes(bad))


def test_truncated_frame():
    frame = sp.encode(sp.TYPE_TM, sp.APID_BEACON, 1, b"ABCDEFGH")
    with pytest.raises(sp.DecodeError):
        sp.decode(frame[:5])


def test_short_frame():
    with pytest.raises(sp.DecodeError):
        sp.decode(b"\x02\x00\x00")


# ---------------------------------------------------------------------------
# L1 — HMAC (no nonce binding) — replay still works (lesson L07)
# ---------------------------------------------------------------------------

def test_l1_roundtrip_and_replay_succeeds():
    n1 = b"\x00" * 7 + b"\x01"
    frame = sp.encode(sp.TYPE_TC, sp.APID_FORCE_SAFE, 1, b"x",
                      security_level=sp.SEC_L1_HMAC, key=KEY, nonce=n1)
    d = sp.decode(frame, security_level=sp.SEC_L1_HMAC, key=KEY)
    assert d["auth_ok"]
    assert d["user_data"] == b"x"
    # Replay decodes identically — that's the lesson.
    d2 = sp.decode(frame, security_level=sp.SEC_L1_HMAC, key=KEY)
    assert d2["auth_ok"]


def test_l1_tampered_body_fails():
    n1 = b"\x00" * 7 + b"\x01"
    frame = bytearray(sp.encode(sp.TYPE_TC, sp.APID_FORCE_SAFE, 1, b"x",
                                security_level=sp.SEC_L1_HMAC, key=KEY, nonce=n1))
    # Flip a byte inside the body. The body sits after primary header (6 B)
    # + secondary (16 B), which is at offset 1+6+16 = 23 from start.
    frame[23] ^= 0x01
    # CRC fix to keep the decoder reaching the HMAC check.
    space = bytes(frame[1:-2])
    new_crc = sp.crc16_ccitt(space)
    frame[-2:] = new_crc.to_bytes(2, "big")
    d = sp.decode(bytes(frame), security_level=sp.SEC_L1_HMAC, key=KEY)
    assert d["auth_ok"] is False


# ---------------------------------------------------------------------------
# L2 — HMAC over nonce ‖ body, monotonic nonce — replay blocked
# ---------------------------------------------------------------------------

def test_l2_replay_blocked():
    n1 = b"\x00" * 7 + b"\x01"
    frame = sp.encode(sp.TYPE_TC, sp.APID_FORCE_SAFE, 1, b"",
                      security_level=sp.SEC_L2_HMAC_CTR, key=KEY, nonce=n1)
    # First reception: window starts at zero, nonce is greater → accepted.
    d1 = sp.decode(frame, security_level=sp.SEC_L2_HMAC_CTR, key=KEY,
                   last_seen_nonce=b"\x00" * 8)
    assert d1["auth_ok"] and d1["replay_ok"]
    # Replay with last_seen_nonce now == n1 → must reject.
    d2 = sp.decode(frame, security_level=sp.SEC_L2_HMAC_CTR, key=KEY,
                   last_seen_nonce=n1)
    assert d2["auth_ok"] and not d2["replay_ok"]


def test_l2_nonce_must_strictly_increase():
    n1 = b"\x00" * 7 + b"\x05"
    n2 = b"\x00" * 7 + b"\x06"
    f1 = sp.encode(sp.TYPE_TC, sp.APID_PING, 1, b"a",
                   security_level=sp.SEC_L2_HMAC_CTR, key=KEY, nonce=n1)
    f2 = sp.encode(sp.TYPE_TC, sp.APID_PING, 2, b"b",
                   security_level=sp.SEC_L2_HMAC_CTR, key=KEY, nonce=n2)
    last = b"\x00" * 8
    d1 = sp.decode(f1, security_level=sp.SEC_L2_HMAC_CTR, key=KEY,
                   last_seen_nonce=last)
    assert d1["replay_ok"]
    # Now process f2 — it should be accepted because n2 > n1.
    d2 = sp.decode(f2, security_level=sp.SEC_L2_HMAC_CTR, key=KEY,
                   last_seen_nonce=n1)
    assert d2["replay_ok"]


# ---------------------------------------------------------------------------
# L3 — AES-128-CTR + HMAC — ciphertext is not plaintext
# ---------------------------------------------------------------------------

def test_l3_encrypts_and_authenticates():
    pytest.importorskip("Crypto", reason="pycryptodome not installed")
    n1 = b"\x00" * 7 + b"\x09"
    plaintext = b"OPERATOR-ONLY: ARM PAYLOAD AT T+30"
    frame = sp.encode(sp.TYPE_TC, sp.APID_ARM_PAYLOAD, 1, plaintext,
                      security_level=sp.SEC_L3_AES_HMAC, key=KEY, nonce=n1)
    # Ciphertext block sits after [LEN][primary 6][nonce 8][tag 8] = 23 bytes.
    body = frame[23:-2]
    assert body != plaintext  # encrypted
    # Decode roundtrips.
    d = sp.decode(frame, security_level=sp.SEC_L3_AES_HMAC, key=KEY,
                  last_seen_nonce=b"\x00" * 8)
    assert d["auth_ok"] and d["replay_ok"]
    assert d["user_data"] == plaintext


# ---------------------------------------------------------------------------
# Fuzz round-trip — encode any plausible payload, ensure decode recovers it
# ---------------------------------------------------------------------------

def test_random_roundtrip_l0():
    rng = random.Random(0xCAFE)
    for _ in range(200):
        n = rng.randint(0, 100)
        payload = bytes(rng.randrange(256) for _ in range(n))
        apid = rng.randrange(0x800)
        seq  = rng.randrange(0x4000)
        ptype = rng.choice([sp.TYPE_TM, sp.TYPE_TC])
        frame = sp.encode(ptype, apid, seq, payload)
        d = sp.decode(frame)
        assert d["type"] == ptype
        assert d["apid"] == apid
        assert d["seq_count"] == seq
        assert d["user_data"] == payload
