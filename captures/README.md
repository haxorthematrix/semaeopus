# Captures

Reference recordings used by lessons L01–L04.

## `baseline.iq` (5.4 MB) + `baseline.jsonl`

A deterministic 2.7-second IQ recording of a synthetic Semaeopus
session — BEACON + HK + ADCS + EPS frames — modulated as 2-GFSK at
9600 bps with ±4.8 kHz deviation, sampled at 1 Msps. Format is `.cu8`
(interleaved unsigned 8-bit I,Q), same as `rtl_sdr` capture output.

Open in:
  - `gqrx` — File menu → "I/Q file...", sample rate 1 Msps, mode "Raw I/Q"
  - `inspectrum` (drag-and-drop)
  - GNU Radio — File Source block, type "complex char", repeat off
  - `tools/verify_iq.py` for the modulator smoke test

`baseline.jsonl` is the **oracle**: one line per transmitted frame
with hex bytes and decoded fields. Lessons L03 / L04 use this as a
ground-truth reference for the demod chain you build.

Regenerate with:
```bash
python -m tools.generate_iq
```

The output is deterministic given `--seed`.
