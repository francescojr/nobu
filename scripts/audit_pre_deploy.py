#!/usr/bin/env python3
"""Pre-deploy audit — run from repo root."""
from __future__ import annotations

import inspect
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import nobu_mcp
import nobu_render

EXPECTED_TOOLS = [
    "start_project",
    "suggest_scale_for_mood",
    "generate_scale",
    "add_layer",
    "set_tempo_change",
    "list_layers",
    "export_midi",
    "get_render_capabilities",
    "list_soundfonts",
    "render_project",
    "render_chip",
    "render_hybrid",
    "render_sf2",
    "render_all_modes",
]

failures: list[str] = []


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL {msg}")
    failures.append(msg)


print("=== nobu pre-deploy audit ===\n")

# 1. Tools
print("1. MCP tools")
for name in EXPECTED_TOOLS:
    if callable(getattr(nobu_mcp, name, None)):
        ok(name)
    else:
        fail(f"missing tool: {name}")

# 2. Drum schema
print("\n2. add_layer schema")
ann = inspect.signature(nobu_mcp.add_layer).parameters["notes"].annotation
if "str" in str(ann):
    ok(f"notes annotation includes str: {ann}")
else:
    fail(f"notes annotation missing str: {ann}")

nobu_mcp._PROJECTS.clear()
nobu_mcp.start_project("_audit", 120)
nobu_mcp.add_layer("_audit", "dr", "drums", [["kick", 0, 0.5], ["snare", 1, 0.5]])
p0 = nobu_mcp._PROJECTS["_audit"]["tracks"][0]["notes"][0]["pitch"]
p1 = nobu_mcp._PROJECTS["_audit"]["tracks"][0]["notes"][1]["pitch"]
if p0 == 36 and p1 == 38:
    ok(f"kick/snare -> {p0}/{p1}")
else:
    fail(f"drum mapping wrong: {p0}/{p1}")

# 3. Output paths
print("\n3. Output layout")
paths = nobu_render.audio_output_paths(ROOT / "output" / "audio", "boss", "boss_chip")
if paths["wav"].replace("\\", "/").endswith("output/audio/boss/wav/boss_chip.wav"):
    ok("nested wav/ogg layout")
else:
    fail(f"bad layout: {paths}")

legacy = nobu_render.audio_output_paths(
    "", "", "", flat_legacy=True, legacy_out_base=str(ROOT / "tmp" / "out" / "foo")
)
if legacy["wav"].endswith("foo.wav") and legacy["ogg"].endswith("foo.ogg"):
    ok("legacy --out flat paths")
else:
    fail(f"legacy paths broken: {legacy}")

# 4. export_midi next_step
print("\n4. export_midi metadata")
nobu_mcp.add_layer("_audit", "bass", "bass", [[36, 0, 2]], chiptune_program="triangle_bass")
meta = json.loads(nobu_mcp.export_midi("_audit"))
if meta.get("next_step") and "render" in meta["next_step"]:
    ok("export_midi next_step hint")
else:
    fail("export_midi missing next_step")

# 5. Render pipeline
print("\n5. Render pipeline")
result = nobu_render.render_midi_file(meta["file"], "chip", project_name="_audit", quiet=True)
if result.get("wav") and os.path.isfile(result["wav"]):
    ok(f"render_midi_file chip -> {Path(result['wav']).name}")
else:
    fail("render_midi_file produced no wav")

all_modes = json.loads(nobu_mcp.render_all_modes("_audit"))
if len(all_modes.get("modes", {})) == 3:
    ok("render_all_modes returns 3 modes")
else:
    fail(f"render_all_modes modes: {all_modes.get('modes', {}).keys()}")

for mode in ("chip", "hybrid", "sf2"):
    wav = all_modes["modes"][mode].get("wav")
    if wav and os.path.isfile(wav):
        ok(f"{mode} wav exists")
    else:
        fail(f"{mode} wav missing: {wav}")

# 6. Capabilities
print("\n6. Capabilities")
caps = nobu_render.get_render_capabilities_impl()
if caps["modes_available"]["chip"]:
    ok("chip always available")
else:
    fail("chip not available")
if "install_hints" in caps and isinstance(caps["install_hints"], list):
    ok(f"install_hints ({len(caps['install_hints'])} items)")
else:
    fail("install_hints missing")

sf = nobu_render.list_soundfonts_impl()
if "soundfonts" in sf:
    ok("list_soundfonts structure")
else:
    fail("list_soundfonts broken")

# 7. Version sync
print("\n7. Version sync")
pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
if 'version = "0.2.0"' in pyproject and "## [0.2.0]" in changelog:
    ok("pyproject + CHANGELOG 0.2.0")
else:
    fail("version mismatch pyproject/CHANGELOG")

print("\n=== summary ===")
if failures:
    print(f"FAILED ({len(failures)} issues):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("ALL CHECKS PASSED")
sys.exit(0)
