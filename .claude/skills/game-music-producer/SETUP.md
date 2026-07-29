# nobu — Installation & MCP Setup

## English

### 0. Agent / one-command setup (recommended)

From the repo root — creates `.venv`, installs deps, writes local `.mcp.json` with absolute paths:

```bash
python scripts/bootstrap.py              # human: interactive optional-upgrade menu
python scripts/bootstrap.py --no-prompt  # agents/CI: no menu
python scripts/bootstrap.py --smoke --no-prompt   # prove chip render end-to-end
python scripts/bootstrap.py --doctor   # re-check deps only
```

Into another project (game repo):

```bash
python scripts/bootstrap.py --integrate /absolute/path/to/game --no-prompt
```

Agents should follow [AGENTS.md](../../../AGENTS.md) and run bootstrap with `--no-prompt` without asking.

### 1. Requirements (manual)

```bash
pip install -r requirements.txt
# or: pip install fastmcp midiutil mido numpy soundfile
```

Optional extras:

```bash
pip install "nobu[render]"   # or: pip install tinysoundfont==0.3.7
```

For richer `.mid` → `.ogg` rendering:

```bash
# Windows (recommended):  winget install FluidSynth.FluidSynth
#                         then restart Kilo / MCP session (PATH)
# Windows (alt):         choco install fluidsynth
# macOS:                 brew install fluidsynth
# Linux:                 apt install fluidsynth
```

Full SF2 mode always does **FluidSynth → WAV**, then converts to OGG with **`ffmpeg`** when available. On non-Windows, `soundfile` may convert WAV→OGG if ffmpeg is missing; on Windows, install `ffmpeg` for OGG from `render_track` / SF2 (some libsndfile wheels crash encoding Vorbis).

`render_midi.py --mode chip` can still write OGG directly via `soundfile` from the in-memory buffer.

Windows FluidSynth builds often cannot write OGG/Vorbis directly (`-T ogg` / filename `.ogg`). nobu does not rely on that path. Note: FluidSynth `-O` sets **sample format** (`s16`, `float`, …), not the file container.

FluidSynth **2.5.x** (common on Windows via winget): nobu passes `-F` and sample-rate flags **before** the `.sf2` and `.mid` paths. Re-check with `python scripts/bootstrap.py --doctor`.

### 2. Folder layout

```
nobu/
├── nobu_mcp.py
├── assets/
│   ├── midi/           # .mid output (MCP + examples)
│   └── soundfonts/     # place default.sf2 here
└── output/
    └── audio/          # rendered .ogg / .wav
```

### 3. Cursor

Run `python scripts/bootstrap.py` — it writes **project-local** `.cursor/mcp.json` (+ legacy `.mcp.json`) using the venv Python + absolute path to `nobu_mcp.py` (gitignored; never writes `~/.cursor/mcp.json`). Open the project in Cursor, reload the window, then **enable `nobu` once** under Settings → MCP if it shows disabled (Cursor security default — the repo cannot auto-toggle).

Portable fallback (before bootstrap):

```json
{
  "mcpServers": {
    "nobu": {
      "command": "python",
      "args": ["${workspaceFolder}/nobu_mcp.py"]
    }
  }
}
```

### 4. Claude Desktop

Edit (or create) the Claude Desktop config:

| Platform | Path |
|---|---|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

```json
{
  "mcpServers": {
    "nobu": {
      "command": "python",
      "args": ["C:/absolute/path/to/nobu/nobu_mcp.py"]
    }
  }
}
```

### 5. Kilo Code (v7+)

