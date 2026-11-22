"""
Operator ground station configuration (CYD build). Pin numbers live in pins.py.
"""

from pins import *   # noqa: F401,F403

# Power-on frequency. The laptop's gs.py also sends CFG on connect, so
# always run it with --freq 915000000 to match.
RF_FREQ_HZ = 915_000_000
RF_TX_POWER_DBM = 0

# Display orientation / panel type: same meaning as in the satellite's config.py.
DISPLAY_MADCTL = 0x28
DISPLAY_INVERT = False
