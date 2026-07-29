# SoundFonts

Place **your own** `.sf2` files here. They are **not** shipped with nobu.

**Chip audio always works without a soundfont** via the built-in chiptune synth.
SF2 only unlocks hybrid / full SF2 modes.

## Bring your own SF2

1. Copy your `.sf2` file to `assets/soundfonts/default.sf2` (recommended name).
2. Or set `NOBU_SF2=/path/to/yours.sf2` (also accepts `FLUID_SYNTH_SF2`).
3. Re-check: `python scripts/bootstrap.py --doctor` or MCP `get_render_capabilities`.
4. **Hybrid** also needs `tinysoundfont` (`python scripts/bootstrap.py --with-render --no-prompt`).
5. **Full SF2** also needs FluidSynth on PATH (see SETUP.md).

## Recommended default path

```
assets/soundfonts/default.sf2
```

Or:

```bash
# Windows PowerShell
$env:NOBU_SF2 = "C:\path\to\your.sf2"

# macOS / Linux
export NOBU_SF2=/path/to/your.sf2
```

## Render modes

| Mode | Command | Needs SF2? | Result |
|---|---|---|---|
| **chip** | `--mode chip` | No | Pure chiptune (always works) |
| **hybrid** | `--mode hybrid` | Optional* | SF2 drums + chiptune melodic |
| **sf2** | `--mode sf2` | Optional* | Full SoundFont (all GM instruments) |
| **auto** | `--mode auto` | — | Best available; never fails |

\*If SF2 / FluidSynth / tinysoundfont is missing, nobu **falls back to chip** instead of erroring.

Output layout: `output/audio/{project_name}/wav/` and `output/audio/{project_name}/ogg/`.

```bash
python scripts/render_midi.py --mode chip
python scripts/render_midi.py --mode sf2 --soundfont assets/soundfonts/default.sf2
python scripts/render_track.py assets/midi/track.mid --mode hybrid
```

Hybrid also needs: `pip install tinysoundfont` (or `pip install "nobu[render]"`).  
Full SF2 needs the **FluidSynth** CLI on PATH. nobu renders SF2 to WAV, then converts to OGG via `ffmpeg` (recommended on Windows) or `soundfile` elsewhere.

## Where to get soundfonts

nobu does not download or ship soundfonts. Use your own `.sf2` file (see steps above).

---

## Português

Coloque **seu próprio** `.sf2` aqui. Sem soundfont o chiptune puro **já gera áudio** em `output/audio/{project}/wav|ogg/`.

1. Copie seu `.sf2` para `assets/soundfonts/default.sf2`
2. Ou `NOBU_SF2=/caminho/para/seu.sf2`
3. Re-check: `python scripts/bootstrap.py --doctor`
4. Hybrid: `tinysoundfont` · SF2 completo: FluidSynth no PATH

Modos: `chip` (puro), `hybrid` (SF2 drums + chip), `sf2` (SoundFont completo).  
Se faltar SF2/FluidSynth, o nobu faz fallback para chiptune — não quebra.