Kilo uses [`.kilo/kilo.jsonc`](../../../.kilo/kilo.example.jsonc) (not Claude’s `mcpServers` shape).
See [Using MCP in Kilo Code](https://kilo.ai/docs/automate/mcp/using-in-kilo-code).

**Recommended:** from the repo root run `python scripts/bootstrap.py` — it writes
`.kilo/kilo.jsonc` with absolute venv Python + `nobu_mcp.py`, plus loads
`AGENTS.md` / the skill via `instructions`.

Template checked into git: `.kilo/kilo.example.jsonc`. Local generated file is gitignored.

Manual example (replace paths with absolutes from your machine):

```jsonc
{
  "instructions": [
    "AGENTS.md",
    ".claude/skills/game-music-producer/SKILL.md",
    ".kilo/rules/nobu.md"
  ],
  "mcp": {
    "nobu": {
      "type": "local",
      "command": [
        "C:/path/to/nobu/.venv/Scripts/python.exe",
        "C:/path/to/nobu/nobu_mcp.py"
      ],
      "enabled": true,
      "timeout": 300000
    }
  }
}
```

**Kilo render timeout:** In Settings → Agent Behaviour → MCP Servers → **nobu**,
set the **Network Timeout** dropdown to **5 minutes** (default is often 30s–1min).
Also ensure `.kilo/kilo.jsonc` has `"timeout": 300000` (bootstrap writes this).

Then: Settings → Agent Behaviour → MCP Servers → confirm **nobu** is enabled.
Also supported: global `~/.config/kilo/kilo.jsonc` (Windows: `%USERPROFILE%\.config\kilo\kilo.jsonc`).

### 6. Restart & verify

Fully quit and reopen the client. You should see server **nobu** with 14 tools:

**Compose:** `start_project`, `suggest_scale_for_mood`, `generate_scale`, `add_layer`, `set_tempo_change`, `list_layers`, `export_midi`

**Render:** `render_project`, `render_chip`, `render_hybrid`, `render_sf2`, `render_all_modes`

**Discovery:** `get_render_capabilities`, `list_soundfonts`

### 7. Where files go

By default `export_midi` writes to `assets/midi/` (override with `destination_dir` or `NOBU_MIDI_DIR`).

Render:

```bash
python scripts/render_midi.py
# or with a soundfont:
python scripts/render_midi.py --soundfont assets/soundfonts/default.sf2
```

Output lands in `output/audio/{project_name}/wav/` and `.../ogg/`.

Env vars: `NOBU_MIDI_DIR`, `NOBU_OUTPUT_DIR`, `NOBU_SF2` (also accepts `FLUID_SYNTH_SF2`).

### 8. Hearing the music

- MIDI needs a soundfont or the chiptune synth in `render_midi.py`.
- Free SNES-style soundfonts: [williamkage.com](https://www.williamkage.com/snes_soundfonts/) — save as `assets/soundfonts/default.sf2`.

### 9. Game-agnostic note

nobu and this skill ship **no game-specific data**. Your game (or `examples/demo_biome_ost.py`) supplies tonic + mood. Typical integration:

1. Each stage/biome defines `mood` + `tonic_midi`.
2. AudioManager loads `{stage}_calm.ogg` / `{stage}_combat.ogg` from your runtime audio path (copy from `output/audio/{project}/ogg/`).
3. Build step converts `assets/midi/*.mid` → `output/audio/{project}/wav|ogg/` (MCP `render_all_modes` or `scripts/render_midi.py`).

### Troubleshooting

| Symptom | Fix |
|---|---|
| Server does not appear | Absolute path in JSON; `python` on PATH |
| Tools fail on import | `pip install -r requirements.txt` |
| Empty MIDI folder after compose | Check `NOBU_MIDI_DIR` / default `assets/midi` |
| No OGG (WAV only) | Install `ffmpeg` (Windows) or ensure `soundfile` Vorbis works; FluidSynth alone does not write OGG here |

---

## Português

### Setup recomendado (agente / um comando)

```bash
python scripts/bootstrap.py --no-prompt
# ou, num projeto de jogo:
python scripts/bootstrap.py --integrate C:/caminho/do/jogo --no-prompt
```

Siga [AGENTS.md](../../../AGENTS.md).

### Requisitos (manual)

```bash
pip install -r requirements.txt
```

### Pastas

| Artefato | Path |
|---|---|
| MIDI | `assets/midi/` |
| SoundFonts | `assets/soundfonts/` |
| Áudio renderizado | `output/audio/{project}/wav/` e `.../ogg/` |

### Cursor

Rode `python scripts/bootstrap.py --no-prompt` (agentes) ou `python scripts/bootstrap.py` (humano, menu interativo) — gera `.cursor/mcp.json` + `.mcp.json` locais (gitignored). Template portable: `.mcp.example.json`. No Cursor, habilite `nobu` uma vez em Settings → MCP se vier desligado.

### Claude Desktop

JSON clássico `mcpServers` com caminho absoluto para `nobu_mcp.py`.

### Kilo Code

Formato v7 em `.kilo/kilo.jsonc` (`mcp.nobu.type: "local"`, `command: [python, nobu_mcp.py]`).
Rode `python scripts/bootstrap.py` ou copie `.kilo/kilo.example.jsonc`.

### Tools (inglês)

**Compose:** `start_project`, `suggest_scale_for_mood`, `generate_scale`, `add_layer`, `set_tempo_change`, `list_layers`, `export_midi`

**Render:** `render_project`, `render_chip`, `render_hybrid`, `render_sf2`, `render_all_modes`

**Discovery:** `get_render_capabilities`, `list_soundfonts`

### Pipeline

```bash
python examples/demo_biome_ost.py
python scripts/render_midi.py --mode chip
# ou via MCP: export_midi → render_all_modes
```

MIDI em `assets/midi/` → OGG/WAV em `output/audio/{project}/wav/` e `.../ogg/`.
SF2: FluidSynth → WAV → OGG (`ffmpeg` no Windows). Detalhes na seção EN acima.

O nobu é **game-agnostic** — não sabe nada do seu jogo; tônica e mood vêm do caller.
