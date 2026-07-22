# SoundFonts

Place your `.sf2` files here. They are **not** shipped with nobu (licensing).

**Audio always works without a soundfont** via the built-in chiptune synth.
SF2 only unlocks richer / hybrid modes.

## Recommended default

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

`FLUID_SYNTH_SF2` is also accepted.

## Render modes

| Mode | Command | Needs SF2? | Result |
|---|---|---|---|
| **chip** | `--mode chip` | No | Pure chiptune (always works) |
| **hybrid** | `--mode hybrid` | Optional* | SF2 drums + chiptune melodic |
| **sf2** | `--mode sf2` | Optional* | Full SoundFont (all GM instruments) |
| **auto** | `--mode auto` | — | Best available; never fails |

\*If SF2 / FluidSynth / tinysoundfont is missing, nobu **falls back to chip** instead of erroring.

```bash
python scripts/render_midi.py --mode chip
python scripts/render_midi.py --mode sf2 --soundfont assets/soundfonts/default.sf2
python scripts/render_track.py assets/midi/track.mid --mode hybrid
```

Hybrid also needs: `pip install tinysoundfont` (or `pip install "nobu[render]"`).  
Full SF2 needs the **FluidSynth** CLI on PATH. nobu renders SF2 to WAV, then converts to OGG via `ffmpeg` (recommended on Windows) or `soundfile` elsewhere.

## Where to get free soundfonts

- [williamkage.com SNES soundfonts](https://www.williamkage.com/snes_soundfonts/)
- Any General MIDI `.sf2` works with FluidSynth

---

## Português

Coloque `.sf2` aqui. Sem soundfont o chiptune puro **já gera áudio**.  
Modos: `chip` (puro), `hybrid` (SF2 drums + chip), `sf2` (SoundFont completo).  
Se faltar SF2/FluidSynth, o nobu faz fallback para chiptune — não quebra.
