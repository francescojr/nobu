"""
Batch-render .mid -> .ogg/.wav. Three modes (never hard-fails without SF2):

  chip    — pure chiptune via nobu_render.
  sf2     — full SoundFont via FluidSynth. Falls back to chip.
  hybrid  — SF2 drums + chiptune melodic. Falls back to chip.
  auto    — sf2 if FluidSynth+SF2, else chip (batch default).

Usage:
  python scripts/render_midi.py
  python scripts/render_midi.py --mode chip
  python scripts/render_midi.py --mode sf2 --soundfont assets/soundfonts/default.sf2
  python scripts/render_midi.py --mode hybrid

Output: output/audio/{project_name}/wav/ and .../ogg/

Env: NOBU_MIDI_DIR, NOBU_OUTPUT_DIR, NOBU_SF2 (or FLUID_SYNTH_SF2).
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import nobu_render
from nobu_render import (
    MIDI_DIR,
    OUT_DIR,
    find_soundfont,
    get_render_capabilities_impl,
    has_fluidsynth,
    render_midi_file,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch render .mid -> audio (chip / hybrid / full SF2)"
    )
    parser.add_argument("--soundfont", help="Path to .sf2 file")
    parser.add_argument(
        "--mode",
        choices=("auto", "chip", "hybrid", "sf2"),
        default="auto",
        help="chip | hybrid | sf2 | auto (default: sf2 if available else chip)",
    )
    parser.add_argument(
        "--force-chip",
        action="store_true",
        help="Deprecated alias for --mode chip",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help="Single .mid file (default: all .mid in assets/midi/)",
    )
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    if args.input:
        midi_path = Path(args.input)
        if not midi_path.is_absolute():
            midi_path = Path.cwd() / midi_path
        if not midi_path.exists():
            alt = MIDI_DIR / midi_path.name
            if alt.exists():
                midi_path = alt
            else:
                print(f"File not found: {midi_path}")
                return
        midi_files = [str(midi_path)]
    else:
        midi_files = sorted(glob.glob(str(MIDI_DIR / "*.mid")))
        if not midi_files:
            print(f"No .mid files found in {MIDI_DIR}")
            print("Run: python examples/demo_biome_ost.py  (or use the nobu MCP)")
            return

    mode = "chip" if args.force_chip else args.mode
    soundfont = find_soundfont(args.soundfont)

    print(f"Rendering {len(midi_files)} file(s) --mode {mode}")
    if soundfont:
        print(f"Soundfont: {soundfont}")

    ok = 0
    for path in midi_files:
        stem = Path(path).stem
        try:
            result = render_midi_file(
                path,
                mode,
                soundfont=soundfont or None,
                output_root=OUT_DIR,
                project_name=stem,
            )
            if result.get("wav") and os.path.isfile(result["wav"]):
                ok += 1
                print(f"  OK {stem} -> {result['output_dir']}")
            else:
                print(f"  X {stem}: no WAV output")
        except Exception as e:
            print(f"  X {Path(path).name}: {e}")

    print(f"\nDone: {ok}/{len(midi_files)} rendered under {OUT_DIR}")

    caps = get_render_capabilities_impl()
    if mode in ("auto", "chip", "hybrid", "sf2") and not caps["modes_available"].get("sf2"):
        print("Tip: for full SF2 or hybrid drums, add assets/soundfonts/default.sf2")
        print("  https://www.williamkage.com/snes_soundfonts/")
        print("  Then: python scripts/render_midi.py --mode sf2")
        if not has_fluidsynth():
            print("  Install FluidSynth for sf2 mode (see bootstrap / SETUP.md)")


if __name__ == "__main__":
    main()
