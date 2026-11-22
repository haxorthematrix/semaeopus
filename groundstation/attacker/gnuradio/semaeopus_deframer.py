"""
Embedded Python Block: Semaeopus deframer.

Paste this whole file into an Embedded Python Block in GNU Radio
Companion (double-click the block, "Open in Editor", replace the
template, save). Python 3, GNU Radio 3.10+, no other dependencies.

Input: one bit per byte (0/1) from "Correlate Access Code - Tag Stream",
with a tag (name `sync` by default) on the first bit after each sync match.

What a real CC1101 sends with the Semaeopus register settings:

    AA AA AA AA | D3 91 D3 91 | LEN | space packet | CRC-CCITT | radio CRC
    preamble      sync, sent    1     CCSDS          over the    poly 0x8005
                  twice (30/32  byte  packet         packet      over LEN..
                  sync mode)                                     CRC-CCITT

LEN counts the bytes after it, not including the radio CRC. Set
radio_crc=False for the synthetic captures from tools/generate_iq.py,
which send the sync word once and have no radio CRC.

Each frame is printed, published on the `frames` message port as a PDU,
and (if `jsonl` is a file path) appended as {"frame": "<hex>"}, the same
key the capture tools use, so you can diff against a capture.
"""
import json

import numpy as np
import pmt
from gnuradio import gr

SYNC = [int(c) for c in "1101001110010001"]   # 0xD391


def _crc16(data, poly):
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


class blk(gr.sync_block):
    def __init__(self, tag_name="sync", radio_crc=True, jsonl=""):
        gr.sync_block.__init__(self, name="Semaeopus Deframer",
                               in_sig=[np.uint8], out_sig=None)
        self.tag_name = tag_name
        self.radio_crc = radio_crc
        self.jsonl = jsonl
        self.message_port_register_out(pmt.intern("frames"))
        self.bits = None          # bits of the frame being collected
        self.length = None
        self.checked = False
        self.frames_ok = 0
        self.frames_bad = 0

    def _byte(self, k):
        b = 0
        for bit in self.bits[8 * k:8 * k + 8]:
            b = (b << 1) | bit
        return b

    def _finish(self):
        raw = bytes(self._byte(k) for k in range(1 + self.length))   # LEN..CRC
        good = _crc16(raw[1:-2], 0x1021) == int.from_bytes(raw[-2:], "big")
        note = ""
        if self.radio_crc:
            rc = (self._byte(1 + self.length) << 8) | self._byte(2 + self.length)
            note = " radio-crc=%s" % ("ok" if rc == _crc16(raw, 0x8005) else "BAD")
        if good:
            self.frames_ok += 1
        else:
            self.frames_bad += 1
        apid = ((raw[1] << 8) | raw[2]) & 0x7FF
        seq = ((raw[3] << 8) | raw[4]) & 0x3FFF
        print("frame apid=0x%03x seq=%d len=%d ccsds-crc=%s%s : %s" % (
            apid, seq, self.length, "ok" if good else "BAD", note, raw.hex()), flush=True)
        self.message_port_pub(pmt.intern("frames"),
                              pmt.cons(pmt.PMT_NIL, pmt.init_u8vector(len(raw), list(raw))))
        if self.jsonl:
            with open(self.jsonl, "a") as fp:
                fp.write(json.dumps({"frame": raw.hex(), "crc_ok": good}) + "\n")

    def work(self, input_items, output_items):
        x = input_items[0]
        base = self.nitems_read(0)
        starts = set(t.offset - base for t in
                     self.get_tags_in_window(0, 0, len(x), pmt.intern(self.tag_name)))
        for i in range(len(x)):
            if self.bits is None:
                if i not in starts:
                    continue
                self.bits, self.length, self.checked = [], None, False
            self.bits.append(int(x[i]) & 1)
            if not self.checked:
                if len(self.bits) < 16:
                    continue
                self.checked = True
                # Correlating on one copy of the sync word: skip the second.
                if sum(a != b for a, b in zip(self.bits, SYNC)) <= 2:
                    self.bits = []
                    continue
            n = len(self.bits)
            if self.length is None:
                if n >= 8:
                    self.length = self._byte(0)
                    if not 3 <= self.length <= 61:     # CC1101 62-byte FIFO limit
                        self.bits = None
                continue
            if n == 8 * (1 + self.length + (2 if self.radio_crc else 0)):
                self._finish()
                self.bits = None
        return len(x)
