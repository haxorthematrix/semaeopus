"""
Textual operator GS — live dashboard.

Same command set as gs.py (ping / safe / mode N / req / arm / fire /
raw / key / quit) but rendered as a TUI with four panes:

  ┌─ Link status ────────┐ ┌─ Latest beacon ──┐
  │ RSSI history, queue  │ │ call sign, mode, │
  │ depth, sec level     │ │ SOC, uptime      │
  └──────────────────────┘ └──────────────────┘
  ┌─ Telemetry stream (HK/ADCS/EPS, last 50)  │
  │  ts  apid  rssi  pretty                   │
  └───────────────────────────────────────────┘
  ┌─ Command palette ─────────────────────────┐
  │ op>                                       │
  └───────────────────────────────────────────┘

Plus a footer row showing TC count, RX count, sequence-counter gaps.

Run with --sim:
    pip install textual rich
    python -m groundstation.operator.tui --sim
"""

import argparse
import asyncio
import os
import sys
import time
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

try:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, Container
    from textual.widgets import Header, Footer, Static, RichLog, Input, Label
    from textual.reactive import reactive
    from rich.text import Text
    from rich.table import Table
except ImportError:
    print("textual + rich not installed.")
    print("  pip install textual rich")
    sys.exit(1)

from groundstation.shared.decoder import decode_rx
from protocol import space_packet as sp


class OperatorState:
    def __init__(self):
        self.tc_seq = 0
        self.last_nonce = None
        self.security = 0
        self.key = None
        self.tx_count = 0
        self.rx_count = 0
        self.rx_bad   = 0
        self.last_beacon = None
        self.last_rssi = None
        self.last_apid_name = ""
        self.seen_seqs = {}  # apid → last seq, for gap detection
        self.gaps = 0

    def next_nonce(self):
        n = 1 if self.last_nonce is None else int.from_bytes(self.last_nonce, "big") + 1
        return n.to_bytes(8, "big")


class TelemetryLog(RichLog):
    def __init__(self, **kw):
        super().__init__(highlight=False, markup=True, wrap=False, **kw)


class LinkStatus(Static):
    def update_status(self, state, link_ready):
        t = Table.grid(padding=(0, 1))
        t.add_column(style="dim")
        t.add_column(style="bold")
        t.add_row("link",      "[green]up[/green]" if link_ready else "[red]down[/red]")
        t.add_row("security",  f"L{state.security}")
        t.add_row("RSSI",      f"{state.last_rssi} dBm" if state.last_rssi is not None else "—")
        t.add_row("TX count",  str(state.tx_count))
        t.add_row("RX count",  str(state.rx_count))
        t.add_row("RX bad",    f"[yellow]{state.rx_bad}[/yellow]" if state.rx_bad else "0")
        t.add_row("seq gaps",  f"[red]{state.gaps}[/red]" if state.gaps else "0")
        self.update(t)


class BeaconBox(Static):
    def update_beacon(self, beacon_text, rssi):
        if not beacon_text:
            self.update("[dim]no beacon yet[/dim]")
            return
        self.update(f"[bold green]{beacon_text}[/bold green]\nRSSI: {rssi} dBm")


