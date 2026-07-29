#!/usr/bin/env python3
"""
Idempotent nobu setup. Agents: run with --no-prompt (no interactive menu).

Usage:
  python scripts/bootstrap.py
  python scripts/bootstrap.py --no-prompt
  python scripts/bootstrap.py --json
  python scripts/bootstrap.py --with-render --no-prompt
  python scripts/bootstrap.py --doctor
  python scripts/bootstrap.py --smoke --no-prompt
  python scripts/bootstrap.py --integrate /path/to/your/game

What it does:
  1. Checks Python >= 3.10
  2. Ensures assets/midi, assets/soundfonts, output/audio exist
  3. Creates .venv if missing
  4. pip install -r requirements.txt into that venv
  5. Verifies imports (fastmcp, midiutil, mido, numpy, soundfile)
  6. Prints MCP config snippet with absolute paths
  7. With --integrate: merges "nobu" into that project's .cursor/mcp.json
     (and legacy .mcp.json for Claude Desktop / older clients)
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIN_PY = (3, 10)
TINYSOUNDFONT_VERSION = "0.3.7"
REQUIRED_PKGS = ("fastmcp", "midiutil", "mido", "numpy", "soundfile")
DIRS = (
    REPO_ROOT / "assets" / "midi",
    REPO_ROOT / "assets" / "soundfonts",
    REPO_ROOT / "output" / "audio",
)


def venv_python() -> Path:
    if platform.system() == "Windows":
        return REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    return REPO_ROOT / ".venv" / "bin" / "python"


def venv_pip() -> list[str]:
    return [str(venv_python()), "-m", "pip"]


def ensure_python_version() -> None:
    if sys.version_info < MIN_PY:
        raise SystemExit(
            f"Python {MIN_PY[0]}.{MIN_PY[1]}+ required; "
            f"found {sys.version_info.major}.{sys.version_info.minor}"
        )


def ensure_dirs() -> list[str]:
    created = []
    for d in DIRS:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(str(d))
    return created


def ensure_venv() -> bool:
    py = venv_python()
    if py.exists():
        return False
    subprocess.run(
        [sys.executable, "-m", "venv", str(REPO_ROOT / ".venv")],
        check=True,
    )
    return True


def pip_install() -> None:
    subprocess.run(
        [*venv_pip(), "install", "--upgrade", "pip"],
        check=True,
        cwd=str(REPO_ROOT),
    )
    subprocess.run(
        [*venv_pip(), "install", "-r", str(REPO_ROOT / "requirements.txt")],
        check=True,
        cwd=str(REPO_ROOT),
    )


def verify_imports() -> dict[str, bool]:
    results = {}
    py = str(venv_python())
    for pkg in REQUIRED_PKGS:
        r = subprocess.run(
            [py, "-c", f"import {pkg}"],
            capture_output=True,
            text=True,
        )
        results[pkg] = r.returncode == 0
    r = subprocess.run(
        [py, "-c", "import nobu_mcp; print(nobu_mcp.mcp.name)"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    results["nobu_mcp"] = r.returncode == 0 and "nobu" in (r.stdout or "")
    r2 = subprocess.run(
        [py, "-c", "import nobu_render; print('ok')"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    results["nobu_render"] = r2.returncode == 0
    return results


def get_capabilities_via_venv() -> dict:
    """Run get_render_capabilities_impl inside the venv (accurate tinysoundfont check)."""
    py = venv_python()
    if not py.exists():
        return {}
    script = (
        "import json, nobu_render; "
        "print(json.dumps(nobu_render.get_render_capabilities_impl()))"
    )
    r = subprocess.run(
        [str(py), "-c", script],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if r.returncode != 0:
        return {}
    try:
        return json.loads(r.stdout.strip())
    except json.JSONDecodeError:
        return {}


def optional_render_from_caps(caps: dict) -> dict:
    """Backward-compatible booleans for --json consumers."""
    return {
        "fluidsynth": bool(caps.get("fluidsynth")),
        "ffmpeg": bool(caps.get("ffmpeg")),
        "sf2_found": bool(caps.get("sf2_found")),
        "tinysoundfont": bool(caps.get("tinysoundfont")),
    }


def pip_install_tinysoundfont() -> bool:
    if not venv_python().exists():
        return False
    r = subprocess.run(
        [
            *venv_pip(),
            "install",
            f"tinysoundfont=={TINYSOUNDFONT_VERSION}",
        ],
        cwd=str(REPO_ROOT),
    )
    return r.returncode == 0


def run_smoke_test() -> bool | None:
    py = venv_python()
    if not py.exists():
        return None
    r = subprocess.run(
        [str(py), str(REPO_ROOT / "scripts" / "smoke_render.py")],
        cwd=str(REPO_ROOT),
    )
    return r.returncode == 0


def _mode_label(available: bool, ready_text: str, needs_text: str) -> str:
    return f"[ready]" if available else f"[needs {needs_text}]"


def _print_system_install_hint(tool: str) -> None:
    system = platform.system()
    if tool == "fluidsynth":
        if system == "Windows":
            print("  winget install FluidSynth.FluidSynth")
            print("  Then restart Kilo / MCP session so PATH picks up FluidSynth.")
        elif system == "Darwin":
            print("  brew install fluidsynth")
        else:
            print("  sudo apt install fluidsynth   # or your distro equivalent")
    elif tool == "ffmpeg":
        if system == "Windows":
            print("  winget install Gyan.FFmpeg")
        elif system == "Darwin":
            print("  brew install ffmpeg")
        else:
            print("  sudo apt install ffmpeg")


def _offer_winget(package_id: str, label: str) -> None:
    if platform.system() != "Windows" or not shutil.which("winget"):
        _print_system_install_hint(label)
        return
    answer = input(f"  Try winget install {package_id}? [y/N] ").strip().lower()
    if answer != "y":
        _print_system_install_hint(label)
        return
    r = subprocess.run(
        ["winget", "install", "--id", package_id, "-e", "--accept-package-agreements"],
        cwd=str(REPO_ROOT),
    )
    if r.returncode != 0:
        print("  winget failed - install manually:")
        _print_system_install_hint(label)
        return
    if label == "fluidsynth":
        print("  Restart Kilo / MCP session so PATH picks up FluidSynth.")


def run_optional_install_menu(caps: dict) -> dict:
    """Interactive optional upgrades; no-op when stdin is not a TTY."""
    if not sys.stdin.isatty():
        return caps

    tsf_ok = caps.get("tinysoundfont", False)
    fs_ok = caps.get("fluidsynth", False)
    ff_ok = caps.get("ffmpeg", False)
    needs = not tsf_ok or not fs_ok or (platform.system() == "Windows" and not ff_ok)
    if not needs:
        print("\nOptional upgrades: all detected - skipping menu.")
        return caps

    print("\n--- Optional upgrades (chip already works) ---")
    print("Select numbers separated by commas, or Enter to skip:\n")
    if not tsf_ok:
        print("  [1] tinysoundfont (hybrid drums)  -> pip install in venv")
    if not fs_ok:
        print("  [2] FluidSynth (full SF2 mode)    -> system install")
    if platform.system() == "Windows" and not ff_ok:
        print("  [3] ffmpeg (WAV->OGG on Windows)   -> system install")
    if not tsf_ok:
        print("  [a] All pip optionals ([1])")
    print("  [Enter] Continue - chip is already ready\n")

    choice = input("Choice: ").strip().lower()
    if not choice:
        return caps

    selections = set(choice.replace(" ", "").split(","))
    if "a" in selections:
        selections.add("1")

    before = dict(caps.get("modes_available") or {})

    if "1" in selections and not tsf_ok:
        print("\nInstalling tinysoundfont...")
        if pip_install_tinysoundfont():
            print("  tinysoundfont installed.")
        else:
            print("  tinysoundfont install failed - try manually:")
            print(f"  .venv/Scripts/pip install tinysoundfont=={TINYSOUNDFONT_VERSION}")

    if "2" in selections and not fs_ok:
        print("\nFluidSynth:")
        _offer_winget("FluidSynth.FluidSynth", "fluidsynth")

    if "3" in selections and platform.system() == "Windows" and not ff_ok:
        print("\nffmpeg:")
        _offer_winget("Gyan.FFmpeg", "ffmpeg")

    caps = get_capabilities_via_venv()
    after = caps.get("modes_available") or {}
    for mode in ("chip", "hybrid", "sf2"):
        if before.get(mode) != after.get(mode):
            state = "available" if after.get(mode) else "unavailable"
            print(f"  {mode}: now {state}")
    return caps


def print_welcome_banner(report: dict) -> None:
    caps = report.get("capabilities") or {}
    modes = caps.get("modes_available") or {}

    print("=== nobu ===\n")
    if all(report["imports"].values()):
        print("READY - chip compose + render works now (no SF2 required)\n")
    else:
        print("INCOMPLETE - fix failed imports below\n")

    print("Modes available:")
    print(
        f"  chip    {_mode_label(modes.get('chip', True), 'ready', '')}"
    )
    print(
        f"  hybrid  {_mode_label(modes.get('hybrid'), 'ready', 'tinysoundfont + your .sf2')}"
    )
    print(
        f"  sf2     {_mode_label(modes.get('sf2'), 'ready', 'FluidSynth + your .sf2')}"
    )

    fs_path = caps.get("fluidsynth_path")
    fs_ver = caps.get("fluidsynth_version")
    if fs_path:
        print(f"\nFluidSynth CLI: {fs_path}")
        if fs_ver:
            print(f"  {fs_ver}")
    elif not modes.get("sf2"):
        print("\nFluidSynth: not found — sf2 mode will fall back to hybrid/chip")

    print("\nYour SF2 (optional - unlocks hybrid/sf2):")
    print(f"  Place your file at: {REPO_ROOT / 'assets' / 'soundfonts' / 'default.sf2'}")
    print("  Or set NOBU_SF2=/path/to/yours.sf2")
    print("  See: assets/soundfonts/README.md")
    print("  (Repo ships no soundfonts - chip always works without one.)")

    hints = caps.get("install_hints") or []
    if hints:
        print("\nOptional upgrades:")
        for i, hint in enumerate(hints, 1):
            print(f"  {i}. {hint}")

    smoke = report.get("smoke_passed")
    if smoke is True:
        print("\nSmoke test: PASS (compose + chip render verified)")
    elif smoke is False:
        print("\nSmoke test: FAIL - run: python scripts/bootstrap.py --smoke --no-prompt")


def mcp_server_entry() -> dict:
    """Cursor / Claude Desktop shape: command + args."""
    py = venv_python()
    server = REPO_ROOT / "nobu_mcp.py"
    return {
        "command": str(py.resolve()),
        "args": [str(server.resolve())],
    }


def kilo_mcp_entry() -> dict:
    """Kilo Code v7+ shape: type local + command array."""
    py = venv_python()
    server = REPO_ROOT / "nobu_mcp.py"
    return {
        "type": "local",
        "command": [str(py.resolve()), str(server.resolve())],
        "enabled": True,
        "timeout": 300000,
    }


def mcp_config_snippet() -> dict:
    return {"mcpServers": {"nobu": mcp_server_entry()}}


def kilo_config_snippet() -> dict:
    return {
        "instructions": [
            "AGENTS.md",
            "CLAUDE.md",
            ".claude/skills/game-music-producer/SKILL.md",
            ".claude/skills/game-music-producer/references/mcp-integration.md",
            ".kilo/rules/nobu.md",
        ],
        "mcp": {"nobu": kilo_mcp_entry()},
    }


def write_kilo_config() -> Path:
    """Rewrite .kilo/kilo.jsonc with absolute venv paths for this machine."""
    kilo_dir = REPO_ROOT / ".kilo"
    kilo_dir.mkdir(parents=True, exist_ok=True)
    path = kilo_dir / "kilo.jsonc"
    body = json.dumps(kilo_config_snippet(), indent=2, ensure_ascii=False)
    path.write_text(
        "// Generated by scripts/bootstrap.py (venv absolute paths).\n"
        "// Gitignored — portable template: .kilo/kilo.example.jsonc\n"
        "// Same for .mcp.json / .cursor/mcp.json (.mcp.example.json).\n"
        + body
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_cursor_mcp(mcp_path: Path, entry: dict) -> None:
    """Merge nobu into a Cursor mcp.json (create or update). Project-scoped only."""
    data: dict = {"mcpServers": {}}
    if mcp_path.exists():
        try:
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SystemExit(f"Invalid JSON in {mcp_path}: {e}") from e
        data.setdefault("mcpServers", {})
    data["mcpServers"]["nobu"] = entry
    mcp_path.parent.mkdir(parents=True, exist_ok=True)
    mcp_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _integrate_instruction_paths(target_dir: Path, instr: list) -> None:
    """Append nobu skill/rules via absolute paths when missing in target."""
    abs_items = [
        str(REPO_ROOT / "AGENTS.md"),
        str(REPO_ROOT / ".claude/skills/game-music-producer/SKILL.md"),
        str(
            REPO_ROOT
            / ".claude/skills/game-music-producer/references/mcp-integration.md"
        ),
        str(REPO_ROOT / ".kilo/rules/nobu.md"),
    ]
    rel_items = [
        "AGENTS.md",
        ".claude/skills/game-music-producer/SKILL.md",
        ".claude/skills/game-music-producer/references/mcp-integration.md",
        ".kilo/rules/nobu.md",
    ]
    for rel, abs_path in zip(rel_items, abs_items):
        if rel in instr or abs_path in instr:
            continue
        if rel == "AGENTS.md" and not (target_dir / "AGENTS.md").exists():
            if Path(abs_path).exists():
                instr.append(abs_path)
            continue
        if rel.startswith(".claude/") and (
            target_dir / ".claude/skills/game-music-producer/SKILL.md"
        ).exists():
            if rel not in instr:
                instr.append(rel)
            continue
        if Path(abs_path).exists():
            instr.append(abs_path)


def _write_integrate_cursor_rule(target_dir: Path) -> str | None:
    rule_path = target_dir / ".cursor" / "rules" / "nobu.mdc"
    if rule_path.exists():
        return None
    src = REPO_ROOT / ".cursor" / "rules" / "nobu.mdc"
    if not src.exists():
        return None
    rule_path.parent.mkdir(parents=True, exist_ok=True)
    rule_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return str(rule_path)


def integrate_mcp(target_dir: Path) -> list[str]:
    """Merge nobu into target project's Cursor + Kilo configs (never global)."""
    target_dir = target_dir.resolve()
    if not target_dir.is_dir():
        raise SystemExit(f"Not a directory: {target_dir}")

    written: list[str] = []
    entry = mcp_server_entry()

    # Cursor project scope: .cursor/mcp.json (current) + legacy root .mcp.json
    for mcp_path in (
        target_dir / ".cursor" / "mcp.json",
        target_dir / ".mcp.json",
    ):
        _write_cursor_mcp(mcp_path, entry)
        written.append(str(mcp_path))

    # Kilo Code v7+
    kilo_dir = target_dir / ".kilo"
    kilo_dir.mkdir(parents=True, exist_ok=True)
    kilo_path = kilo_dir / "kilo.jsonc"
    kilo_data: dict = {}
    if kilo_path.exists():
        raw = kilo_path.read_text(encoding="utf-8")
        # Strip // line comments for parse
        stripped = "\n".join(
            ln
            for ln in raw.splitlines()
            if not ln.strip().startswith("//")
        )
        try:
            kilo_data = json.loads(stripped) if stripped.strip() else {}
        except json.JSONDecodeError as e:
            raise SystemExit(f"Invalid JSONC in {kilo_path}: {e}") from e
    kilo_data.setdefault("mcp", {})
    kilo_data["mcp"]["nobu"] = kilo_mcp_entry()
    instr = kilo_data.setdefault("instructions", [])
    _integrate_instruction_paths(target_dir, instr)
    kilo_path.write_text(
        "// Merged by nobu scripts/bootstrap.py --integrate\n"
        + json.dumps(kilo_data, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    written.append(str(kilo_path))

    rule_written = _write_integrate_cursor_rule(target_dir)
    if rule_written:
        written.append(rule_written)

    return written


def print_human(report: dict) -> None:
    print_welcome_banner(report)
    print(f"\nRepo:     {report['repo_root']}")
    print(f"Python:   {report['python']}")
    print(f"Venv:     {report['venv_python']}")
    print(f"Created:  {', '.join(report['dirs_created']) or '(none)'}")
    print(f"Venv new: {report['venv_created']}")
    print("Imports:")
    for name, ok in report["imports"].items():
        print(f"  {'OK' if ok else 'FAIL':4} {name}")
    opt = report.get("optional_render") or {}
    if opt:
        print("Optional render:")
        for name, ok in opt.items():
            print(f"  {'yes' if ok else 'no':4} {name}")
    print()
    if report.get("cursor_mcp_path"):
        print(f"MCP config written: {report['cursor_mcp_path']}")
    if report.get("kilo_config_path"):
        print(f"Kilo config written: {report['kilo_config_path']}")
    if report.get("integrated_mcp"):
        print(f"Integrated into: {report['integrated_mcp']}")
    print()
    if all(report["imports"].values()):
        print("Next:")
        print("  1. Reload window -> enable nobu once (Settings -> MCP)")
        print("  2. Kilo: set MCP Network Timeout to 5 min if render times out")
        print("  3. Ask your agent for music, or run:")
        print("     python scripts/bootstrap.py --smoke --no-prompt")
        print("  Skill: .claude/skills/game-music-producer/")
        print("  Output: output/audio/{project}/wav/ and .../ogg/")
    else:
        print("Status: INCOMPLETE - fix failed imports and re-run bootstrap.")
        sys.exit(1)


def build_report(
    *,
    imports: dict[str, bool],
    skip_install: bool,
    venv_created: bool,
    dirs_created: list[str],
    integrated: list[str] | None,
    cursor_mcp_path: str | None,
    kilo_cfg: str | None,
    capabilities: dict,
    smoke_passed: bool | None,
) -> dict:
    optional = optional_render_from_caps(capabilities)
    modes = capabilities.get("modes_available") or {}
    return {
        "ok": all(imports.values()) if not skip_install else True,
        "ready_for_audio": bool(modes.get("chip", True)),
        "repo_root": str(REPO_ROOT),
        "python": sys.version.split()[0],
        "venv_python": str(venv_python()),
        "venv_created": venv_created,
        "dirs_created": dirs_created,
        "imports": imports,
        "optional_render": optional,
        "capabilities": capabilities,
        "smoke_passed": smoke_passed,
        "mcp_config": mcp_config_snippet(),
        "cursor_mcp_path": cursor_mcp_path,
        "kilo_config": kilo_config_snippet() if venv_python().exists() else None,
        "kilo_config_path": kilo_cfg,
        "skill_path": str(
            REPO_ROOT / ".claude" / "skills" / "game-music-producer"
        ),
        "integrated_mcp": integrated,
        "next_steps": [
            "Reload Window (project .cursor/mcp.json — never global ~/.cursor/mcp.json)",
            "Cursor: enable 'nobu' once under Settings → MCP if it appears disabled (Cursor default)",
            "Kilo: Settings → Agent Behaviour → MCP Servers (uses .kilo/kilo.jsonc)",
            "Confirm server 'nobu' exposes compose + render tools (see AGENTS.md)",
            "After compose: render_project or render_all_modes for audio delivery",
            "Read .claude/skills/game-music-producer/SKILL.md when composing",
            "Prove audio: python scripts/bootstrap.py --smoke --no-prompt",
            "Optional upgrades: python scripts/bootstrap.py --with-render --no-prompt",
            "Re-check deps: python scripts/bootstrap.py --doctor",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap nobu for agent/human use")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON report only",
    )
    parser.add_argument(
        "--integrate",
        metavar="DIR",
        help="Merge nobu MCP entry into DIR/.mcp.json (absolute venv + script paths)",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Only create dirs / print MCP config (no pip)",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Skip interactive optional-upgrade menu (use for agents/CI)",
    )
    parser.add_argument(
        "--with-render",
        action="store_true",
        help="Install tinysoundfont in venv (hybrid mode) without prompting",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Re-check render capabilities only (no pip install, no menu)",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run end-to-end compose+chip render smoke test after setup",
    )
    args = parser.parse_args()

    if args.doctor:
        args.skip_install = True
        args.no_prompt = True

    ensure_python_version()
    dirs_created = ensure_dirs()
    venv_created = False
    if not args.skip_install:
        venv_created = ensure_venv()
        pip_install()
        imports = verify_imports()
    else:
        imports = {p: False for p in REQUIRED_PKGS}
        imports["nobu_mcp"] = (REPO_ROOT / "nobu_mcp.py").exists()
        if venv_python().exists():
            imports = verify_imports()

    if args.with_render and venv_python().exists():
        caps_pre = get_capabilities_via_venv()
        if not caps_pre.get("tinysoundfont"):
            pip_install_tinysoundfont()

    integrated = None
    if args.integrate:
        integrated = integrate_mcp(Path(args.integrate))

    kilo_cfg = None
    cursor_mcp_path = None
    if venv_python().exists():
        snippet = json.dumps(mcp_config_snippet(), indent=2) + "\n"
        (REPO_ROOT / ".mcp.json").write_text(snippet, encoding="utf-8")
        cursor_mcp = REPO_ROOT / ".cursor" / "mcp.json"
        cursor_mcp.parent.mkdir(parents=True, exist_ok=True)
        cursor_mcp.write_text(snippet, encoding="utf-8")
        cursor_mcp_path = str(cursor_mcp)
        kilo_cfg = str(write_kilo_config())

    capabilities = get_capabilities_via_venv()
    interactive = (
        sys.stdin.isatty()
        and not args.json
        and not args.no_prompt
        and venv_python().exists()
    )
    if interactive:
        capabilities = run_optional_install_menu(capabilities)

    smoke_passed: bool | None = None
    if args.smoke:
        smoke_passed = run_smoke_test()

    report = build_report(
        imports=imports,
        skip_install=args.skip_install,
        venv_created=venv_created,
        dirs_created=dirs_created,
        integrated=integrated,
        cursor_mcp_path=cursor_mcp_path,
        kilo_cfg=kilo_cfg,
        capabilities=capabilities,
        smoke_passed=smoke_passed,
    )

    if args.json:
        print(json.dumps(report, indent=2))
        if not report["ok"]:
            sys.exit(1)
    else:
        print_human(report)


if __name__ == "__main__":
    main()
