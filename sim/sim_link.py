"""
SimLink — a Link-compatible class that goes over the UDP radio bus
instead of USB-serial. Lets the operator GS and attacker tooling run
unmodified against the virtual satellite.

Same surface as groundstation/shared/link.Link:
    send_tx(frame_bytes)
    send_cfg(freq, sync, bitrate)   — no-op in sim
    rx_packets()                    — returns one dict or None
    events()                        — returns one str or None
    close()
"""

import queue
import time

from sim.radio_bus import RadioNode


class SimLink:
    def __init__(self, node_id="GS0", tx_power_dbm=0):
        self.radio = RadioNode(node_id, tx_power_dbm=tx_power_dbm)
        self.radio.listen()
        self._evt_q = queue.Queue()
        self._evt_q.put("EVT sim-link ready (%s)" % node_id)

    def send_tx(self, frame_bytes):
        self.radio.transmit(frame_bytes)

    def send_cfg(self, freq_hz, sync_word, bitrate):
        # No-op for the simulator — recorded as an event for visibility.
        self._evt_q.put("EVT cfg %d %04x %d (sim)" % (freq_hz, sync_word, bitrate))

    def rx_packets(self):
        if not self.radio.packet_available():
            return None
        frame, rssi, lqi = self.radio.read_packet()
        if frame is None:
            return None
        return {"frame": frame, "rssi": rssi, "lqi": lqi, "ts": time.time()}

    def events(self):
        try:
            return self._evt_q.get_nowait()
        except queue.Empty:
            return None

    def close(self):
        self.radio.close()


def make_link(args, default_node_id):
    """Factory: --sim → SimLink, otherwise the serial Link."""
    if getattr(args, "sim", False):
        return SimLink(node_id=getattr(args, "node_id", default_node_id))
    from groundstation.shared.link import Link
    return Link(args.port)
