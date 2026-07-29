"""
nobu — MCP server for generating chiptune/retro MIDI.

Generates multi-track .mid files with independent channels (melody, harmony,
bass, drums). Designed for game music composition with mood→scale automation.

Usage:
  pip install -r requirements.txt
  python nobu_mcp.py

Then configure in Cursor / Claude Desktop / Kilo Code / your MCP client:
  {
    "mcpServers": {
      "nobu": {
        "command": "python",
        "args": ["/absolute/path/to/nobu_mcp.py"]
      }
    }
  }

This server is game-agnostic — it ships no game-specific data. Biome mappings,
tonal centers, and mood choices come from the caller (game-music-producer skill
+ your game's data).
"""

from __future__ import annotations

from fastmcp import Context, FastMCP
from midiutil import MIDIFile
import os
import json
import sys
import time
from pathlib import Path

mcp = FastMCP("nobu")

_PROJECTS: dict[str, dict] = {}

_REPO_ROOT = Path(__file__).resolve().parent
_DEFAULT_MIDI_DIR = Path(
    os.environ.get("NOBU_MIDI_DIR", str(_REPO_ROOT / "assets" / "midi"))
)
_DEFAULT_OUTPUT_DIR = Path(
    os.environ.get("NOBU_OUTPUT_DIR", str(_REPO_ROOT / "output" / "audio"))
)

# ─── GM Drum Map (EN primary + PT aliases) ──────────────────────────
GM_DRUM_MAP = {
    # English
    "kick": 36,
    "kick_soft": 35,
    "snare": 38,
    "snare_alt": 40,
    "closed_hihat": 42,
    "open_hihat": 46,
    "pedal_hihat": 44,
    "low_tom": 41,
    "mid_tom": 47,
    "high_tom": 50,
    "crash": 49,
    "ride": 51,
    "clap": 39,
    "rimshot": 37,
    # Portuguese aliases
    "bumbo": 36,
    "bumbo_agudo": 35,
    "caixa": 38,
    "caixa_alt": 40,
    "chimbal_fechado": 42,
    "chimbal_aberto": 46,
    "chimbal_pedal": 44,
    "tom_baixo": 41,
    "tom_medio": 47,
    "tom_alto": 50,
}

# ─── Chiptune instrument programs (General MIDI approximations) ────
CHIPTUNE_PROGRAMS = {
    "pulse_lead": 80,  # GM Lead 1 (square) — NES Pulse 1
    "pulse_harmony": 81,  # GM Lead 2 (sawtooth-ish) — NES Pulse 2
    "triangle_bass": 38,  # GM Synth Bass 1 — NES Triangle approximation
    "noise_perc": 0,  # not used; drums use channel 9
}

# ─── Scales (EN keys + PT aliases) ──────────────────────────────────
SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "natural_minor": [0, 2, 3, 5, 7, 8, 10],
    "major_pentatonic": [0, 2, 4, 7, 9],
    "minor_pentatonic": [0, 3, 5, 7, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    # Portuguese aliases
    "maior": [0, 2, 4, 5, 7, 9, 11],
    "menor_natural": [0, 2, 3, 5, 7, 8, 10],
    "pentatonica_maior": [0, 2, 4, 7, 9],
    "pentatonica_menor": [0, 3, 5, 7, 10],
    "dorico": [0, 2, 3, 5, 7, 9, 10],
    "mixolidio": [0, 2, 4, 5, 7, 9, 10],
    "frigio": [0, 1, 3, 5, 7, 8, 10],
    "lidio": [0, 2, 4, 6, 7, 9, 11],
}

SCALE_CANONICAL = {
    "maior": "major",
    "menor_natural": "natural_minor",
    "pentatonica_maior": "major_pentatonic",
    "pentatonica_menor": "minor_pentatonic",
    "dorico": "dorian",
    "mixolidio": "mixolydian",
    "frigio": "phrygian",
    "lidio": "lydian",
}

# ─── Mood → scale mapping (game music theory) ───────────────────────
MOOD_TO_SCALE: dict[str, str] = {
    # English
    "safe_exploration": "major",
    "heroic_exploration": "dorian",
    "nostalgic_town": "mixolydian",
    "melancholic_dungeon": "natural_minor",
    "hostile_exotic_biome": "phrygian",
    "magical_dreamlike": "lydian",
    "combat": "minor_pentatonic",
    "victory": "major",
    "classic_retro": "major_pentatonic",
    # Portuguese aliases
    "exploracao_segura": "major",
    "exploracao_heroica": "dorian",
    "vila_nostalgica": "mixolydian",
    "masmorra_melancolica": "natural_minor",
    "bioma_hostil_exotico": "phrygian",
    "area_magica_onirica": "lydian",
    "combate": "minor_pentatonic",
    "vitoria": "major",
    "retro_classico": "major_pentatonic",
}

