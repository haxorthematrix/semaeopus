"""Smoke test for the GFSK IQ generator."""

import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_verify_iq_modulator_self_check():
    """Regenerate a small IQ blob and assert the modulator passes its
    own structural check (constant envelope + directional bit
    recovery)."""
    result = subprocess.run(
        [sys.executable, "-m", "tools.verify_iq"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: modulator output is well-formed GFSK" in result.stdout


def test_baseline_iq_exists_or_regenerates():
    """The repo ships a pre-generated captures/baseline.iq + .jsonl
    pair so learners can do lessons L01-L04 without hardware. If
    they're missing (e.g. someone just cloned the repo and gitignored
    them), running the generator should reproduce them deterministically.
    """
    iq_path    = os.path.join(ROOT, "captures", "baseline.iq")
    json_path  = os.path.join(ROOT, "captures", "baseline.jsonl")
    if not (os.path.exists(iq_path) and os.path.exists(json_path)):
        result = subprocess.run(
            [sys.executable, "-m", "tools.generate_iq"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    assert os.path.getsize(iq_path) > 1_000_000     # >1 MB of IQ
    with open(json_path) as fp:
        lines = [l for l in fp if l.strip()]
    assert len(lines) >= 8, "expected at least 8 oracle records"
