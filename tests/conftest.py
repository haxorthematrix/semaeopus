"""
pytest config — make project ROOT and firmware/satellite importable so
tests can pull in the codec, OBC modules, and simulator.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "firmware", "satellite"))
sys.path.insert(0, ROOT)