LAYER_TYPE_ALIASES = {
    "melody": "melody",
    "harmony": "harmony",
    "bass": "bass",
    "drums": "drums",
    "melodia": "melody",
    "harmonia": "harmony",
    "baixo": "bass",
    "bateria": "drums",
}


def _default_midi_dir() -> str:
    return str(_DEFAULT_MIDI_DIR)


def _default_output_dir() -> str:
    return str(_DEFAULT_OUTPUT_DIR)


def _ensure_midi_path(project_name: str) -> str:
    """Return absolute path to project MIDI, exporting from memory if needed."""
    midi_path = _DEFAULT_MIDI_DIR / f"{project_name}.mid"
    if midi_path.exists():
        return str(midi_path.resolve())
    if project_name in _PROJECTS:
        export_midi(project_name)
        if midi_path.exists():
            return str(midi_path.resolve())
    raise ValueError(
        f"No MIDI at {midi_path}. Call export_midi first or compose via start_project."
    )


def _make_progress_callback(ctx: Context | None):
    def on_progress(stage: str, pct: float) -> None:
        if ctx is not None:
            try:
                ctx.report_progress(progress=pct, total=1.0, message=stage)
                return
            except Exception:
                pass
        print(
            f"[nobu render] {stage} ({pct:.0%})",
            file=sys.stderr,
            flush=True,
        )

    return on_progress


def _render_project_impl(
    project_name: str,
    mode: str = "auto",
    soundfont: str | None = None,
    loop_beats: float = 0,
    destination_dir: str | None = None,
    filename_stem: str | None = None,
    ctx: Context | None = None,
) -> dict:
    import nobu_render

    midi_path = _ensure_midi_path(project_name)
    out_root = destination_dir if destination_dir else _default_output_dir()
    stem = filename_stem or project_name
    return nobu_render.render_midi_file(
        midi_path,
        mode,
        soundfont=soundfont,
        loop_beats=loop_beats,
        output_root=out_root,
        project_name=project_name,
        filename_stem=stem,
        quiet=True,
        on_progress=_make_progress_callback(ctx),
    )


def _normalize_scale(scale_type: str) -> str:
    if scale_type not in SCALES:
        raise ValueError(
            f"Unknown scale '{scale_type}'. Options: "
            f"{sorted(k for k in SCALES if k not in SCALE_CANONICAL)}"
        )
    return SCALE_CANONICAL.get(scale_type, scale_type)


def _generate_scale_impl(tonic_midi: int, scale_type: str, octaves: int) -> dict:
    canonical = _normalize_scale(scale_type)
    intervals = SCALES[canonical]
    pitches = []
    for oct_i in range(octaves):
        for iv in intervals:
            pitches.append(tonic_midi + iv + 12 * oct_i)
    return {
        "scale_type": canonical,
        "tonic_midi": tonic_midi,
        "available_pitches": pitches,
    }


# ─── Tools ──────────────────────────────────────────────────────────

@mcp.tool()
def start_project(project_name: str, bpm: int) -> str:
    """
    ALWAYS call this tool first, before any other, when composing a game
    track. Creates an empty project where layers (independent channels:
    melody, harmony, bass, drums) are added one by one via add_layer.
    Each layer may have a completely different length and rhythm from the
    others (e.g. a 4-note bass loop while the melody plays a 32-note phrase),
    matching how independent channels work on real NES/SNES hardware.
    """
    _PROJECTS[project_name] = {"bpm": bpm, "tracks": [], "tempo_changes": []}
    return (
        f"Project '{project_name}' started at {bpm} BPM. "
        f"Next recommended step: call suggest_scale_for_mood "
        f"to choose the right scale before composing."
    )