class OperatorApp(App):
    CSS = """
    Screen { layout: vertical; }
    #top { height: 7; }
    #status { width: 36; border: tall $primary; padding: 0 1; }
    #beacon { border: tall $secondary; padding: 0 1; }
    #tlm    { border: tall $accent; height: 1fr; }
    #cmd    { dock: bottom; height: 3; border: tall $warning; }
    """

    def __init__(self, link, state):
        super().__init__()
        self.link = link
        self.state = state
        self._tlm_log = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, name="Semaeopus operator")
        with Horizontal(id="top"):
            yield LinkStatus(id="status")
            yield BeaconBox(id="beacon")
        yield TelemetryLog(id="tlm")
        yield Input(placeholder="op> commands: ping | safe | arm | fire | mode N | req <apid_hex> | raw <apid_hex> <hex> | quit",
                    id="cmd")
        yield Footer()

    async def on_mount(self):
        self._tlm_log = self.query_one("#tlm", TelemetryLog)
        self.query_one("#status", LinkStatus).update_status(self.state, True)
        self.query_one("#beacon", BeaconBox).update_beacon(None, None)
        self.set_interval(0.05, self._poll_link)

    async def _poll_link(self):
        rx = self.link.rx_packets()
        if rx is None:
            return
        self.state.rx_count += 1
        self.state.last_rssi = rx["rssi"]
        d = decode_rx(rx,
                      security_level=self.state.security,
                      key=self.state.key,
                      last_nonce=self.state.last_nonce if self.state.security >= 2 else None)
        if "error" in d:
            self.state.rx_bad += 1
            self._tlm_log.write(f"[red]BAD  {d['error']}  RSSI={d['rssi']}[/red]")
        else:
            # Sequence gap detection
            prev = self.state.seen_seqs.get(d["apid"])
            if prev is not None:
                expected = (prev + 1) & 0x3FFF
                if d["seq"] != expected and d["seq"] != prev:
                    self.state.gaps += 1
            self.state.seen_seqs[d["apid"]] = d["seq"]

            if d["apid"] == sp.APID_BEACON:
                try:
                    btxt = d["pretty"]
                except Exception:
                    btxt = "<beacon>"
                self.state.last_beacon = btxt
                self.query_one("#beacon", BeaconBox).update_beacon(btxt, d["rssi"])

            sev = ""
            if d["auth_ok"] is False:
                sev = "[red](AUTH FAIL)[/red] "
            elif d["replay_ok"] is False:
                sev = "[yellow](REPLAY)[/yellow] "
            self._tlm_log.write(
                f"[dim]{int(rx['ts']) % 100000:5d}[/dim]  "
                f"[cyan]{d['apid_name']:13s}[/cyan]  RSSI={d['rssi']:+4d}  "
                f"seq={d['seq']:5d}  {sev}{d['pretty']}"
            )
        self.query_one("#status", LinkStatus).update_status(self.state, True)

    def _build_tc(self, apid, user_data):
        self.state.tc_seq = (self.state.tc_seq + 1) & 0x3FFF
        nonce = self.state.next_nonce() if self.state.security > 0 else None
        frame = sp.encode(
            sp.TYPE_TC, apid, self.state.tc_seq, user_data,
            security_level=self.state.security,
            key=self.state.key, nonce=nonce,
        )
        if nonce is not None:
            self.state.last_nonce = nonce
        return frame

    async def on_input_submitted(self, event: Input.Submitted):
        inp = event.value
        event.input.value = ""
        parts = inp.strip().split()
        if not parts:
            return
        cmd = parts[0].lower()
        try:
            if cmd == "quit":
                self.exit()
                return
            elif cmd == "ping":
                frame = self._build_tc(sp.APID_PING, b"\x00\x01\x02\x03")
            elif cmd == "safe":
                frame = self._build_tc(sp.APID_FORCE_SAFE, b"")
            elif cmd == "arm":
                frame = self._build_tc(sp.APID_ARM_PAYLOAD, b"")
            elif cmd == "fire":
                frame = self._build_tc(sp.APID_FIRE_PAYLOAD, b"")
            elif cmd == "mode" and len(parts) == 2:
                frame = self._build_tc(sp.APID_SET_MODE, bytes([int(parts[1])]))
            elif cmd == "req" and len(parts) == 2:
                frame = self._build_tc(sp.APID_REQ_TLM, bytes([int(parts[1], 16)]))
            elif cmd == "raw" and len(parts) == 3:
                apid = int(parts[1], 16)
                body = bytes.fromhex(parts[2])
                frame = self._build_tc(apid, body)
            elif cmd == "key" and len(parts) == 2:
                body = bytes.fromhex(parts[1])
                if len(body) != 16:
                    self._tlm_log.write("[red]key must be 16 bytes hex[/red]")
                    return
                frame = self._build_tc(sp.APID_KEY_ROTATE, body)
            else:
                self._tlm_log.write(f"[red]unknown: {inp}[/red]")
                return
            self.link.send_tx(frame)
            self.state.tx_count += 1
            self._tlm_log.write(f"[bold]→ TX {cmd:8s} apid=0x{frame[3]:02x}{frame[2]:02x} len={len(frame)}[/bold]")
        except Exception as e:
            self._tlm_log.write(f"[red]error: {e}[/red]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--node-id", default="OPGS")
    ap.add_argument("--freq", type=int, default=433_920_000)
    ap.add_argument("--sync", default="d391")
    ap.add_argument("--bitrate", type=int, default=9600)
    ap.add_argument("--security", type=int, default=0, choices=[0, 1, 2, 3])
    ap.add_argument("--key", default=None)
    args = ap.parse_args()

    if not args.sim and not args.port:
        ap.error("--port required unless --sim")

    state = OperatorState()
    state.security = args.security
    if args.security > 0:
        if not args.key:
            ap.error("--key required when --security >= 1")
        state.key = bytes.fromhex(args.key)
        if len(state.key) != 16:
            ap.error("--key must be 16 bytes hex")

    from sim.sim_link import make_link
    link = make_link(args, default_node_id=args.node_id)
    time.sleep(0.3)
    link.send_cfg(args.freq, int(args.sync, 16), args.bitrate)

    app = OperatorApp(link, state)
    app.run()


if __name__ == "__main__":
    main()
