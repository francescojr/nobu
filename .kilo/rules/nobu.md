# nobu (Kilo Code)

Game-agnostic MCP for chiptune/retro MIDI + audio render.

## Setup

```bash
python scripts/bootstrap.py --no-prompt
```

Bootstrap writes `.kilo/kilo.jsonc` with absolute venv paths. Reload Kilo MCP
(Settings → Agent Behaviour → MCP Servers).

## Paths

- MIDI → `assets/midi/`
- SoundFonts → `assets/soundfonts/`
- Rendered audio → `output/audio/{project_name}/wav/` and `.../ogg/`

## Compose + deliver (MCP)

```
start_project → suggest_scale_for_mood → add_layer → list_layers → export_midi
→ render_chip | render_hybrid | render_sf2 | render_all_modes
```

If the user asks for audio, **never stop at MIDI** — call a render tool after export.

Render modes: `chip` | `hybrid` | `sf2` | `auto` (never hard-fails without SF2).
Use `get_render_capabilities` before promising SF2. Use `render_all_modes` for
chip + hybrid + sf2 in one call.

Follow `.claude/skills/game-music-producer/references/mcp-integration.md`.