@mcp.tool()
def suggest_scale_for_mood(
    mood: str, tonic_midi: int, octaves: int = 2
) -> dict:
    """
    Use this tool BEFORE composing any melody, harmony, or bass line.
    It maps the scene's EMOTION/MOOD to the technically correct musical
    scale (VGM theory: major = joy/safe town, dorian = heroic/adventure,
    phrygian = hostile/exotic, natural_minor = melancholy/dungeon,
    mixolydian = folk/open road, lydian = magical/dreamlike,
    minor_pentatonic = tension/combat).

    Accepted moods: safe_exploration, heroic_exploration, nostalgic_town,
    melancholic_dungeon, hostile_exotic_biome, magical_dreamlike,
    combat, victory, classic_retro.

    Returns the chosen scale AND a list of MIDI pitches ready for
    add_layer — no need to invent note numbers from memory.
    """
    scale_type = MOOD_TO_SCALE.get(mood, "major")
    scale = _generate_scale_impl(tonic_midi, scale_type, octaves)
    scale["mood"] = mood
    scale["chosen_scale"] = scale_type
    return scale


@mcp.tool()
def generate_scale(tonic_midi: int, scale_type: str, octaves: int = 2) -> dict:
    """
    Generate the correct MIDI notes for a musical scale, to use as a
    palette of valid pitches when composing. Use this tool (or
    suggest_scale_for_mood) ALWAYS before inventing note numbers
    manually — that avoids out-of-key / random-sounding melodies.

    scale_type accepts: major, natural_minor, major_pentatonic,
    minor_pentatonic, dorian, mixolydian, phrygian, lydian.
    """
    return _generate_scale_impl(tonic_midi, scale_type, octaves)


@mcp.tool()
def add_layer(
    project_name: str,
    layer_name: str,
    layer_type: str,
    notes: list[list[float | str | int]],
    midi_channel: int = 0,
    chiptune_program: str = "pulse_lead",
    swing_offset: float = 0.0,
) -> str:
    """
    Add ONE independent layer/channel to the project. Call this tool
    multiple times to stack as many layers as you want (melody, harmony,
    bass, drums) — each layer has its own length and rhythm, without
    needing to match the others in note count.

    layer_type accepts: 'melody', 'harmony', 'bass', 'drums'.

    Format of 'notes': each item is [pitch_or_piece, start_time_in_beats,
    duration_in_beats, optional_velocity_0_to_127]. If layer_type='drums',
    pitch may be a string ('kick', 'snare', 'closed_hihat', 'open_hihat',
    'crash', 'ride', 'clap', 'rimshot', 'low_tom', 'mid_tom', 'high_tom')
    or a GM percussion MIDI number. Portuguese drum names are also accepted.

    swing_offset: add a fixed offset (in beats, e.g. 0.02 to 0.08) to every
    ODD-index note, simulating light swing/humanization. Use 0.0 for
    straight quantized rhythm (classic chiptune aesthetic). For deliberate
    off-beats (e.g. hi-hat on 0.5, 1.5, 2.5), place start_time directly in
    the notes list — no swing_offset needed.

    chiptune_program (ignored if layer_type='drums'): 'pulse_lead' (melody,
    NES pulse timbre, GM 80), 'pulse_harmony' (countermelody, GM 81),
    'triangle_bass' (bass, NES triangle approx, GM 38).
    """
    if project_name not in _PROJECTS:
        raise ValueError(
            f"Project '{project_name}' does not exist. Call start_project first."
        )

    normalized_type = LAYER_TYPE_ALIASES.get(layer_type.lower())
    if normalized_type is None:
        raise ValueError(
            f"Unknown layer_type '{layer_type}'. "
            f"Use: melody, harmony, bass, drums."
        )

    proj = _PROJECTS[project_name]
    processed_notes = []
    discarded = 0

    for i, note_info in enumerate(notes):
        if len(note_info) < 3:
            discarded += 1
            continue
        raw_pitch, start_time, duration = (
            note_info[0],
            float(note_info[1]),
            float(note_info[2]),
        )
        volume = (
            int(note_info[3])
            if len(note_info) > 3
            else (85 if normalized_type == "drums" else 95)
        )

        if normalized_type == "drums" and isinstance(raw_pitch, str):
            pitch = GM_DRUM_MAP.get(raw_pitch.lower())
            if pitch is None:
                discarded += 1
                continue
        else:
            try:
                pitch = int(raw_pitch)
            except (ValueError, TypeError):
                discarded += 1
                continue

        if not (0 <= pitch <= 127) or duration <= 0 or start_time < 0:
            discarded += 1
            continue

        adjusted_start = start_time + (swing_offset if i % 2 == 1 else 0.0)
        processed_notes.append(
            {
                "pitch": pitch,
                "start": adjusted_start,
                "duration": duration,
                "volume": max(1, min(127, volume)),
            }
        )

    proj["tracks"].append(
        {
            "name": layer_name,
            "type": normalized_type,
            "channel": midi_channel if normalized_type != "drums" else 9,
            "program": (
                CHIPTUNE_PROGRAMS.get(chiptune_program, 80)
                if normalized_type != "drums"
                else 0
            ),
            "notes": processed_notes,
        }
    )

    warning = f" ({discarded} invalid notes discarded)" if discarded else ""
    return (
        f"Layer '{layer_name}' ({normalized_type}) added with "
        f"{len(processed_notes)} valid notes{warning}. "
        f"Total layers in project: {len(proj['tracks'])}."
    )


