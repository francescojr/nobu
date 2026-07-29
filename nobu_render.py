"""
Shared MIDI → WAV/OGG render library for nobu (CLI, MCP, batch scripts).

Modes: chip | hybrid | sf2 | auto — never hard-fails without SF2.

Output layout (default):
  {NOBU_OUTPUT_DIR}/{project_name}/wav/{stem}.wav
  {NOBU_OUTPUT_DIR}/{project_name}/ogg/{stem}.ogg

Env: NOBU_MIDI_DIR, NOBU_OUTPUT_DIR, NOBU_SF2 (or FLUID_SYNTH_SF2).
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import mido

SAMPLE_RATE = 44100
CHIP_SR = 22050
MIN_AUDIO_BYTES = 8192
# SF2 WAV below this bytes/sec on long tracks likely means fallback/chip, not real FS.
MIN_SF2_BYTES_PER_SEC = 80_000
MIN_SF2_QUALITY_DURATION_SEC = 15.0

FLUIDSYNTH_WINDOWS_CANDIDATES = (
    Path(r"C:\Program Files\FluidSynth\bin\fluidsynth.exe"),
    Path(r"C:\Program Files (x86)\FluidSynth\bin\fluidsynth.exe"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "fluidsynth.exe",
)

ROOT = Path(__file__).resolve().parent
MIDI_DIR = Path(os.environ.get("NOBU_MIDI_DIR", str(ROOT / "assets" / "midi")))
OUT_DIR = Path(os.environ.get("NOBU_OUTPUT_DIR", str(ROOT / "output" / "audio")))
DEFAULT_SF2 = ROOT / "assets" / "soundfonts" / "default.sf2"

ADSR = {
    "pulse_lead": {"a": 0.008, "d": 0.04, "s": 0.70, "r": 0.04},
    "pulse_harmony": {"a": 0.015, "d": 0.06, "s": 0.55, "r": 0.08},
    "triangle_bass": {"a": 0.015, "d": 0.08, "s": 0.75, "r": 0.10},
    "kick": {"a": 0.001, "d": 0.12, "s": 0.0, "r": 0.02},
    "snare": {"a": 0.001, "d": 0.08, "s": 0.0, "r": 0.03},
    "hihat_closed": {"a": 0.001, "d": 0.03, "s": 0.0, "r": 0.01},
    "hihat_open": {"a": 0.001, "d": 0.15, "s": 0.0, "r": 0.05},
    "crash": {"a": 0.001, "d": 0.40, "s": 0.0, "r": 0.10},
}


def midi_to_freq(note: int) -> float:
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


def adsr_gain_array(t: np.ndarray, dur: float, p: dict) -> np.ndarray:
    a, d, s, r = p["a"], p["d"], p["s"], p["r"]
    env = np.zeros_like(t, dtype=np.float64)
    sustain_end = max(dur - r, 0.0)
    ms = (t >= a + d) & (t < sustain_end)
    env[ms] = s
    md = (t >= a) & (t < a + d)
    if np.any(md):
        env[md] = 1.0 - (1.0 - s) * ((t[md] - a) / d) if d > 0 else s
    ma = t < a
    if np.any(ma):
        env[ma] = (t[ma] / a) if a > 0 else 1.0
    if r > 0:
        mr = t >= sustain_end
        rt = t[mr] - sustain_end
        env[mr] = s * np.maximum(1.0 - rt / max(r, 0.001), 0.0)
        env[t >= dur] = 0.0
    return env.astype(np.float32)


ProgressCallback = Callable[[str, float], None]


def _emit_progress(
    on_progress: ProgressCallback | None,
    stages: list[str],
    stage: str,
    pct: float,
) -> None:
    stages.append(stage)
    if on_progress:
        on_progress(stage, pct)


def parse_midi(path: str) -> dict:
    mid = mido.MidiFile(path)
    ticks = mid.ticks_per_beat
    tempo = 500000
    for msg in mid.tracks[0]:
        if msg.type == "set_tempo":
            tempo = msg.tempo
            break
    sec_per_tick = (tempo / 1_000_000.0) / ticks

    drum_notes = []
    mel_tracks = []

    for track in mid.tracks:
        notes = []
        prog = 0
        abs_t = 0
        pending = {}
        is_drums = False
        for msg in track:
            abs_t += msg.time
            if msg.type == "program_change":
                prog = msg.program
            elif msg.type == "note_on" and msg.velocity > 0:
                key = (msg.channel, msg.note)
                pending[key] = {
                    "pitch": msg.note,
                    "vel": msg.velocity,
                    "start_tick": abs_t,
                    "ch": msg.channel,
                }
                if msg.channel == 9:
                    is_drums = True
            elif msg.type == "note_off" or (
                msg.type == "note_on" and msg.velocity == 0
            ):
                key = (msg.channel, msg.note)
                if key in pending:
                    n = pending.pop(key)
                    n["start_sec"] = n["start_tick"] * sec_per_tick
                    n["dur_sec"] = max(
                        (abs_t - n["start_tick"]) * sec_per_tick, 0.01
                    )
                    notes.append(n)
        if not notes:
            continue
        if is_drums:
            drum_notes.extend(notes)
        else:
            mel_tracks.append({"notes": notes, "program": prog})

    total_dur = 0.0
    for n in drum_notes:
        total_dur = max(total_dur, n["start_sec"] + n["dur_sec"])
    for t in mel_tracks:
        for n in t["notes"]:
            total_dur = max(total_dur, n["start_sec"] + n["dur_sec"])

    return {
        "drums": drum_notes,
        "melodic": mel_tracks,
        "bpm": 60_000_000 / tempo,
        "duration": total_dur,
    }


def find_soundfont(custom: str | None = None) -> str:
    if custom and os.path.exists(custom):
        return custom
    for env_key in ("NOBU_SF2", "FLUID_SYNTH_SF2"):
        env_sf = os.environ.get(env_key)
        if env_sf and os.path.exists(env_sf):
            return env_sf
    if DEFAULT_SF2.exists():
        return str(DEFAULT_SF2)
    if custom:
        alt = ROOT / "assets" / "soundfonts" / Path(custom).name
        if alt.exists():
            return str(alt)
    return ""


def has_tinysoundfont() -> bool:
    try:
        import tinysoundfont  # noqa: F401

        return True
    except ImportError:
        return False


def resolve_fluidsynth() -> str | None:
    """Return absolute path to fluidsynth CLI, or None."""
    env_bin = os.environ.get("FLUIDSYNTH")
    if env_bin and Path(env_bin).is_file():
        return str(Path(env_bin).resolve())
    found = shutil.which("fluidsynth")
    if found:
        return found
    if platform.system() == "Windows":
        for candidate in FLUIDSYNTH_WINDOWS_CANDIDATES:
            if candidate.is_file():
                return str(candidate.resolve())
    return None


def fluidsynth_version(fluidsynth_path: str | None = None) -> str | None:
    exe = fluidsynth_path or resolve_fluidsynth()
    if not exe:
        return None
    try:
        result = subprocess.run(
            [exe, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    line = (result.stdout or result.stderr or "").strip().splitlines()
    return line[0] if line else None


def has_fluidsynth() -> bool:
    return resolve_fluidsynth() is not None


def build_fluidsynth_cmd(
    sf2_path: str,
    midi_path: str,
    wav_path: str,
    *,
    fluidsynth_exe: str | None = None,
) -> list[str]:
    """Build FluidSynth argv (-F and rate flags before soundfont/midi — FS 2.5.x)."""
    exe = fluidsynth_exe or resolve_fluidsynth() or "fluidsynth"
    return [
        exe,
        "-ni",
        "-F",
        wav_path,
        "-r",
        str(SAMPLE_RATE),
        "-R",
        "0",
        "-g",
        "1.5",
        sf2_path,
        midi_path,
    ]


def assess_render_quality(
    *,
    mode_requested: str,
    mode_effective: str,
    wav_path: str | None,
    duration_sec: float,
) -> list[str]:
    warnings: list[str] = []
    if mode_requested in ("sf2", "auto") and mode_effective != mode_requested:
        if mode_requested == "sf2" and mode_effective in ("hybrid", "chip"):
            warnings.append(
                f"mode_requested=sf2 but mode_effective={mode_effective} — not full SF2"
            )
        elif mode_requested == "auto" and mode_effective == "chip":
            warnings.append("auto resolved to chip — hybrid/sf2 deps missing")
    if (
        mode_effective == "sf2"
        and wav_path
        and os.path.isfile(wav_path)
        and duration_sec > MIN_SF2_QUALITY_DURATION_SEC
    ):
        wav_size = os.path.getsize(wav_path)
        min_expected = int(duration_sec * MIN_SF2_BYTES_PER_SEC)
        if wav_size < min_expected:
            warnings.append(
                "sf2_wav_suspiciously_small — verify FluidSynth ran (expected larger WAV)"
            )
    return warnings


def audio_output_paths(
    output_root: str | Path,
    project_name: str,
    filename_stem: str,
    *,
    flat_legacy: bool = False,
    legacy_out_base: str | None = None,
) -> dict[str, str]:
    if flat_legacy and legacy_out_base:
        base = Path(legacy_out_base)
        stem = base.name
        return {
            "output_dir": str(base.parent.resolve()),
            "wav": str((base.parent / f"{stem}.wav").resolve()),
            "ogg": str((base.parent / f"{stem}.ogg").resolve()),
        }
    project_dir = Path(output_root) / project_name
    return {
        "output_dir": str(project_dir.resolve()),
        "wav": str((project_dir / "wav" / f"{filename_stem}.wav").resolve()),
        "ogg": str((project_dir / "ogg" / f"{filename_stem}.ogg").resolve()),
    }


def list_soundfonts_impl() -> dict:
    sf2_dir = ROOT / "assets" / "soundfonts"
    found: list[dict] = []
    if sf2_dir.is_dir():
        for p in sorted(sf2_dir.glob("*.sf2")):
            found.append(
                {
                    "path": str(p.resolve()),
                    "name": p.name,
                    "is_default": p.name == "default.sf2",
                }
            )
    for env_key in ("NOBU_SF2", "FLUID_SYNTH_SF2"):
        env_sf = os.environ.get(env_key)
        if env_sf and Path(env_sf).exists():
            p = Path(env_sf)
            entry = {
                "path": str(p.resolve()),
                "name": p.name,
                "is_default": False,
                "source": env_key,
            }
            if not any(x["path"] == entry["path"] for x in found):
                found.append(entry)
    note = None
    if not found:
        note = (
            "No SF2 in assets/soundfonts/. Chip mode always works. "
            "Copy your .sf2 to assets/soundfonts/default.sf2 or set NOBU_SF2. "
            "Re-check: python scripts/bootstrap.py --doctor"
        )
    return {"soundfonts": found, "note": note}


def get_render_capabilities_impl() -> dict:
    sf2_path = find_soundfont()
    sf2_ok = bool(sf2_path)
    fs_path = resolve_fluidsynth()
    fs_ok = fs_path is not None
    fs_version = fluidsynth_version(fs_path) if fs_path else None
    tsf_ok = has_tinysoundfont()
    ffmpeg_ok = shutil.which("ffmpeg") is not None

    modes_available = {
        "chip": True,
        "hybrid": sf2_ok and tsf_ok,
        "sf2": sf2_ok and fs_ok,
    }
    install_hints: list[str] = []
    if not sf2_ok:
        install_hints.append(
            "Place default.sf2 in assets/soundfonts/ or set NOBU_SF2"
        )
    if not tsf_ok:
        install_hints.append("pip install tinysoundfont  # hybrid mode")
    if not fs_ok:
        if platform.system() == "Windows":
            install_hints.append(
                "winget install FluidSynth.FluidSynth  # sf2 mode; restart MCP session after install"
            )
        else:
            install_hints.append("Install FluidSynth CLI on PATH  # sf2 mode")
    if not ffmpeg_ok:
        install_hints.append(
            "Install ffmpeg for WAV→OGG (recommended on Windows)"
        )

    return {
        "fluidsynth": fs_ok,
        "fluidsynth_path": fs_path,
        "fluidsynth_version": fs_version,
        "ffmpeg": ffmpeg_ok,
        "tinysoundfont": tsf_ok,
        "sf2_found": sf2_ok,
        "default_sf2": sf2_path or None,
        "soundfonts": list_soundfonts_impl().get("soundfonts", []),
        "modes_available": modes_available,
        "install_hints": install_hints,
    }


def _synth_kick(duration: float, volume: float, sr: int) -> np.ndarray:
    n = int(duration * sr)
    if n <= 0:
        return np.zeros(1, dtype=np.float32)
    t = np.arange(n, dtype=np.float32) / sr
    vol = volume / 127.0
    env = adsr_gain_array(t, duration, ADSR["kick"])
    freq = np.maximum(100.0 - (65.0 * (t / max(duration, 0.001))), 30.0)
    body = np.sin(2.0 * np.pi * freq * t)
    click = np.zeros(n, dtype=np.float32)
    cm = t < 0.002
    click[cm] = (
        np.sin(2.0 * np.pi * 1000.0 * t[cm]) * (1.0 - t[cm] / 0.002) * 0.3
    )
    out = np.tanh((body + click) * 2.0) * env * vol * 1.2
    out[env <= 0.001] = 0.0
    return out.astype(np.float32)


def _synth_snare(duration: float, volume: float, sr: int) -> np.ndarray:
    n = int(duration * sr)
    if n <= 0:
        return np.zeros(1, dtype=np.float32)
    t = np.arange(n, dtype=np.float32) / sr
    vol = volume / 127.0
    env = adsr_gain_array(t, duration, ADSR["snare"])
    tone = np.sin(2.0 * np.pi * 180.0 * t) * 0.4
    ring = np.sin(2.0 * np.pi * 400.0 * t) * 0.15
    noise = np.random.random(n).astype(np.float32) * 2.0 - 1.0
    wav = tone + ring + noise * 0.7
    wav[t < 0.003] *= 1.3
    out = wav * env * vol
    out[env <= 0.001] = 0.0
    return out.astype(np.float32)


def _synth_hihat(duration: float, volume: float, sr: int, open_hat: bool) -> np.ndarray:
    n = int(duration * sr)
    if n <= 0:
        return np.zeros(1, dtype=np.float32)
    t = np.arange(n, dtype=np.float32) / sr
    vol = volume / 127.0
    p = ADSR["hihat_open" if open_hat else "hihat_closed"]
    gain = 0.8 if open_hat else 0.55
    env = adsr_gain_array(t, duration, p)
    noise = np.random.random(n).astype(np.float32) * 2.0 - 1.0
    out = noise * env * vol * gain
    out[env <= 0.001] = 0.0
    return out.astype(np.float32)


def _synth_crash(duration: float, volume: float, sr: int) -> np.ndarray:
    n = int(duration * sr)
    if n <= 0:
        return np.zeros(1, dtype=np.float32)
    t = np.arange(n, dtype=np.float32) / sr
    vol = volume / 127.0
    env = adsr_gain_array(t, duration, ADSR["crash"])
    noise = np.random.random(n).astype(np.float32) * 2.0 - 1.0
    out = noise * env * vol * 0.5
    out[env <= 0.001] = 0.0
    return out.astype(np.float32)


def synth_drum_hit(pitch: int, duration: float, volume: float, sr: int) -> np.ndarray:
    dur = max(duration, 0.02)
    if pitch in (35, 36):
        return _synth_kick(dur, volume, sr)
    if pitch in (38, 40):
        return _synth_snare(dur, volume, sr)
    if pitch == 42:
        return _synth_hihat(dur, volume, sr, open_hat=False)
    if pitch == 46:
        return _synth_hihat(dur, volume, sr, open_hat=True)
    if pitch in (49, 57):
        return _synth_crash(max(dur, 0.2), volume, sr)
    return _synth_hihat(dur * 0.5, volume, sr, open_hat=False)


def render_drums_chip(drum_notes: list) -> np.ndarray:
    if not drum_notes:
        return np.zeros(1, dtype=np.float32)
    total_dur = max(n["start_sec"] + n["dur_sec"] for n in drum_notes) + 0.5
    buf = np.zeros(int(total_dur * SAMPLE_RATE) + SAMPLE_RATE, dtype=np.float32)
    for n in drum_notes:
        hit = synth_drum_hit(n["pitch"], n["dur_sec"], n["vel"], SAMPLE_RATE)
        start = int(n["start_sec"] * SAMPLE_RATE)
        end = start + len(hit)
        if end > len(buf):
            buf = np.pad(buf, (0, end - len(buf)))
        buf[start:end] += hit
    peak = float(np.max(np.abs(buf)))
    if peak > 0.001:
        buf /= peak
    return buf


def render_drums_sf2(drum_notes: list, sf2_path: str) -> np.ndarray:
    if not drum_notes:
        return np.zeros(1, dtype=np.float32)

    import tinysoundfont as tsf

    events = []
    for n in drum_notes:
        events.append((n["start_sec"], "on", n["pitch"], n["vel"]))
        events.append((n["start_sec"] + n["dur_sec"], "off", n["pitch"], 0))
    events.sort(key=lambda x: x[0])
    total_dur = max(e[0] for e in events) + 0.5

    synth = tsf.Synth(samplerate=SAMPLE_RATE)
    sfid = synth.sfload(sf2_path)
    synth.program_select(9, sfid, 128, 0, is_drums=True)
    synth.start()

    BLOCK = 4096
    chunks = []
    prev_t = 0.0

    for t, action, note, vel in events:
        dt = t - prev_t
        if dt > 0.0001:
            frames = int(dt * SAMPLE_RATE)
            while frames > 0:
                n = min(BLOCK, frames)
                chunks.append(bytes(synth.generate(n)))
                frames -= n
        if action == "on":
            synth.noteon(9, note, vel)
        else:
            synth.noteoff(9, note)
        prev_t = t

    frames = int(0.5 * SAMPLE_RATE)
    while frames > 0:
        n = min(BLOCK, frames)
        chunks.append(bytes(synth.generate(n)))
        frames -= n
    synth.stop()

    stereo = np.frombuffer(b"".join(chunks), dtype=np.float32).reshape(-1, 2)
    mono = stereo.mean(axis=1)
    peak = float(np.max(np.abs(mono)))
    if peak > 0.001:
        mono /= peak
    max_s = int(total_dur * SAMPLE_RATE)
    if len(mono) > max_s:
        mono = mono[:max_s]
    return mono


def _melodic_waveform(phase: np.ndarray, wt: str, duty: float) -> np.ndarray:
    if wt == "square":
        return np.where(phase < duty, 1.0, -1.0).astype(np.float32)
    if wt == "triangle":
        return np.where(
            phase < 0.25,
            4.0 * phase,
            np.where(phase < 0.75, 2.0 - 4.0 * phase, 4.0 * phase - 4.0),
        ).astype(np.float32)
    return np.where(phase < 0.5, 1.0, -1.0).astype(np.float32)


def render_melodic(
    mel_tracks: list,
    on_note_progress: Callable[[float], None] | None = None,
) -> np.ndarray:
    if not mel_tracks:
        return np.zeros(1, dtype=np.float32)

    total_dur = 0.0
    total_notes = 0
    for t in mel_tracks:
        total_notes += len(t["notes"])
        for n in t["notes"]:
            total_dur = max(total_dur, n["start_sec"] + n["dur_sec"])
    total_samples = int(total_dur * CHIP_SR) + CHIP_SR
    mixed = np.zeros(total_samples, dtype=np.float32)
    progress_stride = max(1, total_notes // 10) if total_notes else 1
    notes_done = 0

    for t in mel_tracks:
        prog = t["program"]
        if prog == 80:
            wt, ak, duty = "square", "pulse_lead", 0.375
        elif prog == 81:
            wt, ak, duty = "square", "pulse_harmony", 0.5
        elif prog == 38:
            wt, ak, duty = "triangle", "triangle_bass", 0.5
        else:
            wt, ak, duty = "square", "pulse_lead", 0.5

        adsr_p = ADSR[ak]
        gain = 0.22 / 127.0

        for n in t["notes"]:
            start = int(n["start_sec"] * CHIP_SR)
            dur = max(n["dur_sec"], 0.005)
            freq = midi_to_freq(n["pitch"])
            vel = n["vel"]
            n_s = int(dur * CHIP_SR)
            if n_s <= 0:
                continue
            t_arr = np.arange(n_s, dtype=np.float32) / CHIP_SR
            env = adsr_gain_array(t_arr, dur, adsr_p)
            phase = (freq * t_arr) % 1.0
            wav = _melodic_waveform(phase, wt, duty)
            buf = wav * env * vel * gain
            buf[env <= 0.001] = 0.0
            end = start + n_s
            if end > total_samples:
                n_s = total_samples - start
            if n_s > 0:
                mixed[start : start + n_s] += buf[:n_s]
            notes_done += 1
            if on_note_progress and total_notes > 0:
                if notes_done % progress_stride == 0 or notes_done == total_notes:
                    on_note_progress(notes_done / total_notes)

    return mixed


def mix_down(drums: np.ndarray, melodic: np.ndarray) -> np.ndarray:
    if len(melodic) > 1:
        ratio = SAMPLE_RATE / CHIP_SR
        new_len = int(len(melodic) * ratio)
        x_old = np.arange(len(melodic), dtype=np.float64)
        x_new = np.linspace(0.0, float(len(melodic) - 1), new_len, dtype=np.float64)
        melodic = np.interp(x_new, x_old, melodic).astype(np.float32)
    else:
        melodic = np.zeros(max(len(drums), 1), dtype=np.float32)

    mx = max(len(drums), len(melodic))
    if len(drums) < mx:
        drums = np.pad(drums, (0, mx - len(drums)))
    if len(melodic) < mx:
        melodic = np.pad(melodic, (0, mx - len(melodic)))

    mixed = drums * 0.65 + melodic * 0.55
    peak = float(np.max(np.abs(mixed)))
    if peak > 0.95:
        mixed *= 0.90 / peak
    return mixed


def wav_to_ogg(wav_path: str, ogg_path: str, quiet: bool = False) -> bool:
    if os.path.isfile(ogg_path) and os.path.getsize(ogg_path) < MIN_AUDIO_BYTES:
        try:
            os.remove(ogg_path)
        except OSError:
            pass

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        try:
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    wav_path,
                    "-c:a",
                    "libvorbis",
                    "-q:a",
                    "5",
                    ogg_path,
                ],
                check=True,
                timeout=120,
            )
            if os.path.isfile(ogg_path) and os.path.getsize(ogg_path) >= MIN_AUDIO_BYTES:
                if not quiet:
                    print(
                        f"OGG: {ogg_path} ({os.path.getsize(ogg_path) / 1024:.0f} KB) [ffmpeg]"
                    )
                return True
        except Exception as e:
            if not quiet:
                print(f"  (ffmpeg OGG skip: {e})")

    if sys.platform == "win32":
        if not quiet:
            print("  (OGG skipped — install ffmpeg for WAV→OGG on Windows)")
        return False

    try:
        import soundfile as sf

        data, rate = sf.read(wav_path)
        sf.write(ogg_path, data, rate, format="OGG", subtype="VORBIS")
        if os.path.isfile(ogg_path) and os.path.getsize(ogg_path) >= MIN_AUDIO_BYTES:
            if not quiet:
                print(
                    f"OGG: {ogg_path} ({os.path.getsize(ogg_path) / 1024:.0f} KB) [soundfile]"
                )
            return True
        if os.path.isfile(ogg_path):
            try:
                os.remove(ogg_path)
            except OSError:
                pass
    except Exception as e:
        if not quiet:
            print(f"  (soundfile OGG skip: {e})")

    if not quiet:
        print("  (OGG skipped — install ffmpeg or soundfile with Vorbis)")
    return False


def write_output(
    mixed: np.ndarray,
    wav_path: str,
    ogg_path: str,
    loop_beats: float = 0,
    bpm: float = 152,
    quiet: bool = False,
) -> dict:
    import soundfile as sf

    if loop_beats > 0:
        loop_samples = int(loop_beats * (60.0 / bpm) * SAMPLE_RATE)
        if loop_samples < len(mixed):
            mixed = mixed[:loop_samples].copy()

    os.makedirs(os.path.dirname(wav_path) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(ogg_path) or ".", exist_ok=True)
    sf.write(wav_path, mixed, SAMPLE_RATE, subtype="PCM_16")
    if not quiet:
        print(f"WAV: {wav_path} ({os.path.getsize(wav_path) / 1024:.0f} KB)")
    ogg_ok = wav_to_ogg(wav_path, ogg_path, quiet=quiet)
    result = {"wav": wav_path, "ogg": ogg_path if ogg_ok else None}
    if not ogg_ok:
        result["ogg_skipped_reason"] = (
            "OGG conversion failed or skipped — WAV is available; install ffmpeg"
        )
    return result


def _fluidsynth_output_ok(result: subprocess.CompletedProcess, wav_path: str) -> bool:
    combined = f"{result.stderr or ''}{result.stdout or ''}".lower()
    if "fluidsynth: error:" in combined:
        return False
    if not os.path.isfile(wav_path):
        return False
    if os.path.getsize(wav_path) < MIN_AUDIO_BYTES:
        return False
    return True


def render_full_sf2(
    midi_path: str,
    sf2_path: str,
    wav_path: str,
    ogg_path: str,
    quiet: bool = False,
) -> dict:
    os.makedirs(os.path.dirname(wav_path) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(ogg_path) or ".", exist_ok=True)

    fs_exe = resolve_fluidsynth()
    if not fs_exe:
        if not quiet:
            print("  FluidSynth not on PATH")
        return {"ok": False, "reason": "fluidsynth not on PATH"}

    cmd_wav = build_fluidsynth_cmd(sf2_path, midi_path, wav_path, fluidsynth_exe=fs_exe)
    try:
        result = subprocess.run(
            cmd_wav, capture_output=True, text=True, timeout=90
        )
    except FileNotFoundError:
        if not quiet:
            print("  FluidSynth not on PATH")
        return {"ok": False, "reason": "fluidsynth not on PATH"}
    except subprocess.TimeoutExpired:
        if not quiet:
            print("  FluidSynth timed out")
        return {"ok": False, "reason": "fluidsynth timed out"}

    if not _fluidsynth_output_ok(result, wav_path):
        err = (result.stderr or result.stdout or "").strip()
        snippet = err[:200] if err else f"exit={result.returncode}, missing/tiny WAV"
        if not quiet:
            print(f"  FluidSynth failed: {snippet}")
        if os.path.isfile(wav_path) and os.path.getsize(wav_path) < MIN_AUDIO_BYTES:
            try:
                os.remove(wav_path)
            except OSError:
                pass
        return {"ok": False, "reason": snippet}

    if not quiet:
        print(f"WAV: {wav_path} ({os.path.getsize(wav_path) / 1024:.0f} KB) [FluidSynth]")
    ogg_ok = wav_to_ogg(wav_path, ogg_path, quiet=quiet)
    out = {"ok": True, "wav": wav_path, "ogg": ogg_path if ogg_ok else None}
    if not ogg_ok:
        out["ogg_skipped_reason"] = (
            "OGG conversion failed or skipped — WAV is available; install ffmpeg"
        )
    return out


def resolve_mode(requested: str, sf2_path: str) -> tuple[str, str]:
    tsf_ok = has_tinysoundfont()
    fs_ok = has_fluidsynth()
    sf2_ok = bool(sf2_path and os.path.exists(sf2_path))

    if requested == "chip":
        return "chip", "pure chiptune (no SF2)"

    if requested == "hybrid":
        if sf2_ok and tsf_ok:
            return "hybrid", f"SF2 drums + chiptune melodic ({sf2_path})"
        reasons = []
        if not sf2_ok:
            reasons.append("no soundfont")
        if not tsf_ok:
            reasons.append("tinysoundfont not installed")
        return "chip", (
            "hybrid requested but "
            + ", ".join(reasons)
            + " — falling back to pure chiptune"
        )

    if requested == "sf2":
        if sf2_ok and fs_ok:
            return "sf2", f"full SoundFont via FluidSynth ({sf2_path})"
        reasons = []
        if not sf2_ok:
            reasons.append("no soundfont")
        if not fs_ok:
            reasons.append("fluidsynth not on PATH")
        if sf2_ok and tsf_ok:
            return "hybrid", (
                "sf2 requested but FluidSynth unavailable — "
                "falling back to hybrid (SF2 drums + chip melodic)"
            )
        return "chip", (
            "sf2 requested but "
            + ", ".join(reasons)
            + " — falling back to pure chiptune"
        )

    if sf2_ok and tsf_ok:
        return "hybrid", f"auto → hybrid ({sf2_path})"
    if sf2_ok and fs_ok:
        return "sf2", f"auto → full SF2 ({sf2_path})"
    return "chip", "auto → pure chiptune (no SF2 / FluidSynth / tinysoundfont)"


def render_chip_or_hybrid(
    data: dict,
    mode: str,
    sf2_path: str,
    wav_path: str,
    ogg_path: str,
    loop_beats: float,
    quiet: bool = False,
    on_progress: ProgressCallback | None = None,
    stages: list[str] | None = None,
) -> dict:
    stage_log = stages if stages is not None else []
    if mode == "hybrid":
        if not quiet:
            print("Drums via SF2...", end=" ", flush=True)
        _emit_progress(on_progress, stage_log, "synthesizing_drums", 0.3)
        try:
            drums = render_drums_sf2(data["drums"], sf2_path)
        except Exception as e:
            if not quiet:
                print(f"failed ({e}) — chip drums")
            drums = render_drums_chip(data["drums"])
        else:
            if not quiet:
                print(f"peak={float(np.max(np.abs(drums))):.3f}")
    else:
        if not quiet:
            print("Drums via chiptune...", end=" ", flush=True)
        _emit_progress(on_progress, stage_log, "synthesizing_drums", 0.3)
        drums = render_drums_chip(data["drums"])
        if not quiet:
            print(f"peak={float(np.max(np.abs(drums))):.3f}")

    if not quiet:
        print("Melodic via chiptune...", end=" ", flush=True)
    _emit_progress(on_progress, stage_log, "synthesizing_melodic", 0.6)

    def _melodic_sub_progress(sub: float) -> None:
        if on_progress:
            on_progress("synthesizing_melodic", 0.6 + 0.2 * sub)

    melodic = render_melodic(
        data["melodic"],
        on_note_progress=_melodic_sub_progress if on_progress else None,
    )
    if not quiet:
        print(f"peak={float(np.max(np.abs(melodic))):.3f}")

    if not quiet:
        print("Mixing...", end=" ", flush=True)
    _emit_progress(on_progress, stage_log, "mixing", 0.8)
    mixed = mix_down(drums, melodic)
    if not quiet:
        print(f"peak={float(np.max(np.abs(mixed))):.3f}")

    _emit_progress(on_progress, stage_log, "writing_wav", 0.9)
    out = write_output(mixed, wav_path, ogg_path, loop_beats, data["bpm"], quiet=quiet)
    _emit_progress(on_progress, stage_log, "writing_ogg", 1.0)
    return out


def render_midi_file(
    midi_path: str,
    mode: str = "auto",
    *,
    soundfont: str | None = None,
    loop_beats: float = 0,
    output_root: str | Path | None = None,
    project_name: str | None = None,
    filename_stem: str | None = None,
    flat_legacy: bool = False,
    legacy_out_base: str | None = None,
    quiet: bool = False,
    on_progress: ProgressCallback | None = None,
) -> dict:
    t0 = time.perf_counter()
    stages: list[str] = []
    if not os.path.exists(midi_path):
        alt = MIDI_DIR / Path(midi_path).name
        if alt.exists():
            midi_path = str(alt)
        else:
            raise FileNotFoundError(f"MIDI not found: {midi_path}")

    requested = mode
    sf2_path = find_soundfont(soundfont)
    effective, mode_note = resolve_mode(requested, sf2_path)
    fallback_reason = mode_note if effective != requested else None

    stem = project_name or Path(midi_path).stem
    fname = filename_stem or stem
    out_root = Path(output_root) if output_root else OUT_DIR

    if flat_legacy and legacy_out_base:
        paths = audio_output_paths(
            out_root, stem, fname, flat_legacy=True, legacy_out_base=legacy_out_base
        )
    else:
        paths = audio_output_paths(out_root, stem, fname)

    result: dict = {
        "midi_file": os.path.abspath(midi_path),
        "project": stem,
        "mode_requested": requested,
        "mode_effective": effective,
        "fallback_reason": fallback_reason,
        "output_dir": paths["output_dir"],
        "wav": None,
        "ogg": None,
    }

    if not quiet:
        print(f"MIDI:  {midi_path}")
        print(f"Mode:  {effective} — {mode_note}")
        print(f"SF2:   {sf2_path or '(none)'}")

    if effective == "sf2":
        _emit_progress(on_progress, stages, "rendering_sf2", 0.2)
        sf2_out = render_full_sf2(
            midi_path, sf2_path, paths["wav"], paths["ogg"], quiet=quiet
        )
        if sf2_out.get("ok"):
            result["wav"] = sf2_out.get("wav")
            result["ogg"] = sf2_out.get("ogg")
            if sf2_out.get("ogg_skipped_reason"):
                result["ogg_skipped_reason"] = sf2_out["ogg_skipped_reason"]
            result["render_stages_completed"] = stages
            result["render_duration_sec"] = round(time.perf_counter() - t0, 3)
            sf2_data = parse_midi(midi_path)
            quality = assess_render_quality(
                mode_requested=requested,
                mode_effective=result["mode_effective"],
                wav_path=result.get("wav"),
                duration_sec=sf2_data["duration"],
            )
            if quality:
                result["quality_warnings"] = quality
            return result
        if not quiet:
            print("Falling back to pure chiptune...")
        effective = "chip"
        result["mode_effective"] = "chip"
        extra = sf2_out.get("reason", "sf2 render failed")
        result["fallback_reason"] = (
            (result.get("fallback_reason") or "") + f"; {extra}"
        ).strip("; ")

    _emit_progress(on_progress, stages, "parsing_midi", 0.1)
    data = parse_midi(midi_path)
    if not quiet:
        print(
            f"Parse: {data['bpm']:.0f} BPM, {data['duration']:.1f}s, "
            f"{len(data['drums'])} drum notes, "
            f"{sum(len(t['notes']) for t in data['melodic'])} melodic notes"
        )
    chip_out = render_chip_or_hybrid(
        data,
        effective,
        sf2_path,
        paths["wav"],
        paths["ogg"],
        loop_beats,
        quiet=quiet,
        on_progress=on_progress,
        stages=stages,
    )
    result["wav"] = chip_out.get("wav")
    result["ogg"] = chip_out.get("ogg")
    if chip_out.get("ogg_skipped_reason"):
        result["ogg_skipped_reason"] = chip_out["ogg_skipped_reason"]
    if result.get("fallback_reason"):
        caps = get_render_capabilities_impl()
        result["install_hints"] = caps.get("install_hints", [])
    quality = assess_render_quality(
        mode_requested=requested,
        mode_effective=result["mode_effective"],
        wav_path=result.get("wav"),
        duration_sec=data["duration"],
    )
    if quality:
        result["quality_warnings"] = quality
    result["render_stages_completed"] = stages
    result["render_duration_sec"] = round(time.perf_counter() - t0, 3)
    return result
