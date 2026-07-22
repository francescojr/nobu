# nobu — Installation & MCP Setup

## English

### 0. Agent / one-command setup (recommended)

From the repo root — creates `.venv`, installs deps, writes local `.mcp.json` with absolute paths:

```bash
python scripts/bootstrap.py
```

Into another project (game repo):

```bash
python scripts/bootstrap.py --integrate /absolute/path/to/game
```

Agents should follow [AGENTS.md](../../../AGENTS.md) and run bootstrap without asking.

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
# Windows:  choco install fluidsynth
# macOS:    brew install fluidsynth
# Linux:    apt install fluidsynth
```

`ffmpeg` is required only for `scripts/render_track.py` (WAV → OGG).

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

Run `python scripts/bootstrap.py` — it writes `.mcp.json` using the venv Python + absolute path to `nobu_mcp.py` (gitignored; template is `.mcp.example.json`). Open the project in Cursor, enable MCP, reload the window.

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

### 5. Kilo Code / VS Code MCP

Add to workspace or user MCP settings (same shape as Claude Desktop):

```json
{
  "mcpServers": {
    "nobu": {
      "command": "python",
      "args": ["/absolute/path/to/nobu/nobu_mcp.py"]
    }
  }
}
```

On macOS/Linux prefer `python3` if `python` is not on PATH.

### 6. Restart & verify

Fully quit and reopen the client. You should see server **nobu** with 7 tools:

- `start_project`
- `suggest_scale_for_mood`
- `generate_scale`
- `add_layer`
- `set_tempo_change`
- `list_layers`
- `export_midi`

### 7. Where files go

By default `export_midi` writes to `assets/midi/` (override with `destination_dir` or `NOBU_MIDI_DIR`).

Render:

```bash
python scripts/render_midi.py
# or with a soundfont:
python scripts/render_midi.py --soundfont assets/soundfonts/default.sf2
```

Output lands in `output/audio/`.

Env vars: `NOBU_MIDI_DIR`, `NOBU_OUTPUT_DIR`, `NOBU_SF2` (also accepts `FLUID_SYNTH_SF2`).

### 8. Hearing the music

- MIDI needs a soundfont or the chiptune synth in `render_midi.py`.
- Free SNES-style soundfonts: [williamkage.com](https://www.williamkage.com/snes_soundfonts/) — save as `assets/soundfonts/default.sf2`.

### 9. Game-agnostic note

nobu and this skill ship **no game-specific data**. Your game (or `examples/demo_biome_ost.py`) supplies tonic + mood. Typical integration:

1. Each stage/biome defines `mood` + `tonic_midi`.
2. AudioManager loads `{stage}_calm.ogg` / `{stage}_combat.ogg` from your runtime audio path.
3. Build step converts `assets/midi/*.mid` → `output/audio/*.ogg`.

### Troubleshooting

| Symptom | Fix |
|---|---|
| Server does not appear | Absolute path in JSON; `python` on PATH |
| Tools fail on import | `pip install -r requirements.txt` |
| Empty MIDI folder after compose | Check `NOBU_MIDI_DIR` / default `assets/midi` |
| No OGG | Install `soundfile` / FluidSynth / ffmpeg as needed |

---

## Português

### Setup recomendado (agente / um comando)

```bash
python scripts/bootstrap.py
# ou, num projeto de jogo:
python scripts/bootstrap.py --integrate C:/caminho/do/jogo
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
| Áudio renderizado | `output/audio/` |

### Cursor

O repo já inclui `.mcp.json` com o servidor `nobu`. Se `${workspaceFolder}` não for expandido, use caminho absoluto para `nobu_mcp.py`.

### Claude Desktop / Kilo Code

Mesmo JSON — chave `"nobu"`, `command: "python"`, `args` com caminho **absoluto** para `nobu_mcp.py`. Reinicie o cliente.

### Tools (inglês)

`start_project`, `suggest_scale_for_mood`, `generate_scale`, `add_layer`, `set_tempo_change`, `list_layers`, `export_midi`.

### Pipeline

```bash
python examples/demo_biome_ost.py
python scripts/render_midi.py
```

MIDI em `assets/midi/` → OGG/WAV em `output/audio/`.

O nobu é **game-agnostic** — não sabe nada do seu jogo; tônica e mood vêm do caller.
