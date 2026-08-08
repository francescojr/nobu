#!/usr/bin/env python3
"""Pre-deploy audit — run from repo root."""
from __future__ import annotations

import inspect
import json
import os
import subprocess
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
    "get_megadrive_capabilities",
    "export_megadrive",
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
if meta.get("next_step") and "export_megadrive" in meta["next_step"]:
    ok("export_midi next_step mentions export_megadrive")
else:
    fail("export_midi next_step missing export_megadrive")

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
if 'version = "0.3.0"' in pyproject and "## [0.3.0]" in changelog:
    ok("pyproject + CHANGELOG 0.3.0")
else:
    fail("version mismatch pyproject/CHANGELOG")

# 7b. Mega Drive VGM
print("\n7b. Mega Drive VGM")
import nobu_megadrive

md_caps = nobu_megadrive.get_megadrive_capabilities_impl()
if md_caps.get("vgm_export") and "lead" in md_caps.get("builtin_patches", []):
    ok("megadrive capabilities")
else:
    fail(f"megadrive capabilities: {md_caps}")
md_result = json.loads(nobu_mcp.export_megadrive("_audit"))
vgm_path = md_result.get("file", "")
if vgm_path and os.path.isfile(vgm_path):
    magic = Path(vgm_path).read_bytes()[:4]
    if magic == b"Vgm " and os.path.getsize(vgm_path) > 0x40:
        ok(f"export_megadrive -> {Path(vgm_path).name}")
    else:
        fail(f"bad vgm magic/size: {magic} {os.path.getsize(vgm_path)}")
else:
    fail(f"export_megadrive missing file: {md_result}")

# 8. Bootstrap JSON report
print("\n8. Bootstrap JSON")
r = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "bootstrap.py"), "--json", "--no-prompt", "--skip-install"],
    capture_output=True,
    text=True,
    cwd=str(ROOT),
)
if r.returncode != 0:
    fail(f"bootstrap --json failed: {r.stderr[:200]}")
else:
    try:
        boot = json.loads(r.stdout)
    except json.JSONDecodeError:
        fail("bootstrap --json invalid JSON")
    else:
        for key in ("capabilities", "ready_for_audio", "optional_render"):
            if key in boot:
                ok(f"bootstrap report has {key}")
            else:
                fail(f"bootstrap report missing {key}")

# 9. Render benchmark
print("\n9. Render benchmark")
r = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "bench_render.py")],
    capture_output=True,
    text=True,
    cwd=str(ROOT),
)
if r.returncode == 0:
    ok("bench_render under 15s budget")
else:
    fail(f"bench_render: {r.stdout.strip()} {r.stderr.strip()}")

# 10. FluidSynth argv order
print("\n10. FluidSynth argv")
r = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "test_fluidsynth_argv.py")],
    capture_output=True,
    text=True,
    cwd=str(ROOT),
)
if r.returncode == 0:
    ok("fluidsynth -F before sf2/midi")
else:
    fail(f"test_fluidsynth_argv: {r.stdout.strip()} {r.stderr.strip()}")

# 11. Capabilities fluidsynth fields
print("\n11. Capabilities schema")
caps = nobu_render.get_render_capabilities_impl()
for key in ("fluidsynth_path", "fluidsynth_version"):
    if key in caps:
        ok(f"capabilities has {key}")
    else:
        fail(f"capabilities missing {key}")

# 12. Progress scale
print("\n12. Progress scale")
r = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "test_progress_scale.py")],
    capture_output=True,
    text=True,
    cwd=str(ROOT),
)
if r.returncode == 0:
    ok("render_all_modes global progress scale")
else:
    fail(f"test_progress_scale: {r.stdout.strip()} {r.stderr.strip()}")

print("\n=== summary ===")
if failures:
    print(f"FAILED ({len(failures)} issues):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("ALL CHECKS PASSED")
sys.exit(0)
