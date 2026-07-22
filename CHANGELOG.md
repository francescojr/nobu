# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This project **does not use an `[Unreleased]` section**. Every session with
meaningful changes cuts a new `MAJOR.MINOR.PATCH` entry (via Cursor hooks).

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

[0.1.6]: https://github.com/francescojr/nobu/releases/tag/v0.1.6
[0.1.5]: https://github.com/francescojr/nobu/releases/tag/v0.1.5
[0.1.4]: https://github.com/francescojr/nobu/releases/tag/v0.1.4
[0.1.3]: https://github.com/francescojr/nobu/releases/tag/v0.1.3
[0.1.2]: https://github.com/francescojr/nobu/releases/tag/v0.1.2
[0.1.1]: https://github.com/francescojr/nobu/releases/tag/v0.1.1
[0.1.0]: https://github.com/francescojr/nobu/releases/tag/v0.1.0
