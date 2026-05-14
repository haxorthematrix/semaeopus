"""
Periodic beacon. Mimics the human-readable AX.25 status beacons many
amateur CubeSats transmit — but wrapped in a CCSDS-lite frame so the
attacker has structured bytes to chew on.

BEACON payload:  "<callsign> M<mode> B<boot> U<uptime_s> SOC<pct>"
"""

from obc.compat import ticks_ms, ticks_diff
from protocol import space_packet as sp


class Beacon:
    def __init__(self, state):
        self.state = state
        self._t0 = ticks_ms()

    def build(self):
        uptime_s = ticks_diff(ticks_ms(), self._t0) // 1000
        s = "%s M%d B%d U%d SOC%d" % (
            self.state.callsign,
            self.state.mode.current,
            self.state.boot_count,
            uptime_s,
            int(self.state.eps.soc),
        )
        return (sp.APID_BEACON, s.encode())