@mcp.tool()
def set_tempo_change(
    project_name: str, time_in_beats: float, new_bpm: int
) -> str:
    """
    Schedule a tempo (BPM) change at a specific absolute beat. Use for
    horizontal resequencing inside a single file — e.g. speed up when
    entering boss phase 2, or slow down for tension before a climax.
    """
    if project_name not in _PROJECTS:
        raise ValueError(f"Project '{project_name}' does not exist.")
    _PROJECTS[project_name]["tempo_changes"].append(
        (float(time_in_beats), int(new_bpm))
    )
    return (
        f"Tempo change scheduled: BPM {new_bpm} from beat {time_in_beats}."
    )


@mcp.tool()
def list_layers(project_name: str) -> dict:
    """
    List all layers already added to the project, with note counts and
    duration for each. Use before export_midi to verify that every planned
    layer (melody, bass, drums, harmony) was actually added, or to decide
    whether to add more.
    """
    if project_name not in _PROJECTS:
        raise ValueError(f"Project '{project_name}' does not exist.")
    proj = _PROJECTS[project_name]
    summary = []
    for t in proj["tracks"]:
        dur = max(
            [n["start"] + n["duration"] for n in t["notes"]], default=0.0
        )
        summary.append(
            {
                "name": t["name"],
                "type": t["type"],
                "note_count": len(t["notes"]),
                "duration_beats": round(dur, 2),
            }
        )
    return {
        "project": project_name,
        "bpm": proj["bpm"],
        "layers": summary,
    }


@mcp.tool()
def export_midi(
    project_name: str, destination_dir: str | None = None
) -> str:
    """
    Export all project layers into a single multi-track .mid file.
    Call last, after all add_layer calls. Returns loop metadata (beats
    and bars) for configuring loop points in the engine (Godot/Unity/
    FMOD/Wwise), since MIDI does not store that natively.

    After export, call render_project, render_chip, render_hybrid,
    render_sf2, or render_all_modes to produce audio under
    output/audio/{project_name}/wav/ and .../ogg/.

    Default destination_dir is assets/midi/ (or NOBU_MIDI_DIR).
    """
    if project_name not in _PROJECTS:
        raise ValueError(f"Project '{project_name}' does not exist.")

    proj = _PROJECTS[project_name]
    tracks = proj["tracks"]
    if not tracks:
        return "No layers added. Use add_layer before exporting."

    dest = destination_dir if destination_dir else _default_midi_dir()
    midi_file = MIDIFile(numTracks=len(tracks), deinterleave=False)

    for i in range(len(tracks)):
        midi_file.addTempo(track=i, time=0, tempo=proj["bpm"])
        for tempo_beat, new_bpm in proj["tempo_changes"]:
            midi_file.addTempo(track=i, time=tempo_beat, tempo=new_bpm)

    max_end_time = 0.0
    for i, track in enumerate(tracks):
        channel = track["channel"]
        if track["type"] != "drums":
            midi_file.addProgramChange(i, channel, 0, track["program"])
        for n in track["notes"]:
            midi_file.addNote(
                track=i,
                channel=channel,
                pitch=n["pitch"],
                time=n["start"],
                duration=n["duration"],
                volume=n["volume"],
            )
            max_end_time = max(max_end_time, n["start"] + n["duration"])

    os.makedirs(dest, exist_ok=True)
    path = os.path.abspath(os.path.join(dest, f"{project_name}.mid"))
    with open(path, "wb") as f:
        midi_file.writeFile(f)

    beats_per_bar = 4
    metadata = {
        "file": path,
        "layers": [t["name"] for t in tracks],
        "total_duration_beats": round(max_end_time, 3),
        "total_duration_bars_approx": round(max_end_time / beats_per_bar, 2),
        "note": (
            "MIDI does not store a native loop point. "
            "Use these beat/bar values to configure looping in your engine."
        ),
        "next_step": (
            f"Call get_render_capabilities() before hybrid/sf2. "
            f"Then render_chip('{project_name}') for fast audio, or "
            f"render_all_modes('{project_name}') only if the user wants all three "
            f"compared — read mode_effective and quality_warnings in each result."
        ),
    }
    return json.dumps(metadata, ensure_ascii=False, indent=2)


