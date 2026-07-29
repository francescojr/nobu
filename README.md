<p align="center">
  <img src="assets/images/nobu.png" alt="nobu — chiptune / retro MIDI MCP" width="720">
</p>

# nobu

**Game-agnostic MCP toolkit for composing chiptune / retro MIDI and rendering game audio.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.2.1-blue.svg)](CHANGELOG.md)
[![Changelog](https://img.shields.io/badge/changelog-Keep%20a%20Changelog-orange.svg)](CHANGELOG.md)

Plug nobu into **Cursor**, **Claude Desktop**, or **Kilo Code**. Ask an agent to compose a stage theme — get a real multi-track `.mid`, then render to `.ogg` / `.wav` for your engine.

nobu ships **no game-specific data**. Your project supplies tonic, mood, and biome params.

```
  agent / examples ──► nobu MCP ──► assets/midi/{project}.mid
                                      │
  assets/soundfonts/*.sf2 ──┐         ▼
                            └─► render MCP / scripts ──► output/audio/{project}/wav|ogg/
```

---

## Agent-ready?

**Cursor / Claude Code / Kilo (opened on this repo):** yes — after clone the agent should read `AGENTS.md` / `CLAUDE.md`, run `python scripts/bootstrap.py --no-prompt`, reload MCP, and be ready. Humans can run `python scripts/bootstrap.py` without flags for an interactive optional-upgrade menu. Rules/skills ship in-repo (`.cursor/rules`, `.claude/skills`); MCP/Kilo configs are **generated locally** by bootstrap (templates: `.mcp.example.json`, `.kilo/kilo.example.jsonc`).

**Cursor caveat:** new project MCP servers start **disabled** (Cursor security). After bootstrap + reload, toggle **nobu** on once under Settings → MCP (or Customize → MCP). Stays on for that workspace afterward — we cannot force-enable from the repo.

**Claude Desktop:** almost — same bootstrap, but the agent must also merge the MCP snippet into the **global** `claude_desktop_config.json` (Desktop does not auto-load project `.mcp.json`).

**Not magic:** `python` must be on PATH; open the cloned folder; reload after bootstrap; on Cursor, enable `nobu` once if it appears disabled.

## Paste this to your agent

```text
Clone https://github.com/francescojr/nobu.git (sibling folder or into this workspace).
Read AGENTS.md (and CLAUDE.md if present) and run: python scripts/bootstrap.py --no-prompt
If this is a game project, also run: python scripts/bootstrap.py --integrate <this_project_root> --no-prompt
Reload MCP. In Cursor, enable server "nobu" if it is disabled (Settings → MCP).
Confirm tools: compose (start_project … export_midi) + render (render_project / render_all_modes).
Then follow .claude/skills/game-music-producer/ — deliver MIDI and audio when I ask.
```

Integrating into an existing game:

```text
Set up https://github.com/francescojr/nobu as our game-music MCP.
Clone it next to this repo, run python scripts/bootstrap.py --integrate <absolute path to this project> --no-prompt,
reload MCP, and confirm tools work. Do not hardcode our game data into nobu.
```

Agents follow [AGENTS.md](AGENTS.md). Bootstrap rewrites project-local `.cursor/mcp.json` + `.mcp.json` + `.kilo/kilo.jsonc` to the local venv (never global Cursor MCP).

---

## Fastest path to sound

**Human (interactive menu for optional upgrades):**

```bash
git clone https://github.com/francescojr/nobu.git
cd nobu
python scripts/bootstrap.py
# → optional menu for tinysoundfont / FluidSynth / ffmpeg hints
# → reload Cursor/Kilo → enable nobu once → ask your agent for music
```

**Agent / CI (no prompts):**

```bash
python scripts/bootstrap.py --no-prompt
```

**Prove audio works (no MCP):**

```bash
python scripts/bootstrap.py --no-prompt --smoke
```

**Optional upgrades later:**

```bash
python scripts/bootstrap.py --with-render --no-prompt   # hybrid drums (pip)
python scripts/bootstrap.py --doctor                    # re-check deps
# SF2: copy your .sf2 → assets/soundfonts/default.sf2 (see assets/soundfonts/README.md)
```

### Works out of the box vs optional

| After bootstrap | Works? |
|---|---|
| Compose + render **chip** via MCP | Yes |
| Render **hybrid** | Needs `tinysoundfont` + your `.sf2` |
| Render **sf2** | Needs FluidSynth CLI + your `.sf2` |
| OGG on Windows | `ffmpeg` recommended (WAV always works) |

---

## Quick start (manual)

```bash
git clone https://github.com/francescojr/nobu.git
cd nobu
python scripts/bootstrap.py
# creates .venv, installs deps, writes .cursor/mcp.json, optional upgrade menu
```

Then reload MCP. In **Cursor**: Settings → MCP → enable **nobu** once if disabled. Full notes: [SETUP.md](.claude/skills/game-music-producer/SETUP.md).

### Demo without MCP

```bash
python examples/demo_biome_ost.py
python scripts/render_midi.py --mode chip   # always works, no SF2 needed
# → assets/midi/*.mid  and  output/audio/{project}/wav|ogg/
```

### Render modes (chip / hybrid / full SF2)

| Mode | What you get | Requirements |
|---|---|---|
| `chip` | Pure chiptune | None (default path without SF2) |
| `hybrid` | SF2 drums + chiptune melodic | `.sf2` + `tinysoundfont` (else → chip) |
| `sf2` | Full SoundFont (all instruments) | `.sf2` + FluidSynth CLI (else → chip) |
| `auto` | Best available | Never fails — degrades to chip |

Full **SF2** always does FluidSynth → **WAV**, then converts to **OGG** (prefer `ffmpeg` on Windows). FluidSynth is not asked to write OGG directly.

```bash
python scripts/render_midi.py --mode chip
python scripts/render_midi.py --mode sf2 --soundfont assets/soundfonts/default.sf2
python scripts/render_track.py assets/midi/biome1_calm.mid --mode hybrid
```

---

## Folder layout

| Path | Purpose |
|---|---|
| `nobu_mcp.py` | MCP server entrypoint (`FastMCP("nobu")`) |
| `AGENTS.md` | Checklist agents run after clone |
| `scripts/bootstrap.py` | One-shot setup (venv, deps, Cursor `.mcp.json` + Kilo `.kilo/kilo.jsonc`) |
| `.kilo/` | Kilo Code v7+ config (`kilo.example.jsonc`, `rules/nobu.md`) |
| `assets/midi/` | Generated / authored `.mid` files |
| `assets/soundfonts/` | Your `.sf2` files (not vendored — see README there) |
| `output/audio/` | Rendered audio root — `{project}/wav/` and `{project}/ogg/` per track |
| `nobu_render.py` | Shared render library (CLI + MCP) |
| `scripts/render_midi.py` | Batch MIDI → audio (`chip` / `hybrid` / `sf2` / `auto`) |
| `scripts/render_track.py` | Single-file render (same modes; SF2 → WAV → OGG) |
| `examples/demo_biome_ost.py` | Generic 4-biome × calm/combat demo |
| `.claude/skills/game-music-producer/` | Agent skill + theory references |

**Env overrides:** `NOBU_MIDI_DIR`, `NOBU_OUTPUT_DIR`, `NOBU_SF2` (also `FLUID_SYNTH_SF2`).

---

## MCP tools

| Tool | Role |
|---|---|
| `start_project` | Create an empty multi-layer project |
| `suggest_scale_for_mood` | Map scene mood → scale + pitch palette |
| `generate_scale` | Build a scale from tonic + type |
| `add_layer` | Add melody / harmony / bass / drums (string drum names OK) |
| `set_tempo_change` | Schedule BPM changes (horizontal resequencing) |
| `list_layers` | Inspect layers before export |
| `export_midi` | Write `assets/midi/{project}.mid` + loop metadata |
| `render_project` | Render one mode: chip / hybrid / sf2 / auto |
| `render_chip` | Pure chiptune render shortcut |
| `render_hybrid` | SF2 drums + chip melodic shortcut |
| `render_sf2` | Full SoundFont render shortcut |
| `render_all_modes` | chip + hybrid + sf2 in one call |
| `get_render_capabilities` | FluidSynth / SF2 / ffmpeg health check |
| `list_soundfonts` | Discover `.sf2` files |

Audio output: `output/audio/{project}/wav/` and `.../ogg/`.

Mood keys: `safe_exploration`, `heroic_exploration`, `nostalgic_town`, `melancholic_dungeon`, `hostile_exotic_biome`, `magical_dreamlike`, `combat`, `victory`, `classic_retro`.

---

## SoundFonts

Place **your own** `.sf2` at:

```
assets/soundfonts/default.sf2
```

Or set `NOBU_SF2=/path/to/yours.sf2`. Re-check: `python scripts/bootstrap.py --doctor` or MCP `get_render_capabilities`.

Without a soundfont, chip render **always works** via the built-in NES-style synth. Hybrid/sf2 modes fall back to chip until you add a soundfont.

---

## Agent skill

Copy or open this repo so Cursor / Claude can load:

`.claude/skills/game-music-producer/`

When the **nobu** MCP is connected, the skill instructs the agent to call the tools and deliver real MIDI **and audio** — not text-only sketches.

---

## Versioning

nobu follows [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).
See [CHANGELOG.md](CHANGELOG.md) ([Keep a Changelog](https://keepachangelog.com/) categories).

There is **no `[Unreleased]` section** — Cursor session hooks cut a new version
whenever a conversation ends with meaningful changes.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

[MIT](LICENSE) — Copyright (c) 2026 nobu contributors.

---
---

# nobu (Português)

**Toolkit MCP game-agnostic para compor MIDI chiptune/retrô e renderizar áudio de jogo.**

## Cole isso no seu agente

```text
Clone https://github.com/francescojr/nobu.git.
Leia nobu/AGENTS.md e rode: python scripts/bootstrap.py --no-prompt
Se for um projeto de jogo, rode também: python scripts/bootstrap.py --integrate <raiz_deste_projeto> --no-prompt
Recarregue o MCP, confirme o server "nobu" (14 tools: compose + render).
Siga .claude/skills/game-music-producer/ — compose e render quando eu pedir.
```

## Início rápido (manual)

```bash
git clone https://github.com/francescojr/nobu.git
cd nobu
python scripts/bootstrap.py          # humano: menu interativo de optionals
python scripts/bootstrap.py --no-prompt --smoke   # agente: prova chip sem MCP
python examples/demo_biome_ost.py
python scripts/render_midi.py --mode chip   # funciona sem SF2
```

Modos: `chip` (puro) · `hybrid` (SF2 drums + chip) · `sf2` (SoundFont completo).  
Sem SF2/FluidSynth → fallback automático para chiptune (não quebra).  
SF2: FluidSynth → WAV → OGG (`ffmpeg` recomendado no Windows).

Detalhes: [AGENTS.md](AGENTS.md) · [SETUP.md](.claude/skills/game-music-producer/SETUP.md).

## Pastas

| Path | Uso |
|---|---|
| `assets/midi/` | Arquivos `.mid` |
| `assets/soundfonts/` | Seus `.sf2` (não distribuídos no repo) |
| `output/audio/` | `{project}/wav/` e `{project}/ogg/` renderizados |

## Tools MCP (inglês)

Compose: `start_project` → `suggest_scale_for_mood` → `add_layer` → `list_layers` → `export_midi`  
Render: `render_project` / `render_chip` / `render_hybrid` / `render_sf2` / `render_all_modes`

## Licença

[MIT](LICENSE).
