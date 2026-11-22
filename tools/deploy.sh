#!/usr/bin/env bash
# Copy Semaeopus firmware onto a board that already runs MicroPython.
#
#   tools/deploy.sh cyd-satellite  <port>   CYD satellite (recommended build)
#   tools/deploy.sh cyd-ground     <port>   CYD operator ground station modem
#   tools/deploy.sh pico-modem     <port>   Pico + CC1101 USB modem (attacker, or a Pico ground station)
#   tools/deploy.sh pico-satellite <port>   original breadboard Pico satellite
#   tools/deploy.sh bringup-cyd    <port>   run the CYD radio bring-up test (copies nothing)
#   tools/deploy.sh bringup-pico   <port>   run the Pico CC1101 ID test (copies nothing)
#
# Ports: macOS CYD /dev/cu.usbserial-*, Pico /dev/cu.usbmodem*; Linux /dev/ttyUSB* / /dev/ttyACM*.
# Needs mpremote:  python3 -m pip install mpremote
# (Found on PATH or as "python3 -m mpremote". Set MPREMOTE to override.)
#
# STAGE_ONLY=<dir> tools/deploy.sh <target> - : assemble the files into <dir> and stop.

set -euo pipefail

usage() { sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }
[ $# -eq 2 ] || usage
TARGET=$1
PORT=$2
ROOT=$(cd "$(dirname "$0")/.." && pwd)
FW="$ROOT/firmware"

find_mpremote() {
  if [ -n "${MPREMOTE:-}" ]; then MP=($MPREMOTE); return 0; fi
  if command -v mpremote >/dev/null 2>&1; then MP=(mpremote); return 0; fi
  for py in python3 python; do
    if command -v "$py" >/dev/null 2>&1 && "$py" -c "import mpremote" >/dev/null 2>&1; then
      MP=("$py" -m mpremote); return 0
    fi
  done
  echo "mpremote not found. Install it with:  python3 -m pip install mpremote" >&2
  echo "(or point MPREMOTE at it, e.g.  MPREMOTE=\"/path/to/python -m mpremote\" $0 ...)" >&2
  exit 1
}

case "$TARGET" in
  bringup-cyd)  find_mpremote; exec "${MP[@]}" connect "$PORT" run "$ROOT/bringup/cyd/06_cc1101_cyd.py" ;;
  bringup-pico) find_mpremote; exec "${MP[@]}" connect "$PORT" run "$ROOT/bringup/06_cc1101_id.py" ;;
esac

STAGE=${STAGE_ONLY:-$(mktemp -d)}
mkdir -p "$STAGE/lib"

copy_protocol() {
  mkdir -p "$STAGE/protocol"
  cp "$ROOT/protocol/space_packet.py" "$STAGE/protocol/"
  : > "$STAGE/protocol/__init__.py"
}

case "$TARGET" in
  cyd-satellite)
    cp "$FW/cyd_satellite/main.py" "$FW/cyd_satellite/config.py" "$STAGE/"
    cp "$FW/shared/cyd_pins.py" "$STAGE/pins.py"
    cp "$FW/cyd_satellite/lib/"*.py "$FW/satellite/lib/cc1101.py" "$FW/shared/cyd_display.py" "$STAGE/lib/"
    cp -R "$FW/satellite/obc" "$FW/satellite/comms" "$STAGE/"
    copy_protocol
    ;;
  cyd-ground)
    cp "$FW/cyd_ground/main.py" "$FW/cyd_ground/config.py" "$STAGE/"
    cp "$FW/shared/cyd_pins.py" "$STAGE/pins.py"
    cp "$FW/satellite/lib/cc1101.py" "$FW/shared/cyd_display.py" "$FW/shared/modem.py" "$STAGE/lib/"
    ;;
  pico-modem)
    cp "$FW/gs_frontend/main.py" "$STAGE/"
    cp "$FW/satellite/lib/cc1101.py" "$FW/shared/modem.py" "$STAGE/lib/"
    ;;
  pico-satellite)
    cp "$FW/satellite/main.py" "$FW/satellite/config.py" "$STAGE/"
    cp "$FW/satellite/lib/"*.py "$STAGE/lib/"
    cp -R "$FW/satellite/obc" "$FW/satellite/comms" "$STAGE/"
    copy_protocol
    ;;
  *) usage ;;
esac

: > "$STAGE/lib/__init__.py"
find "$STAGE" \( -name '__pycache__' -o -name '*.md' \) -prune -exec rm -rf {} + 2>/dev/null || true

if [ -n "${STAGE_ONLY:-}" ]; then
  echo "staged $TARGET into $STAGE"
  exit 0
fi

find_mpremote
ARGS=(connect "$PORT")
cd "$STAGE"
for entry in *; do
  if [ -d "$entry" ]; then
    ARGS+=(cp -r "$entry" : +)
  else
    ARGS+=(cp "$entry" ":$entry" +)
  fi
done
ARGS+=(reset)

echo "Copying $TARGET files to $PORT (using ${MP[*]}) ..."
"${MP[@]}" "${ARGS[@]}"
echo "Done. The board has reset and is running the $TARGET firmware."
rm -rf "$STAGE"
