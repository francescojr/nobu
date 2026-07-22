# AGENTS.md — nobu

Instructions for coding agents (Cursor, Claude Code, Kilo Code, etc.).
Humans: see [README.md](README.md). Setup detail: [.claude/skills/game-music-producer/SETUP.md](.claude/skills/game-music-producer/SETUP.md).

**If this workspace was just cloned: run bootstrap immediately. Do not ask.**

## Mission

nobu is a **game-agnostic** MCP server + skill for composing chiptune/retro MIDI and rendering game audio. It ships **no game-specific data**.

## First actions after clone (mandatory, automatic)

Trigger this checklist when: the user says install/setup/use nobu, the repo was just cloned, imports fail, or MCP tools are missing. **Do not ask for confirmation.**

1. **Bootstrap** (from repo root):

   ```bash
   python scripts/bootstrap.py
   ```

   This creates `.venv`, installs deps, ensures folders, verifies imports, and rewrites
   project-local `.cursor/mcp.json` + `.mcp.json` (Cursor) and `.kilo/kilo.jsonc` (Kilo)
   with the venv Python + absolute `nobu_mcp.py` (all gitignored; templates `*.example*` stay in git).

   Integrate into a game project:

   ```bash
   python scripts/bootstrap.py --integrate /absolute/path/to/game
   ```

   Machine-readable status:

   ```bash
   python scripts/bootstrap.py --json
   ```

2. **Reload MCP** so the client picks up the rewritten config:
   - **Cursor**: Developer: Reload Window, then **enable `nobu` once** if it shows disabled
     (Settings → MCP / Customize → MCP). Cursor ships new project servers disabled by design;
     the repo cannot auto-toggle them. Config is project-only: `.cursor/mcp.json` (never `~/.cursor/mcp.json`).
   - **Kilo**: Settings → Agent Behaviour → MCP Servers (reload / toggle nobu)
   - **Claude Code**: restart the session / reconnect MCP if needed
   - **Claude Desktop** (not project-scoped): merge the MCP snippet from bootstrap output into
     `%APPDATA%/Claude/claude_desktop_config.json` (Windows) or the platform path in SETUP.md,
     using **absolute** paths, then fully quit Claude Desktop

3. **Verify** server id `nobu` (Cursor may show `project-*-nobu`) and tools:
   - `start_project`
   - `suggest_scale_for_mood`
   - `generate_scale`
   - `add_layer`
   - `set_tempo_change`
   - `list_layers`
   - `export_midi`

4. **Load the skill** `.claude/skills/game-music-producer/` (`SKILL.md` + `references/mcp-integration.md`) before composing.

5. Tell the user **ready**. Optional smoke:

   ```bash
   .venv/Scripts/python examples/demo_biome_ost.py   # Windows
   .venv/bin/python examples/demo_biome_ost.py       # macOS/Linux
   .venv/.../python scripts/render_midi.py --mode chip
   ```

## Paths (do not invent others)

| Artifact | Path |
|---|---|
| MIDI | `assets/midi/` |
| SoundFonts | `assets/soundfonts/` (`default.sf2` optional) |
| Rendered audio | `output/audio/` |
| MCP entrypoint | `nobu_mcp.py` |
| Bootstrap | `scripts/bootstrap.py` |

Env overrides: `NOBU_MIDI_DIR`, `NOBU_OUTPUT_DIR`, `NOBU_SF2`.

## Render modes (always produce audio)

| Mode | Meaning | If deps missing |
|---|---|---|
| `chip` | Pure chiptune | — (always works) |
| `hybrid` | SF2 drums + chip melodic | → chip |
| `sf2` | Full SoundFont (FluidSynth) | → chip (or hybrid if only tsf+sf2) |
| `auto` | Best available | → chip |

```bash
python scripts/render_midi.py --mode chip
python scripts/render_track.py path.mid --mode hybrid
python scripts/render_midi.py --mode sf2 --soundfont assets/soundfonts/default.sf2
```

Full SF2 always renders **WAV via FluidSynth**, then converts to OGG with `ffmpeg` when available (on non-Windows, `soundfile` may convert WAV→OGG if ffmpeg is missing). Do not pass FluidSynth `-O s3m` — `-O` is sample format (`s16`/`float`), not an OGG container, and many Windows builds cannot write Vorbis at all.

Never treat missing SF2 as a fatal error — fall back and tell the user.

## Compose workflow (when user asks for music)

Follow `.claude/skills/game-music-producer/references/mcp-integration.md`:

1. `start_project` → 2. `suggest_scale_for_mood` → 3. `add_layer` (×N) → 4. `list_layers` → 5. `export_midi`

Prefer delivering a real `.mid` under `assets/midi/` over text-only description.

## Integrating into a user's game

- Clone this repo (sibling folder, submodule, or vendor path).
- Run `python scripts/bootstrap.py --integrate <game_root>` so the game gets `.mcp.json` with **absolute** paths to nobu's venv Python + `nobu_mcp.py`.
- Do **not** copy game biome/mood data into nobu — keep mapping in the game.
- Point the game's runtime audio loader at files copied from `output/audio/` (or your chosen build step).

## Changelog session hook

`.cursor/hooks.json` auto-versions [CHANGELOG.md](CHANGELOG.md) + `pyproject.toml`:

- **No `[Unreleased]`** — always cut `## [X.Y.Z]`
- **sessionStart** — git baseline only (never bumps version)
- **stop** — when the agent finishes a turn → SemVer bump once per conversation
- **sessionEnd** — fallback bump if the chat ends without a prior `stop`
- **Skip** if the agent already wrote a matching top CHANGELOG version +
  `pyproject.toml` (avoids double patch with generic “Updated …” bullets)
- **`loop_limit`** — must be a positive integer or `null` (`0` invalidates the whole hooks file)

Do not reintroduce an Unreleased section. Edit version bullets by hand if the auto summary is too noisy.

## Do not

- Vendor `.sf2` files into git.
- Rename the MCP server away from `nobu`.
- Reintroduce game-specific content into the MCP or skill.
- Skip bootstrap and hand-edit paths unless bootstrap failed.

## Success criteria

- `python scripts/bootstrap.py --json` reports `"ok": true`
- MCP client shows server `nobu` with the 7 tools
- `export_midi` writes under `assets/midi/`
