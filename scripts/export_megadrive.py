"""
Export MIDI → Mega Drive VGM (FM + PSG drums; optional BYO PCM).

Usage:
  python scripts/export_megadrive.py assets/midi/biome1_calm.mid
  python scripts/export_megadrive.py assets/midi/biome1_calm.mid --json
  python scripts/export_megadrive.py assets/midi/biome1_calm.mid --dump-voices

Env: NOBU_MIDI_DIR, NOBU_OUTPUT_DIR.
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

from nobu_megadrive import MIDI_DIR, dump_voices, export_midi_to_vgm


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export MIDI → Mega Drive VGM (PSG drums; optional BYO PCM)"
    )
    parser.add_argument("input", help="Path to .mid file")
    parser.add_argument(
        "--out",
        default=None,
        help="Explicit .vgm output path (default: output/audio/{stem}/vgm/{stem}.vgm)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print export result JSON to stdout",
    )
    parser.add_argument(
        "--dump-voices",
        action="store_true",
        help="Print voice assignment JSON and exit (no VGM)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-JSON prints",
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

    if args.dump_voices:
        dump = dump_voices(midi_path)
        print(json.dumps(dump, indent=2))
        return 0

    result = export_midi_to_vgm(midi_path, out_path=args.out)
    if args.json:
        print(json.dumps(result, indent=2))
    elif not args.quiet:
        print(f"Wrote {result['file']} ({result['drums_mode']} drums)")
        if result.get("warnings"):
            for w in result["warnings"]:
                print(f"  warning: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
