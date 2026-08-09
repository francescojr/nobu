# Mega Drive assets (BYO)

Place **your own** FM patch JSON and optional PCM drum WAVs here.
They are **not** shipped with nobu.

**VGM export always works without these files** via builtin FM patches + PSG noise drums.
Local files only unlock custom timbres / sample drums (same idea as SoundFonts).

## Bring your own FM patches

1. Add JSON files under `assets/megadrive/patches/`:
   - `lead.json`, `bass.json`, `harmony.json` (names replace the builtin with the same key)
2. Schema (all integers):

```json
{
  "algo": 4,
  "fb": 3,
  "ops": [
    {"mul": 5, "dt": 0, "tl": 30, "rs": 1, "ar": 31, "am": 0, "d1r": 10, "d2r": 0, "rr": 8, "sl": 2},
    {"mul": 1, "dt": 0, "tl": 18, "rs": 1, "ar": 28, "am": 0, "d1r": 8, "d2r": 0, "rr": 7, "sl": 1},
    {"mul": 1, "dt": 0, "tl": 40, "rs": 0, "ar": 25, "am": 0, "d1r": 6, "d2r": 0, "rr": 6, "sl": 3},
    {"mul": 1, "dt": 0, "tl": 8, "rs": 0, "ar": 31, "am": 0, "d1r": 12, "d2r": 0, "rr": 10, "sl": 1}
  ]
}
```

Ranges: `algo`/`fb` 0–7; per op `mul` 0–15, `dt` 0–7, `tl` 0–127, `rs` 0–3, `ar`/`d1r`/`d2r` 0–31, `rr`/`sl` 0–15, `am` 0/1.

Invalid JSON is skipped (builtin kept). Check with MCP `get_megadrive_capabilities`.

## Bring your own FM patches from GenMDDJ

[GenMDDJ](https://github.com/little-scale/genmddj) ships 32 FM instrument files
(`instrument-patches/*.gmi`) and drum kits (`samples/01 808/`, `02 909/`, …).
All **BYO** — check its LICENSE before shipping; these files are gitignored here
(same policy as SoundFonts).

### `.gmi` format (72 B)

`"GMDJINS1"` magic + a 64-byte record:

- `[1]=algo`, `[2]=fb`
- operators at record offsets **8 / 18 / 28 / 38** in chip-slot order
  **OP1, OP3, OP2, OP4**, each 10 bytes
  `MUL DT TL RS AR AM D1 D2 RR SL`
  (`OP1`=chip S1, `OP3`=S3, `OP2`=S2, `OP4`=S4)
- name at bytes 54–61 of the record

### → nobu JSON

Write `assets/megadrive/patches/{lead,bass,harmony}.json`: copy `algo`, `fb`;
map ops to **logical** order op1..op4 as
`op1←S1@8, op2←S2@28, op3←S3@18, op4←S4@38`
(`apply_patch_commands` reorders them back to chip slots). Ranges match the
schema above.

Convert (Python, from repo root):

```python
import json, sys

def gmi_to_nobu(path):
    d = open(path, "rb").read()
    assert d[:8] == b"GMDJINS1"
    rec = d[8:72]  # record starts after magic
    order = [("op1", 8), ("op2", 28), ("op3", 18), ("op4", 38)]
    ops = []
    for _k, rbase in order:
        b = rec[rbase : rbase + 10]
        ops.append({
            "mul": b[0], "dt": b[1], "tl": b[2], "rs": b[3], "ar": b[4],
            "am": b[5], "d1r": b[6], "d2r": b[7], "rr": b[8], "sl": b[9],
        })
    return {"algo": rec[1] & 7, "fb": rec[2] & 7, "ops": ops}

json.dump(gmi_to_nobu(sys.argv[1]), open(sys.argv[2], "w"), indent=2)
```

Example:

```bash
python -c "..." path/to/Bass.gmi assets/megadrive/patches/bass.json
```

## Bring your own PCM drums

Optional WAVs (mono or stereo; any common rate — resampled to **13300 Hz**
unsigned 8-bit for the YM2612 DAC):

```
assets/megadrive/pcm/kick.wav
assets/megadrive/pcm/snare.wav
assets/megadrive/pcm/closed_hihat.wav
assets/megadrive/pcm/open_hihat.wav
assets/megadrive/pcm/crash.wav
```

From GenMDDJ 808 kit naming (copy/rename locally):

| Kit file | nobu name |
|---|---|
| `01 BD` | `kick.wav` |
| `03 SD` | `snare.wav` |
| `07 HH` | `closed_hihat.wav` |
| `11 HO` | `open_hihat.wav` |
| `14 CY` | `crash.wav` |

Missing hits fall back to **PSG noise**. Do **not** commit third-party kits into
the nobu repo (they are gitignored).

### What to expect from DAC PCM

- **8-bit @ ~13.3 kHz** is authentic Mega Drive DAC — expect a quantization
  noise floor (~48 dB). That is not a bug.
- nobu applies a **lowpass before downsampling** so bright hats/crash do not
  alias into harsh hiss when converting from 44.1/48 kHz masters.

You may author short hits in any tool you like (including community Mega Drive
trackers) **locally**; nobu does not redistribute those packs.

## Export

```bash
python scripts/export_megadrive.py assets/midi/my_track.mid --json
# → output/audio/my_track/vgm/my_track.vgm
```

MCP: `get_megadrive_capabilities` → `export_megadrive("my_track")` after `export_midi`.

Verify BYO loaded: `get_megadrive_capabilities` → `override_patches` + `pcm_hits_found`.

## SGDK handoff

In your game `.res` file (paths relative to the game project):

```
XGM my_bgm "music/my_track.vgm"
```

SGDK **rescomp** converts VGM→XGM via **xgmtool**. nobu does not run xgmtool.

Then play with `XGM_startPlay(&my_bgm)` (or your driver’s API).
