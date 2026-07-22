# nobu (Kilo Code)

Game-agnostic MCP for chiptune/retro MIDI + audio render.

## Setup

```bash
python scripts/bootstrap.py
```

Bootstrap writes `.kilo/kilo.jsonc` with absolute venv paths. Reload Kilo MCP
(Settings → Agent Behaviour → MCP Servers).

## Paths

- MIDI → `assets/midi/`
- SoundFonts → `assets/soundfonts/`
- Rendered audio → `output/audio/`

## Compose

Use nobu MCP tools: `start_project` → `suggest_scale_for_mood` → `add_layer` →
`list_layers` → `export_midi`. Follow `.claude/skills/game-music-producer/`.

Render modes: `--mode chip` | `hybrid` | `sf2` | `auto` (never hard-fails without SF2).
