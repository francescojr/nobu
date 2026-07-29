# MCP Integration: nobu (real MIDI generation)

# English

This file documents the MCP server `nobu_mcp.py`, which lets the agent
GENERATE REAL `.mid` FILES on the user's machine, with independent channels
(melody, harmony, bass, drums) — solving the limitation of list-index-synced
compositions that sound square and groove-less.

**This MCP and skill are game-agnostic.** They contain no data for any specific
game. Biome/stage → tonic/mood mapping comes from the game's code (e.g. your
own `BiomeMusicParams` equivalent), not from nobu.

## Automatic activation rule

Whenever the user asks to "compose", "create a track", "generate music",
"make an OST", "create a theme for [stage/boss/area]" — and the MCP tools
`start_project`, `suggest_scale_for_mood`, `add_layer`, `set_tempo_change`,
`list_layers`, and `export_midi` are available — USE THEM DIRECTLY, without
asking the user. A real `.mid` file is always preferable to text-only or ABC.

## Mandatory compose workflow

Always follow this order:

1. **`start_project(project_name, bpm)`** — always first.
2. **`suggest_scale_for_mood(mood, tonic_midi, octaves)`** — ALWAYS before
   inventing pitches manually. Never guess note numbers from memory.
3. **`add_layer(...)`** — once per layer. Minimum: melody
   (`layer_type="melody"`, `chiptune_program="pulse_lead"`), bass
   (`layer_type="bass"`, `chiptune_program="triangle_bass"`), and drums
   (`layer_type="drums"`) with kick/snare/hi-hat using off-beat hi-hats.
   Add harmony (`chiptune_program="pulse_harmony"`) for denser arrangements.
4. **(Optional) `set_tempo_change(...)`** — for a faster/slower section
   (e.g. boss phase 2).
5. **`list_layers(project_name)`** — review before export.
6. **`export_midi(project_name, destination_dir)`** — writes `.mid` to `assets/midi/`.
7. **Render (when user wants audio):**
   - **`get_render_capabilities()`** — **required** before promising SF2/hybrid; read `modes_available`, `fluidsynth_path`, `install_hints`.
   - **`render_chip(project_name)`** — **preferred first delivery** (fast, no SF2).
   - **`render_project(project_name, mode)`** — single mode (`chip` | `hybrid` | `sf2` | `auto`).
   - **`render_hybrid` / `render_sf2`** — explicit mode shortcuts.
   - **`render_all_modes(project_name)`** — only when user asks to compare all three (slow, up to ~3 min).

After every render, read **`mode_effective`**, **`fallback_reason`**, and **`quality_warnings`** in the JSON. Do not report “SF2 delivered” if `mode_effective` is not `sf2` or if `quality_warnings` is non-empty.

Use default output layout only (`output/audio/{project}/wav|ogg/`). Do **not** use custom `destination_dir` unless the user explicitly asks.

Output: `output/audio/{project_name}/wav/` and `output/audio/{project_name}/ogg/`.

**Expected WAV sizes (~38s track):** chip ~3.5 MB, full SF2 ~7 MB. Similar sizes for chip and “sf2” mean fallback — check JSON.

### MCP render timeout (`-32001`)

If `render_chip` / `render_project` fails with **`MCP error -32001: Request timed out`**:

1. **Kilo:** Settings → MCP → nobu → Network Timeout → **5 minutes**; re-run bootstrap so `.kilo/kilo.jsonc` has `"timeout": 300000`.
2. **Retry via shell** (same result, no MCP timeout):

```bash
python scripts/render_track.py assets/midi/{project}.mid --mode chip --json
```

3. Do **not** use `render_all_modes` for first delivery — use `render_chip` only.

Shell fallback (manual):

```bash
python scripts/render_midi.py --mode chip
python scripts/render_track.py assets/midi/track.mid --mode hybrid
```

## Mood → scale table

| Game situation | Mood key for MCP |
|---|---|
| Safe town, starter hub | `safe_exploration` |
| Overworld, hero's journey | `heroic_exploration` |
| Old / folk city | `nostalgic_town` |
| Dungeon, lost/sad area | `melancholic_dungeon` |
| Desert, foreign/hostile area | `hostile_exotic_biome` |
| Dream, space, magic | `magical_dreamlike` |
| Normal battle | `combat` |
| Victory screen | `victory` |
| Classic 8-bit homage | `classic_retro` |

In **your game's code**, each stage/biome defines `mood` (one of these keys)
and `tonic_midi`. Pass both into `suggest_scale_for_mood` when composing.

## Drum patterns

Kick (`kick`) and snare (`snare`) mark the main pulse on whole beats
(0, 1, 2, 3…). Closed hi-hat (`closed_hihat`) breaks the rhythm on off-beats
(0.5, 1.5, 2.5…) for groove — never put the entire drum layer on whole beats.

For high intensity (combat, boss), add crash at phrase start and denser
hi-hats (0.25 instead of 0.5) with light `swing_offset` (0.02–0.04).

Portuguese drum aliases (`bumbo`, `caixa`, `chimbal_fechado`, …) still work.

## Instrumentation (authentic chiptune)

Respect NES channel limits from `chiptune-sound-design.md` (pulse1, pulse2,
triangle, noise): at most 2 melodic layers + bass + drums for strict retro.
For denser SNES/indie modern sound, 4–5 layers are fine.

## Vertical layering with multiple files

For a full adaptive system (see `adaptive-music-systems.md`), generate
MULTIPLE projects with the same thematic material at different intensities:

- `stage1_calm` — melody + bass only
- `stage1_combat` — melody + bass + drums + harmony

Use the SAME scale/tonic in both (via `generate_scale` with identical
params) so the leitmotif stays recognizable, then crossfade in the engine.

**Runtime naming convention:**
- `{stage}_calm.ogg` — exploration/calm
- `{stage}_combat.ogg` — combat/tension

## Checklist before calling a composition done

- [ ] Scale chosen via `suggest_scale_for_mood`, not invented manually?
- [ ] At least one drum layer with off-beats?
- [ ] Bass and melody have DIFFERENT lengths (short bass loop vs long melody)?
- [ ] `list_layers` called before export?
- [ ] If user asked for audio: render tool called after `export_midi`?
- [ ] `total_duration_bars_approx` shared with the user for engine loops?

## Build pipeline (`.mid` → `.ogg`) — MCP preferred

Use MCP render tools (step 7 above). CLI fallback:

```bash
python scripts/render_midi.py --mode chip
python scripts/render_midi.py --mode sf2 --soundfont assets/soundfonts/default.sf2
```

Renders `.mid` in `assets/midi/` to `output/audio/{project}/wav/` and `.../ogg/`.

---

## Português

Servidor MCP: **nobu** (`nobu_mcp.py`). Tools em inglês:

`start_project` → `suggest_scale_for_mood` → `add_layer` (×N) →
`list_layers` → `export_midi`.

Moods oficiais: `safe_exploration`, `heroic_exploration`, `nostalgic_town`,
`melancholic_dungeon`, `hostile_exotic_biome`, `magical_dreamlike`,
`combat`, `victory`, `classic_retro` (aliases PT ainda aceitos).

Pastas: MIDI → `assets/midi/`; SF2 → `assets/soundfonts/`; áudio → `output/audio/{project}/wav|ogg/`.

Game-agnostic: o nobu não contém dados do seu jogo.
