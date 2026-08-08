# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This project **does not use an `[Unreleased]` section**. Every session with
meaningful changes cuts a new `MAJOR.MINOR.PATCH` entry (via Cursor hooks).

## [0.3.0] — 2026-08-08

### Added

- Mega Drive VGM export library `nobu_megadrive.py` (YM2612 FM + PSG drums)
- MCP tools `get_megadrive_capabilities` and `export_megadrive` (16 tools total)
- CLI `scripts/export_megadrive.py` and smoke `scripts/smoke_megadrive.py`
- Builtin FM patches (`lead` / `bass` / `harmony`) + optional BYO JSON overlays
- Optional BYO PCM drums under `assets/megadrive/pcm/` (SF2-style; not shipped)
- Output path `output/audio/{project}/vgm/{project}.vgm` for SGDK `.res` handoff
- `assets/megadrive/README.md` documenting BYO policy and SGDK XGM usage
- Regression `scripts/test_megadrive_patches.py`

### Changed

- `export_midi` `next_step` mentions Mega Drive / `export_megadrive`
- Agent docs / skill / rules updated for VGM workflow and 16 tools
- `.gitignore` ignores local `assets/megadrive` BYO wav/json (keeps README/gitkeep)

## [0.2.4] — 2026-07-29

### Added

- Global MCP progress in `render_all_modes`: monotonic 0→1 across chip/hybrid/sf2 with `mode_{chip|hybrid|sf2}:{stage}` messages
- Mode boundary pings: `mode_{mode}_start` / `mode_{mode}_done`
- Melodic synthesis sub-progress (~10 pings) during long chip/hybrid renders
- `progress_modes_completed` in `render_all_modes` JSON
- `scripts/test_progress_scale.py` — progress monotonicity regression gate

### Changed

- `_render_project_impl` accepts optional `on_progress` callback (single-mode tools unchanged)

## [0.2.3] — 2026-07-29

### Added

- `resolve_fluidsynth()` with Windows install-path fallbacks + `fluidsynth_path` / `fluidsynth_version` in capabilities JSON
- `build_fluidsynth_cmd()` — `-F` and rate flags before soundfont/MIDI (FluidSynth 2.5.x)
- `quality_warnings` in render JSON when mode fallback or SF2 WAV suspiciously small
- `scripts/test_fluidsynth_argv.py` — argv order regression gate
- `scripts/smoke_sf2.py` — optional SF2 smoke (skips when FluidSynth/SF2 missing)

### Changed

- `export_midi` `next_step` requires `get_render_capabilities()` before hybrid/sf2
- `render_all_modes` aggregates `quality_warnings`; skill/docs require reading `mode_effective`
- Bootstrap doctor banner shows FluidSynth path/version; winget hint to restart MCP session

### Fixed

- Full SF2 render on FluidSynth 2.5.x (Windows): output flags must precede `.sf2` / `.mid` args
- Silent “sf2 success” when FluidSynth missing (actually hybrid/chip) — surfaced via `quality_warnings`

## [0.2.2] — 2026-07-29

### Added

- Numpy-vectorized chip synthesis (drums + melodic) — typical ~6s tracks render in under 1s via MCP
- MCP render progress via `ctx.report_progress` + `render_stages_completed` / `render_duration_sec` in JSON
- `scripts/bench_render.py` — wall-time gate for chip render
- `render_track.py --json` — shell fallback for Kilo `-32001` timeouts

### Changed

- Kilo MCP default timeout: `300000` ms (5 min) in bootstrap + `.kilo/kilo.example.jsonc`
- Render MCP tools use `@mcp.tool(timeout=300)`; prefer **`render_chip`** over `render_all_modes` in skill/docs
- Skill/docs: `-32001` handling, Kilo Network Timeout UI, shell fallback path

### Fixed

- Kilo MCP `render_chip` timing out (-32001) on CPU-bound Python synthesis loops

## [0.2.1] — 2026-07-29

### Added

