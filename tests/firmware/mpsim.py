"""Run the Semaeopus MicroPython firmware on CPython with simulated hardware.

Used by tests/firmware. Everything this module patches (time.ticks_*,
time.sleep_ms/us, sys.modules entries for machine/framebuf/select and the
firmware's own top-level packages) is installed only while run_board()
executes and restored afterwards, so the host-side test suite is unaffected.

Fakes: machine (Pin, SPI, ADC), framebuf, select/stdin, and MicroPython's
time.ticks_* API on a simulated clock. The CC1101 is simulated at the SPI
register level (strobes, registers, status registers, TX and RX FIFOs),
so the real driver code is exercised.
"""
import importlib.util, io, sys, time, types


# ---------------------------------------------------------------- clock ----
class Clock:
    us = 0


def _ticks_us():
    Clock.us += 2
    return Clock.us


_TIME_PATCH = {
    "ticks_us": _ticks_us,
    "ticks_ms": lambda: _ticks_us() // 1000,
    "ticks_diff": lambda a, b: a - b,
    "ticks_add": lambda a, b: a + b,
    "sleep_us": lambda us: setattr(Clock, "us", Clock.us + us),
}


class StopSim(BaseException):
    pass


class Sim:
    loop_ms = None          # the main loop's sleep value
    step = 0
    max_steps = 0
    hook = None


def _sleep_ms(ms):
    Clock.us += ms * 1000
    if ms == Sim.loop_ms:
        Sim.step += 1
        if Sim.hook:
            Sim.hook(Sim.step)
        if Sim.step >= Sim.max_steps:
            raise StopSim()


_TIME_PATCH["sleep_ms"] = _sleep_ms


# ---------------------------------------------------------------- CC1101 ----
DEFAULTS = {0x00: 0x29, 0x02: 0x3F, 0x04: 0xD3, 0x05: 0x91, 0x06: 0xFF,
            0x0D: 0x1E, 0x0E: 0xC4, 0x0F: 0xEC, 0x10: 0x8C}


