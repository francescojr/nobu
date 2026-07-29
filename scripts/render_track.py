"""
Render MIDI → WAV/OGG (chip / hybrid / full SF2 — never hard-fails).

Thin CLI wrapper around nobu_render.render_midi_file().

Usage:
  python scripts/render_track.py assets/midi/biome1_calm.mid
  python scripts/render_track.py assets/midi/biome1_calm.mid --mode chip
  python scripts/render_track.py assets/midi/biome1_calm.mid --mode chip --json
  python scripts/render_track.py assets/midi/biome1_calm.mid --mode hybrid --sf2 path.sf2

Env: NOBU_MIDI_DIR, NOBU_OUTPUT_DIR, NOBU_SF2 (or FLUID_SYNTH_SF2).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nobu_render import MIDI_DIR, OUT_DIR, render_midi_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render MIDI → WAV/OGG (chip / hybrid / full SF2 — never hard-fails)"
    )
    parser.add_argument("input", help="Path to .mid file")
    parser.add_argument(
        "--mode",
        choices=("auto", "chip", "hybrid", "sf2"),
        default="auto",
        help="chip=pure chiptune; hybrid=SF2 drums+chip melodic; "
        "sf2=full SoundFont; auto=best available (default)",
    )
    parser.add_argument(
        "--sf2",
        default=None,
        help="SoundFont path (default: assets/soundfonts/default.sf2 or NOBU_SF2)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Legacy: output path without extension (flat wav+ogg in same dir)",
    )
    parser.add_argument(
        "--loop-beats",
        type=float,
        default=0,
        help="Trim to exact loop length in beats",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print render result JSON to stdout (for agent shell fallback)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress prints (JSON still goes to stdout with --json)",
    )
    args = parser.parse_args()

    midi_path = args.input
    if not os.path.exists(midi_path):
        alt = MIDI_DIR / Path(midi_path).name
        if alt.exists():
            midi_path = str(alt)
        else:
            print(f"File not found: {midi_path}")
            return 1

    stem = os.path.splitext(os.path.basename(midi_path))[0]
    kwargs = {
        "soundfont": args.sf2,
        "loop_beats": args.loop_beats,
        "project_name": stem,
        "quiet": args.quiet or args.json,
    }
    if args.out:
        kwargs["flat_legacy"] = True
        kwargs["legacy_out_base"] = args.out
    else:
        kwargs["output_root"] = OUT_DIR

    result = render_midi_file(midi_path, args.mode, **kwargs)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