- Bootstrap welcome banner: READY chip-first messaging, SF2 bring-your-own guidance
- Interactive optional-upgrade menu (tinysoundfont pip, FluidSynth/ffmpeg hints with winget opt-in on Windows)
- Flags: `--no-prompt`, `--with-render`, `--doctor`, `--smoke`
- JSON report fields: `capabilities`, `ready_for_audio`, `smoke_passed`
- `install_hints` in render JSON when `fallback_reason` is set

### Changed

- Bootstrap uses venv subprocess for `get_render_capabilities` (accurate tinysoundfont detection)
- README/AGENTS/SETUP: fastest-path install docs; agents use `--no-prompt`
- `assets/soundfonts/README.md`: numbered bring-your-own SF2 steps (no download script)

## [0.2.0] — 2026-07-29

### Added

- **`nobu_render.py`** — shared render library (CLI + MCP)
- MCP render tools: `render_project`, `render_chip`, `render_hybrid`, `render_sf2`, `render_all_modes`
- MCP discovery: `get_render_capabilities`, `list_soundfonts`
- Kilo MCP timeout 120s for multi-mode renders; `mcp-integration.md` in `instructions`

### Changed

- **Breaking:** audio output layout → `output/audio/{project}/wav/` and `.../ogg/` (no longer flat in `output/audio/`)
- `render_track.py` / `render_midi.py` delegate to `nobu_render`
- `--out` on `render_track.py` keeps legacy flat wav+ogg in same directory

### Fixed

- `add_layer` accepts string drum names (`kick`, `snare`, …) — Pydantic schema aligned with docstring
- `export_midi` docstring says Export (not Render); JSON includes `next_step` for render tools
- Onboarding: Cursor `nobu.mdc`, Kilo rules, Claude `CLAUDE.md`, `--integrate` absolute skill paths
- Docs aligned to nested output layout (`README`, `SETUP`, `production-workflow`, `CONTRIBUTING`, paste prompts)

## [0.1.6] — 2026-07-22

### Fixed

- Changelog hook no longer writes `_Auto-release from session …_` noise
- Skip auto-bump when the agent already cut a matching `CHANGELOG` +
  `pyproject.toml` version (stops double patch like 0.1.5 → junk 0.1.6)
- Resolve session id from `last_session.json` when `stop` omits ids
  (avoids `session unknown` and lost `finalized` state)
- Ignore `pyproject.toml` path noise in auto bullets (version sync is the release)

## [0.1.5] — 2026-07-22

### Added

- README header banner from `assets/images/nobu.png` (GitHub-friendly centered hero)

## [0.1.4] — 2026-07-22

### Fixed

- Full SF2 render no longer uses FluidSynth `-O s3m` (invalid: `-O` is sample
  format, not OGG). Always render WAV, then convert to OGG via `ffmpeg`
  (Windows-safe); validate file size / FluidSynth stderr even when exit is 0
- `render_midi` SF2/auto path delegates to `render_track` so both share one
  FluidSynth → WAV → OGG implementation
- Cursor project hooks failed to load: `loop_limit: 0` is invalid — use `null`
  (or a positive integer). Log showed the entire `.cursor/hooks.json` rejected

### Changed

- `render_track` chip/hybrid OGG export prefers `ffmpeg` after WAV (avoids
  Windows libsndfile Vorbis crashes that left ~4 KB stub files)
- Bootstrap `--json` reports optional render health: `fluidsynth`, `ffmpeg`,
  `sf2_found`, `tinysoundfont` (does not affect `ok`)
- Docs (README / AGENTS / SETUP / CONTRIBUTING / requirements / mcp-integration
  / soundfonts README) aligned with WAV→OGG path, ffmpeg on Windows, and the
  hooks `loop_limit` gotcha

### Added

- Project Cursor rules: `.cursor/rules/karpathy-guidelines.mdc` and
  `.cursor/rules/clean-code.mdc` (`alwaysApply: true`, project-agnostic)

## [0.1.3] — 2026-07-21

### Changed

- `.kilo/kilo.jsonc` is gitignored like `.mcp.json` / `.cursor/mcp.json` so
  `git add -A` cannot commit machine-local venv paths; template remains
  `.kilo/kilo.example.jsonc` (bootstrap regenerates the local file)

## [0.1.2] — 2026-07-21

### Added