class Chip:
    def __init__(self):
        self.sent = []
        self.rx = bytearray()
        self.tx = bytearray()
        self.patable = None
        self.cs_low = False
        self.hdr = None
        self.gdo_seq = []
        self.rssi_raw = 0xC8           # -102 dBm idle noise
        self.incoming = []             # packets arriving over the air: [start_us, bytes, delivered]
        self.realistic = True          # bytes arrive at 9600 bps; RX -> IDLE at packet end
        self.reset()

    US_PER_BYTE = 833                  # 9600 bps

    def _advance(self):
        """Move over-the-air bytes into the RX FIFO as simulated time passes.
        A packet is only heard if the radio is in RX when it starts; at its end the
        chip leaves RX for IDLE (MCSM1 RXOFF_MODE = IDLE), like the real CC1101."""
        while self.incoming:
            pkt = self.incoming[0]
            if pkt[0] is None:
                if self.marc != 0x0D:
                    return                        # not listening yet: wait
                pkt[0] = Clock.us
            due = min(len(pkt[1]), (Clock.us - pkt[0]) // self.US_PER_BYTE + 1)
            while pkt[2] < due:
                self.rx.append(pkt[1][pkt[2]])
                pkt[2] += 1
            if pkt[2] < len(pkt[1]):
                self.receiving = True
                return
            self.receiving = False
            self.incoming.pop(0)
            self.marc = 0x01
            return

    def reset(self):
        self.regs = bytearray(0x30)
        for a, v in DEFAULTS.items():
            self.regs[a] = v
        self.marc = 0x01

    def freq_hz(self):
        w = (self.regs[0x0D] << 16) | (self.regs[0x0E] << 8) | self.regs[0x0F]
        return w * 26_000_000 / 65536

    def begin(self):
        self.hdr = None
        if self.realistic:
            self._advance()

    def xfer(self, b):
        if self.hdr is None:
            self.hdr = b
            self.addr, self.rw, self.burst = b & 0x3F, b & 0x80, b & 0x40
            if 0x30 <= self.addr <= 0x3D and not self.burst:
                self.strobe(self.addr)
                self.hdr = "done"
            return 0x00
        if self.hdr == "done":
            return 0x00
        a = self.addr
        if self.rw:
            if a == 0x3F:
                return self.rx.pop(0) if self.rx else 0
            if 0x30 <= a <= 0x3D and self.burst:
                return {0x30: 0x00, 0x31: 0x14, 0x34: self.rssi_raw, 0x35: self.marc,
                        0x3B: len(self.rx)}.get(a, 0)
            v = self.regs[a] if a < 0x30 else 0
            if self.burst:
                self.addr += 1
            return v
        if a == 0x3F:
            self.tx.append(b)
        elif a == 0x3E:
            self.patable = b
        elif a < 0x30:
            self.regs[a] = b
            if self.burst:
                self.addr += 1
        return 0x00

    def strobe(self, c):
        if c in (0x30, 0x33, 0x35, 0x36) and self.incoming and self.incoming[0][0] is not None:
            if self.incoming[0][2] < len(self.incoming[0][1]):
                self.incoming.pop(0)          # reception aborted: rest of packet is lost
                self.receiving = False
                self.lost = getattr(self, "lost", 0) + 1
        if c == 0x30:
            self.reset()
        elif c in (0x36, 0x33):
            self.marc = 0x01
        elif c == 0x34:
            self.marc = 0x0D
        elif c == 0x35:
            self.sent.append(bytes(self.tx))
            self.tx = bytearray()
            self.gdo_seq = [1, 0]
            self.marc = 0x01
        elif c == 0x3A:
            self.rx = bytearray()
        elif c == 0x3B:
            self.tx = bytearray()

    def gdo0(self):
        if self.gdo_seq:
            return self.gdo_seq.pop(0)
        if self.realistic:
            self._advance()
            return 1 if getattr(self, "receiving", False) else 0
        return 0

    def inject(self, frame, rssi_dbm=-60, lqi=40):
        raw = ((rssi_dbm + 74) * 2) & 0xFF
        data = bytes(frame) + bytes([raw, 0x80 | lqi])
        if self.realistic:
            self.incoming.append([None, data, 0])
        else:
            self.rx += data


# ---------------------------------------------------------------- board ----
class Board:
    def __init__(self, radio_spi, cs, gdo0):
        self.radio_spi, self.cs, self.gdo0 = radio_spi, cs, gdo0
        self.chip = Chip()
        self.display_bytes = 0
        self.display_cmds = []
        self.irqs = {}
        self.adc = 20000
        self.stdin = []
        self.stdout = io.StringIO()


BOARD = None


class Pin:
    IN, OUT, PULL_UP, PULL_DOWN, IRQ_FALLING, IRQ_RISING = 1, 2, 3, 4, 5, 6

    def __init__(self, n, mode=None, pull=None, value=None):
        self.n, self.v = n, 1
        if value is not None:
            self.value(value)

    def value(self, v=None):
        if v is None:
            if self.n == BOARD.gdo0:
                return BOARD.chip.gdo0()
            return self.v
        self.v = v
        if self.n == BOARD.cs:
            low = v == 0
            if low and not BOARD.chip.cs_low:
                BOARD.chip.begin()
            BOARD.chip.cs_low = low

    def toggle(self):
        self.v ^= 1

    def irq(self, trigger=None, handler=None):
        BOARD.irqs[self.n] = handler


class SPI:
    def __init__(self, id, baudrate=0, polarity=0, phase=0, sck=None, mosi=None, miso=None):
        self.id = id
        if id == BOARD.radio_spi:
            BOARD.radio_pins = (sck.n, mosi.n, miso.n)

    def deinit(self):
        pass

    def write(self, buf):
        if self.id == BOARD.radio_spi:
            for b in buf:
                BOARD.chip.xfer(b)
        else:
            BOARD.display_bytes += len(buf)
            if len(buf) == 1:
                BOARD.display_cmds.append(buf[0])

    def read(self, n):
        return bytes(BOARD.chip.xfer(0) for _ in range(n))


class ADC:
    ATTN_0DB = 0

    def __init__(self, pin):
        pass

    def atten(self, a):
        pass

    def read_u16(self):
        return BOARD.adc


machine = types.ModuleType("machine")
machine.Pin, machine.SPI, machine.ADC = Pin, SPI, ADC

# framebuf: deterministic stand-in font, one byte per character row
framebuf = types.ModuleType("framebuf")
framebuf.MONO_HLSB = 3


class FrameBuffer:
    def __init__(self, buf, w, h, fmt):
        self.buf, self.w = buf, w

    def text(self, s, x, y, c):
        n = self.w // 8
        for k, ch in enumerate(s):
            for r in range(8):
                self.buf[r * n + x // 8 + k] = 0 if ch == " " else (ord(ch) * 7 + r * 13) & 0xFF


framebuf.FrameBuffer = FrameBuffer


# select / stdin for the modem
class _Poll:
    def register(self, *a):
        pass

    def poll(self, t=0):
        return [1] if BOARD.stdin else []


select = types.ModuleType("select")
select.poll, select.POLLIN = _Poll, 1


class _Stdin:
    def read(self, n):
        return BOARD.stdin.pop(0) if BOARD.stdin else ""


def host_space_packet(path):
    spec = importlib.util.spec_from_file_location("host_space_packet", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


DEVICE_MODULES = ("config", "pins", "lib", "obc", "comms", "protocol", "main")


def run_board(stage, board, loop_ms, max_steps, hook=None, pre=None):
    """Execute stage/main.py on `board` until max_steps main-loop sleeps."""
    global BOARD
    BOARD = board
    try:
        import Crypto.Cipher.AES, Crypto.Util.Counter   # load before faking select
    except ImportError:
        pass
    saved_mods = {n: m for n, m in sys.modules.items()
                  if n.split(".")[0] in DEVICE_MODULES + ("machine", "framebuf", "select")}
    for name in saved_mods:
        del sys.modules[name]
    for name, fn in _TIME_PATCH.items():
        setattr(time, name, fn)
    sys.modules["machine"], sys.modules["framebuf"], sys.modules["select"] = machine, framebuf, select
    sys.path.insert(0, stage)
    Sim.loop_ms, Sim.step, Sim.max_steps, Sim.hook = loop_ms, 0, max_steps, hook
    saved_in, saved_out = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = _Stdin(), board.stdout
    g = {"__name__": "__main__"}
    try:
        if pre:
            pre()
        exec(compile(open(stage + "/main.py").read(), stage + "/main.py", "exec"), g)
    except StopSim:
        pass
    finally:
        sys.stdin, sys.stdout = saved_in, saved_out
        sys.path.remove(stage)
        for name in list(sys.modules):
            if name.split(".")[0] in DEVICE_MODULES + ("machine", "framebuf", "select"):
                del sys.modules[name]
        sys.modules.update(saved_mods)
        for name in _TIME_PATCH:
            if hasattr(time, name):
                delattr(time, name)
    return g
