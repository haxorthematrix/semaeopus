"""
Mode state machine.

Real CubeSats have a similar set of operating modes:
  NOMINAL — comms + telemetry as usual
  SAFE    — minimum power, beacon only, ignore most TCs
  PAYLOAD — payload "exposed" / armed
  IDLE    — comms but no payload, intermediate state

Only certain transitions are legal. Some attacks (L06) try to break out
of SAFE without authentication — the firmware enforces a
SAFE→NOMINAL transition only if the TC arrives in SAFE mode AND its
APID matches `0x083 SET_MODE` exactly. In later lessons this becomes
harder to forge.
"""

FLAG_PAYLOAD_ARMED = 0x01
FLAG_SAFE_LATCHED  = 0x02


class ModeState:
    NOMINAL = 0
    SAFE    = 1
    PAYLOAD = 2
    IDLE    = 3

    def __init__(self, initial):
        self.current = initial
        self.flags = 0

    def request(self, new_mode):
        """Return True if the transition was applied."""
        legal = {
            (self.NOMINAL, self.SAFE),
            (self.NOMINAL, self.PAYLOAD),
            (self.NOMINAL, self.IDLE),
            (self.IDLE,    self.NOMINAL),
            (self.IDLE,    self.SAFE),
            (self.PAYLOAD, self.NOMINAL),
            (self.PAYLOAD, self.SAFE),
            (self.SAFE,    self.NOMINAL),
        }
        if (self.current, new_mode) in legal:
            self.current = new_mode
            if new_mode == self.SAFE:
                self.flags |= FLAG_SAFE_LATCHED
                self.flags &= ~FLAG_PAYLOAD_ARMED
            return True
        return False

    def arm_payload(self):
        if self.current in (self.NOMINAL, self.PAYLOAD):
            self.flags |= FLAG_PAYLOAD_ARMED
            return True
        return False

    def fire_payload(self):
        return bool(self.flags & FLAG_PAYLOAD_ARMED)
