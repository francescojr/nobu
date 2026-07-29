#!/usr/bin/env python3
"""Smoke test: compose stub + render + path layout. Run from repo root."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import nobu_mcp
import nobu_render


def main() -> int:
    project = "_smoke_test"
    nobu_mcp._PROJECTS.clear()
    nobu_mcp.start_project(project, 120)
    nobu_mcp.add_layer(
        project,
        "drums",
        "drums",
        [["kick", 0.0, 0.5], ["snare", 1.0, 0.5]],
    )
    nobu_mcp.add_layer(
        project,
        "bass",
        "bass",
        [[36, 0.0, 2.0]],
        chiptune_program="triangle_bass",
    )
    export_json = json.loads(nobu_mcp.export_midi(project))
    assert export_json.get("file"), "export_midi failed"

    result = nobu_render.render_midi_file(
        export_json["file"],
        "chip",
        project_name=project,
        quiet=True,
    )
    wav = result.get("wav")
    assert wav and os.path.isfile(wav), f"WAV missing: {wav}"
    assert f"{project}{os.sep}wav" in wav.replace("/", os.sep), f"bad layout: {wav}"

    caps = nobu_render.get_render_capabilities_impl()
    assert caps["modes_available"]["chip"] is True

    print("smoke_render: OK")
    print(f"  wav: {wav}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
