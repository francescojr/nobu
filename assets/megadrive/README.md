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

## Bring your own PCM drums

Optional WAVs (mono or stereo; any common rate — resampled to **13300 Hz** u8):

```
assets/megadrive/pcm/kick.wav
assets/megadrive/pcm/snare.wav
assets/megadrive/pcm/closed_hihat.wav
assets/megadrive/pcm/open_hihat.wav
assets/megadrive/pcm/crash.wav
```

Missing hits fall back to **PSG noise**. Do **not** commit third-party kits into the nobu repo (they are gitignored).

You may author short hits in any tool you like (including community Mega Drive trackers) **locally**; nobu does not redistribute those packs.

## Export

```bash
python scripts/export_megadrive.py assets/midi/my_track.mid --json
# → output/audio/my_track/vgm/my_track.vgm
```

MCP: `get_megadrive_capabilities` → `export_megadrive("my_track")` after `export_midi`.

## SGDK handoff

In your game `.res` file (paths relative to the game project):

```
XGM my_bgm "music/my_track.vgm"
```

SGDK **rescomp** converts VGM→XGM via **xgmtool**. nobu does not run xgmtool.

Then play with `XGM_startPlay(&my_bgm)` (or your driver’s API).
