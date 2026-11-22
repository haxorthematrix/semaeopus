"""Fixtures for the firmware tests: stage each build exactly as
tools/deploy.sh would copy it onto a board."""
import importlib.util
import os
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TARGETS = ("cyd-satellite", "cyd-ground", "pico-modem", "pico-satellite")


@pytest.fixture(scope="session")
def staged(tmp_path_factory):
    """Map of deploy target -> directory holding that board's filesystem."""
    root = tmp_path_factory.mktemp("staged")
    out = {}
    for t in TARGETS:
        d = root / t
        subprocess.run([os.path.join(ROOT, "tools", "deploy.sh"), t, "-"],
                       env=dict(os.environ, STAGE_ONLY=str(d)), check=True,
                       stdout=subprocess.DEVNULL)
        out[t] = str(d)
    return out


@pytest.fixture(scope="session")
def sp():
    """Host copy of the protocol codec, loaded under its own module name."""
    path = os.path.join(ROOT, "protocol", "space_packet.py")
    spec = importlib.util.spec_from_file_location("host_space_packet_fw", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
