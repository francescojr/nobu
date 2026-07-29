#!/usr/bin/env python3
"""Optional SF2 smoke — skip if FluidSynth or default.sf2 missing. Run from repo root."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import nobu_mcp
import nobu_render


def main() -> int:
    caps = nobu_render.get_render_capabilities_impl()
    if not caps.get("modes_available", {}).get("sf2"):
        print("smoke_sf2: SKIP (FluidSynth or SF2 not available)")
        return 0

    project = "_smoke_sf2"
    nobu_mcp._PROJECTS.clear()
    nobu_mcp.start_project(project, 120)
    nobu_mcp.add_layer(project, "dr", "drums", [["kick", 0, 0.5]])
    nobu_mcp.add_layer(
        project, "bass", "bass", [[36, 0, 2]], chiptune_program="triangle_bass"
    )
    export_json = __import__("json").loads(nobu_mcp.export_midi(project))

    result = nobu_render.render_midi_file(
        export_json["file"],
        "sf2",
        project_name=project,
        quiet=True,
    )
    wav = result.get("wav")
    if result.get("mode_effective") != "sf2":
        print(f"smoke_sf2: FAIL mode_effective={result.get('mode_effective')}")
        return 1
    if not wav or not os.path.isfile(wav):
        print("smoke_sf2: FAIL no wav")
        return 1
    if os.path.getsize(wav) < nobu_render.MIN_AUDIO_BYTES:
        print("smoke_sf2: FAIL tiny wav")
        return 1
    warnings = result.get("quality_warnings") or []
    if warnings:
        print(f"smoke_sf2: FAIL quality_warnings={warnings}")
        return 1

    print("smoke_sf2: OK")
    print(f"  wav: {wav}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