@mcp.tool()
def get_render_capabilities() -> dict:
    """
    Report render pipeline health: FluidSynth, ffmpeg, tinysoundfont,
    available soundfonts, and which modes (chip/hybrid/sf2) will work.
    Call before promising SF2/hybrid audio to the user.
    """
    import nobu_render

    return nobu_render.get_render_capabilities_impl()


@mcp.tool()
def list_soundfonts() -> dict:
    """
    List .sf2 files in assets/soundfonts/ plus NOBU_SF2 env override.
    The repo ships no soundfonts by default — chip mode always works.
    """
    import nobu_render

    return nobu_render.list_soundfonts_impl()


@mcp.tool(timeout=300)
def render_project(
    project_name: str,
    mode: str = "auto",
    soundfont: str | None = None,
    loop_beats: float = 0,
    destination_dir: str | None = None,
    ctx: Context | None = None,
) -> str:
    """
    Render exported MIDI to WAV/OGG. mode: chip | hybrid | sf2 | auto.
    Output: output/audio/{project_name}/wav/ and .../ogg/.
    Exports MIDI first if the project exists in memory but .mid is missing.
    Prefer render_chip for first audio delivery; use render_all_modes only when
    the user wants chip + hybrid + sf2 compared (slower).
    """
    result = _render_project_impl(
        project_name, mode, soundfont, loop_beats, destination_dir, ctx=ctx
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool(timeout=300)
def render_chip(
    project_name: str,
    loop_beats: float = 0,
    destination_dir: str | None = None,
    ctx: Context | None = None,
) -> str:
    """
    Render pure chiptune (no SF2). Preferred first audio delivery tool.
    Fast and always works without soundfonts. Use render_all_modes only when
    the user explicitly wants chip + hybrid + sf2 compared.
    """
    result = _render_project_impl(
        project_name, "chip", None, loop_beats, destination_dir, ctx=ctx
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool(timeout=300)
def render_hybrid(
    project_name: str,
    soundfont: str | None = None,
    loop_beats: float = 0,
    destination_dir: str | None = None,
    ctx: Context | None = None,
) -> str:
    """
    Render SF2 drums + chiptune melodic. Falls back to chip if SF2/tsf missing.
    """
    result = _render_project_impl(
        project_name, "hybrid", soundfont, loop_beats, destination_dir, ctx=ctx
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool(timeout=300)
def render_sf2(
    project_name: str,
    soundfont: str | None = None,
    loop_beats: float = 0,
    destination_dir: str | None = None,
    ctx: Context | None = None,
) -> str:
    """
    Render full SoundFont via FluidSynth. Falls back to hybrid or chip.
    Requires FluidSynth on PATH and a .sf2 file. Use get_render_capabilities
    to check availability first.
    """
    result = _render_project_impl(
        project_name, "sf2", soundfont, loop_beats, destination_dir, ctx=ctx
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool(timeout=300)
def render_all_modes(
    project_name: str,
    soundfont: str | None = None,
    destination_dir: str | None = None,
    ctx: Context | None = None,
) -> str:
    """
    Render chip, hybrid, and sf2 versions in one call (compare modes).
    Slow (up to ~3 min) — use only when the user asks for all versions.
    For normal delivery use render_chip first.
    Output files: {project}_chip, {project}_hybrid, {project}_sf2 under
    output/audio/{project_name}/wav/ and .../ogg/.
    Always report mode_effective, fallback_reason, and quality_warnings per mode.
    """
    modes = ("chip", "hybrid", "sf2")
    out: dict = {"project": project_name, "modes": {}}
    all_quality: list[str] = []
    t0 = time.perf_counter()
    for m in modes:
        result = _render_project_impl(
            project_name,
            m,
            soundfont,
            0,
            destination_dir,
            f"{project_name}_{m}",
            ctx=ctx,
        )
        out["modes"][m] = result
        for w in result.get("quality_warnings") or []:
            all_quality.append(f"{m}: {w}")
        if "output_dir" not in out:
            out["output_dir"] = result.get("output_dir")
            out["midi_file"] = result.get("midi_file")

    if all_quality:
        out["quality_warnings"] = all_quality
    out["render_duration_sec"] = round(time.perf_counter() - t0, 3)
    return json.dumps(out, ensure_ascii=False, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