- Bootstrap writes project-local `.cursor/mcp.json` (Cursor’s current MCP path),
  still alongside legacy `.mcp.json` — never touches global `~/.cursor/mcp.json`

### Changed

- Docs (README / AGENTS / SETUP) spell out Cursor’s one-time “enable nobu” toggle
- Changelog hook: `sessionStart` is baseline-only; version cuts happen on `stop`
  (agent turn end) or `sessionEnd` — ambiguous payloads no longer auto-version
- Stop tracking `.mcp.json` in git (generated locally; use `.mcp.example.json`)

## [0.1.1] — 2026-07-21

### Added

- Explicit render modes on `scripts/render_midi.py` and `scripts/render_track.py`:
  `chip` (pure chiptune), `hybrid` (SF2 drums + chiptune melodic),
  `sf2` (full SoundFont via FluidSynth), and `auto` (best available)
- Cursor session hooks to auto-version this changelog (`.cursor/hooks.json`)

### Deprecated

- `render_midi.py --force-chip` (use `--mode chip`)

### Fixed

- `render_track.py` no longer hard-fails without a `.sf2`; missing SF2 / FluidSynth /
  tinysoundfont now degrade to pure chiptune (or hybrid to chip drums) instead of exiting

## [0.1.0] — 2026-07-21

Initial public release of **nobu** as a game-agnostic MCP toolkit for
chiptune / retro MIDI composition and game audio rendering.

### Added

- MCP server `nobu` (`nobu_mcp.py`) with English tool API:
  `start_project`, `suggest_scale_for_mood`, `generate_scale`, `add_layer`,
  `set_tempo_change`, `list_layers`, `export_midi`
- Mood → scale mapping (English keys + Portuguese aliases)
- Drum piece names in English with Portuguese aliases (GM map)
- Default MIDI export directory: `assets/midi/` (`NOBU_MIDI_DIR` override)
- Folder conventions: `assets/midi/`, `assets/soundfonts/`, `output/audio/`
- Render scripts: `scripts/render_midi.py`, `scripts/render_track.py`
  (`NOBU_OUTPUT_DIR`, `NOBU_SF2` / `FLUID_SYNTH_SF2`)
- Agent-friendly bootstrap: `scripts/bootstrap.py` (venv, deps, local `.mcp.json`,
  `--integrate`, `--json`)
- Agent docs: `AGENTS.md`, `.cursor/rules/nobu.mdc`, `.mcp.example.json`
- Skill pack: `.claude/skills/game-music-producer/` (bilingual SETUP for
  Cursor / Claude Desktop / Kilo Code)
- Demo OST generator: `examples/demo_biome_ost.py` (generic biomes, no game coupling)
- Packaging: `pyproject.toml`, `requirements.txt`, MIT `LICENSE`
- Community docs: `README.md` (EN + PT), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`

### Notes

- SoundFonts (`.sf2`) are **not** redistributed; place them under
  `assets/soundfonts/` (see that folder’s README).
- Local `.mcp.json` is generated by bootstrap and gitignored; use
  `.mcp.example.json` as the portable template.

[0.2.4]: https://github.com/francescojr/nobu/releases/tag/v0.2.4
[0.2.3]: https://github.com/francescojr/nobu/releases/tag/v0.2.3
[0.2.2]: https://github.com/francescojr/nobu/releases/tag/v0.2.2
[0.2.1]: https://github.com/francescojr/nobu/releases/tag/v0.2.1
[0.2.0]: https://github.com/francescojr/nobu/releases/tag/v0.2.0
[0.1.6]: https://github.com/francescojr/nobu/releases/tag/v0.1.6
[0.1.5]: https://github.com/francescojr/nobu/releases/tag/v0.1.5
[0.1.4]: https://github.com/francescojr/nobu/releases/tag/v0.1.4
[0.1.3]: https://github.com/francescojr/nobu/releases/tag/v0.1.3
[0.1.2]: https://github.com/francescojr/nobu/releases/tag/v0.1.2
[0.1.1]: https://github.com/francescojr/nobu/releases/tag/v0.1.1
[0.1.0]: https://github.com/francescojr/nobu/releases/tag/v0.1.0
