# AGENTS.md — nobu

Instructions for coding agents (Cursor, Claude Code, Kilo Code, etc.).
Humans: see [README.md](README.md). Setup detail: [.claude/skills/game-music-producer/SETUP.md](.claude/skills/game-music-producer/SETUP.md).

## Mission

nobu is a **game-agnostic** MCP server + skill for composing chiptune/retro MIDI and rendering game audio. It ships **no game-specific data**.

## First actions after clone (do this automatically)

When the user asks to install / set up / use nobu, or you just cloned this repo, run this checklist **without asking for confirmation**:

1. **Bootstrap** (from repo root):

   ```bash
   python scripts/bootstrap.py
   ```

   This creates `.venv`, installs `requirements.txt`, ensures folders exist, verifies imports, and writes a **local** `.mcp.json` (gitignored) pointing at the venv Python + absolute `nobu_mcp.py`. Template in git: `.mcp.example.json`.

   If integrating into another project (game repo):

   ```bash
   python scripts/bootstrap.py --integrate /absolute/path/to/game
   ```

   Prefer `--json` when you need a machine-readable status:

   ```bash
   python scripts/bootstrap.py --json
   ```

2. **Reload MCP** in the client (Cursor: reload window / restart MCP; Claude Desktop: quit fully; Kilo: reload MCP settings).

3. **Verify** the MCP server id is `nobu` and these tools exist:
   - `start_project`
   - `suggest_scale_for_mood`
   - `generate_scale`
   - `add_layer`
   - `set_tempo_change`
   - `list_layers`
   - `export_midi`

4. **Load the skill** at `.claude/skills/game-music-producer/` (especially `SKILL.md` + `references/mcp-integration.md`) before composing.

5. Tell the user: **ready**. Optional smoke demo:

   ```bash
   .venv/Scripts/python examples/demo_biome_ost.py   # Windows
   .venv/bin/python examples/demo_biome_ost.py       # macOS/Linux
   .venv/.../python scripts/render_midi.py
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
- **sessionStart** — git baseline
- **stop** / **sessionEnd** — SemVer bump (`patch`/`minor`/`major`) once per conversation

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
