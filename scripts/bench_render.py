#!/usr/bin/env python3
"""Benchmark chip render speed (~6s fixture). Run from repo root."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import nobu_mcp
import nobu_render

MAX_WALL_SEC = 15.0
PROJECT = "_bench_render"


def _build_fixture() -> str:
    nobu_mcp._PROJECTS.clear()
    nobu_mcp.start_project(PROJECT, 160)
    drums = []
    for beat in range(24):
        t = beat * 0.375
        drums.append(["kick", t, 0.25])
        if beat % 2 == 1:
            drums.append(["snare", t, 0.25])
        if beat % 4 == 2:
            drums.append(["hihat", t + 0.125, 0.125])
    nobu_mcp.add_layer(PROJECT, "drums", "drums", drums)
    bass = [[36 + (i % 5), i * 0.75, 0.5] for i in range(32)]
    nobu_mcp.add_layer(
        PROJECT, "bass", "bass", bass, chiptune_program="triangle_bass"
    )
    melody = [[60 + (i % 8), i * 0.375, 0.35] for i in range(64)]
    nobu_mcp.add_layer(
        PROJECT, "melody", "melody", melody, chiptune_program="pulse_lead"
    )
    export_json = json.loads(nobu_mcp.export_midi(PROJECT))
    return export_json["file"]


def main() -> int:
    midi_path = _build_fixture()
    t0 = time.perf_counter()
    result = nobu_render.render_midi_file(
        midi_path, "chip", project_name=PROJECT, quiet=True
    )
    elapsed = time.perf_counter() - t0
    wav = result.get("wav")
    if not wav or not os.path.isfile(wav):
        print(f"bench_render: FAIL no wav ({elapsed:.2f}s)")
        return 1
    stages = result.get("render_stages_completed") or []
    print(f"bench_render: OK in {elapsed:.2f}s")
    print(f"  wav: {wav}")
    print(f"  stages: {', '.join(stages)}")
    if elapsed > MAX_WALL_SEC:
        print(f"bench_render: FAIL exceeded {MAX_WALL_SEC}s budget")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
