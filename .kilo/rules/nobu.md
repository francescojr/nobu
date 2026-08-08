# nobu (Kilo Code)

Game-agnostic MCP for chiptune/retro MIDI + audio render.

## Setup

```bash
python scripts/bootstrap.py --no-prompt
```

Bootstrap writes `.kilo/kilo.jsonc` with `"timeout": 300000` (5 min). Reload Kilo MCP
(Settings → Agent Behaviour → MCP Servers).

**If render times out (-32001):** Settings → MCP → nobu → Network Timeout → **5 minutes**.

## Paths

- MIDI → `assets/midi/`
- SoundFonts → `assets/soundfonts/`
- Mega Drive BYO → `assets/megadrive/` (optional)
- Rendered audio → `output/audio/{project_name}/wav/` and `.../ogg/`
- Mega Drive VGM → `output/audio/{project_name}/vgm/`

## Compose + deliver (MCP)

```
start_project → suggest_scale_for_mood → add_layer → list_layers → export_midi
→ get_render_capabilities   (before hybrid/sf2)
→ render_chip   (first audio — preferred)
→ render_hybrid | render_sf2 | render_all_modes   (only when user asks)
→ get_megadrive_capabilities → export_megadrive   (Mega Drive / SGDK / VGM)
```

If the user asks for audio, **never stop at MIDI** — call **`render_chip`** after export.
If they ask for Mega Drive / SGDK, call **`export_megadrive`** (VGM; PSG drums without BYO PCM).

After render, report **`mode_effective`**, **`fallback_reason`**, **`quality_warnings`** — never claim SF2 if `mode_effective != sf2`.

**`-32001` timeout:** retry shell only as last resort:

```bash
python scripts/render_track.py assets/midi/{project}.mid --mode chip --json
```

Use `render_all_modes` only when the user explicitly wants chip + hybrid + sf2 compared.

Follow `.claude/skills/game-music-producer/references/mcp-integration.md`.
