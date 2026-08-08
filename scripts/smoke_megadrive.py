#!/usr/bin/env python3
"""End-to-end Mega Drive VGM export smoke (no BYO PCM required)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import nobu_mcp
import nobu_megadrive


def main() -> int:
    project = "_smoke_megadrive"
    nobu_mcp._PROJECTS.clear()
    nobu_mcp.start_project(project, 140)
    nobu_mcp.add_layer(
        project,
        "lead",
        "melody",
        [[60, 0, 1], [64, 1, 1], [67, 2, 1], [72, 3, 2]],
        chiptune_program="pulse_lead",
    )
    nobu_mcp.add_layer(
        project,
        "bass",
        "bass",
        [[36, 0, 2], [36, 2, 2], [38, 4, 2]],
        chiptune_program="triangle_bass",
    )
    nobu_mcp.add_layer(
        project,
        "drums",
        "drums",
        [
            ["kick", 0, 0.5],
            ["snare", 1, 0.5],
            ["closed_hihat", 0.5, 0.25],
            ["closed_hihat", 1.5, 0.25],
            ["kick", 2, 0.5],
            ["snare", 3, 0.5],
        ],
    )
    meta = json.loads(nobu_mcp.export_midi(project))
    midi_path = meta["file"]
    if "export_megadrive" not in meta.get("next_step", ""):
        print("FAIL export_midi next_step missing export_megadrive")
        return 1
    print("OK  export_midi next_step mentions export_megadrive")

    caps = nobu_megadrive.get_megadrive_capabilities_impl()
    if not caps.get("vgm_export"):
        print("FAIL capabilities vgm_export")
        return 1
    print("OK  get_megadrive_capabilities_impl")

    result = json.loads(nobu_mcp.export_megadrive(project))
    vgm = result["file"]
    if not os.path.isfile(vgm):
        print(f"FAIL missing vgm: {vgm}")
        return 1
    data = Path(vgm).read_bytes()
    if data[:4] != b"Vgm ":
        print(f"FAIL bad magic: {data[:4]!r}")
        return 1
    if len(data) <= 0x40:
        print(f"FAIL vgm too small: {len(data)}")
        return 1
    if result.get("drums_mode") != "psg":
        print(f"FAIL expected drums_mode=psg got {result.get('drums_mode')}")
        return 1
    if not result.get("fm_channels_used"):
        print("FAIL no FM channels")
        return 1
    if not result.get("psg_fallback_hits") and not result.get("pcm_hits"):
        # With drums in the project we should have recorded PSG hits
        print(f"FAIL no drum hits recorded: {result}")
        return 1
    print(f"OK  VGM {Path(vgm).name} size={len(data)} drums={result['drums_mode']}")
    print(f"OK  patches={result['patches_used']} fm={result['fm_channels_used']}")
    print("smoke_megadrive passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
