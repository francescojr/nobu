#!/usr/bin/env python3
"""Regression: FluidSynth argv order (-F before sf2/midi). Run from repo root."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import nobu_render


def main() -> int:
    cmd = nobu_render.build_fluidsynth_cmd(
        "/sf2/default.sf2",
        "/midi/track.mid",
        "/out/track.wav",
        fluidsynth_exe="/usr/bin/fluidsynth",
    )
    sf2_idx = cmd.index("/sf2/default.sf2")
    midi_idx = cmd.index("/midi/track.mid")
    f_idx = cmd.index("-F")
    if not (f_idx < sf2_idx < midi_idx):
        print(f"test_fluidsynth_argv: FAIL bad order: {cmd}")
        return 1
    if cmd[f_idx + 1] != "/out/track.wav":
        print(f"test_fluidsynth_argv: FAIL -F target: {cmd}")
        return 1
    print("test_fluidsynth_argv: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
