"""
Render MIDI → WAV/OGG with three modes (never hard-fails without SF2):

  chip    — pure chiptune (melodic + drums). Zero SF2 / FluidSynth needed.
  hybrid  — SF2 drums (tinysoundfont) + chiptune melodic; falls back to chip drums.
  sf2     — full SoundFont render (FluidSynth, all GM instruments); falls back to chip.
  auto    — hybrid if SF2+tinysoundfont, else sf2 if SF2+FluidSynth, else chip.

Usage:
  python scripts/render_track.py assets/midi/biome1_calm.mid
  python scripts/render_track.py assets/midi/biome1_calm.mid --mode chip
  python scripts/render_track.py assets/midi/biome1_calm.mid --mode hybrid --sf2 path.sf2
  python scripts/render_track.py assets/midi/biome1_calm.mid --mode sf2

Env: NOBU_MIDI_DIR, NOBU_OUTPUT_DIR, NOBU_SF2 (or FLUID_SYNTH_SF2).
"""
from __future__ import annotations

import argparse
import math
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import mido

SAMPLE_RATE = 44100
CHIP_SR = 22050

ROOT = Path(__file__).resolve().parent.parent
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

KICK, SNARE, HIHAT_CLOSED, HIHAT_OPEN, CRASH = 36, 38, 42, 46, 49


def midi_to_freq(note: int) -> float:
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


def adsr_gain(t: float, dur: float, p: dict) -> float:
    a, d, s, r = p["a"], p["d"], p["s"], p["r"]
    if t < a:
        return t / a if a > 0 else 1.0
    if t < a + d:
        return 1.0 - (1.0 - s) * ((t - a) / d) if d > 0 else s
    if t < dur - r:
        return s
    rt = t - (dur - r)
    return s * max(1.0 - rt / max(r, 0.001), 0.0) if rt < r and r > 0 else 0.0


# ── parse ──────────────────────────────────────────────────────────


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


# ── capability probes ──────────────────────────────────────────────


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


def has_fluidsynth() -> bool:
    return shutil.which("fluidsynth") is not None


# ── chip drums ─────────────────────────────────────────────────────


def _synth_kick(duration: float, volume: float, sr: int) -> np.ndarray:
    n = int(duration * sr)
    out = np.zeros(n, dtype=np.float32)
    vol = volume / 127.0
    p = ADSR["kick"]
    for i in range(n):
        t = i / sr
        env = adsr_gain(t, duration, p)
        if env <= 0.001:
            continue
        freq = max(100.0 - (65.0 * (t / max(duration, 0.001))), 30.0)
        body = math.sin(2.0 * math.pi * freq * t)
        click = 0.0
        if t < 0.002:
            click = math.sin(2.0 * math.pi * 1000.0 * t) * (1.0 - t / 0.002) * 0.3
        out[i] = math.tanh((body + click) * 2.0) * env * vol * 1.2
    return out


def _synth_snare(duration: float, volume: float, sr: int) -> np.ndarray:
    n = int(duration * sr)
    out = np.zeros(n, dtype=np.float32)
    vol = volume / 127.0
    p = ADSR["snare"]
    for i in range(n):
        t = i / sr
        env = adsr_gain(t, duration, p)
        if env <= 0.001:
            continue
        tone = math.sin(2.0 * math.pi * 180.0 * t) * 0.4
        ring = math.sin(2.0 * math.pi * 400.0 * t) * 0.15
        noise = random.random() * 2.0 - 1.0
        wav = tone + ring + noise * 0.7
        if t < 0.003:
            wav *= 1.3
        out[i] = wav * env * vol
    return out


def _synth_hihat(duration: float, volume: float, sr: int, open_hat: bool) -> np.ndarray:
    n = int(duration * sr)
    out = np.zeros(n, dtype=np.float32)
    vol = volume / 127.0
    p = ADSR["hihat_open" if open_hat else "hihat_closed"]
    gain = 0.8 if open_hat else 0.55
    for i in range(n):
        t = i / sr
        env = adsr_gain(t, duration, p)
        if env <= 0.001:
            continue
        out[i] = (random.random() * 2.0 - 1.0) * env * vol * gain
    return out


def _synth_crash(duration: float, volume: float, sr: int) -> np.ndarray:
    n = int(duration * sr)
    out = np.zeros(n, dtype=np.float32)
    vol = volume / 127.0
    p = ADSR["crash"]
    for i in range(n):
        t = i / sr
        env = adsr_gain(t, duration, p)
        if env <= 0.001:
            continue
        out[i] = (random.random() * 2.0 - 1.0) * env * vol * 0.5
    return out


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
    """Render drums via tinysoundfont. Returns mono float32 at SAMPLE_RATE."""
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


# ── melodic chiptune ───────────────────────────────────────────────


def render_melodic(mel_tracks: list) -> np.ndarray:
    if not mel_tracks:
        return np.zeros(1, dtype=np.float32)

    total_dur = 0.0
    for t in mel_tracks:
        for n in t["notes"]:
            total_dur = max(total_dur, n["start_sec"] + n["dur_sec"])
    total_samples = int(total_dur * CHIP_SR) + CHIP_SR
    mixed = np.zeros(total_samples, dtype=np.float32)

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

        for n in t["notes"]:
            start = int(n["start_sec"] * CHIP_SR)
            dur = max(n["dur_sec"], 0.005)
            freq = midi_to_freq(n["pitch"])
            vel = n["vel"]
            n_s = int(dur * CHIP_SR)
            adsr_p = ADSR[ak]
            buf = np.zeros(n_s, dtype=np.float32)

            for i in range(n_s):
                t_i = i / CHIP_SR
                env = adsr_gain(t_i, dur, adsr_p)
                if env <= 0.001:
                    continue
                phase = (freq * t_i) % 1.0
                if wt == "square":
                    wav = 1.0 if phase < duty else -1.0
                elif wt == "triangle":
                    if phase < 0.25:
                        wav = 4.0 * phase
                    elif phase < 0.75:
                        wav = 2.0 - 4.0 * phase
                    else:
                        wav = 4.0 * phase - 4.0
                else:
                    wav = 1.0 if phase < 0.5 else -1.0
                buf[i] = wav * env * (vel / 127.0) * 0.22

            end = start + n_s
            if end > total_samples:
                n_s = total_samples - start
            if n_s > 0:
                mixed[start : start + n_s] += buf[:n_s]

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


def write_output(
    mixed: np.ndarray, out_base: str, loop_beats: float = 0, bpm: float = 152
) -> None:
    import soundfile as sf

    if loop_beats > 0:
        loop_samples = int(loop_beats * (60.0 / bpm) * SAMPLE_RATE)
        if loop_samples < len(mixed):
            mixed = mixed[:loop_samples].copy()

    os.makedirs(os.path.dirname(out_base) or ".", exist_ok=True)
    wav_path = out_base + ".wav"
    sf.write(wav_path, mixed, SAMPLE_RATE, subtype="PCM_16")
    print(f"WAV: {wav_path} ({os.path.getsize(wav_path) / 1024:.0f} KB)")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("  (ffmpeg not found — WAV only; OGG skipped)")
        return

    ogg_path = out_base + ".ogg"
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
            timeout=60,
        )
        print(f"OGG: {ogg_path} ({os.path.getsize(ogg_path) / 1024:.0f} KB)")
    except Exception as e:
        print(f"  (OGG skip: {e})")


# ── full SF2 via FluidSynth ────────────────────────────────────────


def render_full_sf2(midi_path: str, sf2_path: str, out_base: str) -> bool:
    """Render entire MIDI through FluidSynth (all instruments from SF2)."""
    os.makedirs(os.path.dirname(out_base) or ".", exist_ok=True)
    ogg_path = out_base + ".ogg"
    wav_path = out_base + ".wav"

    # Prefer OGG; fall back to WAV then convert
    cmd_ogg = [
        "fluidsynth",
        "-ni",
        sf2_path,
        midi_path,
        "-F",
        ogg_path,
        "-O",
        "s3m",
        "-r",
        str(SAMPLE_RATE),
        "-R",
        "0",
        "-g",
        "1.5",
    ]
    try:
        subprocess.run(cmd_ogg, check=True, capture_output=True, text=True, timeout=90)
        print(f"OGG: {ogg_path} ({os.path.getsize(ogg_path) / 1024:.0f} KB) [FluidSynth]")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    cmd_wav = [
        "fluidsynth",
        "-ni",
        sf2_path,
        midi_path,
        "-F",
        wav_path,
        "-r",
        str(SAMPLE_RATE),
        "-R",
        "0",
        "-g",
        "1.5",
    ]
    try:
        subprocess.run(cmd_wav, check=True, capture_output=True, text=True, timeout=90)
        print(f"WAV: {wav_path} ({os.path.getsize(wav_path) / 1024:.0f} KB) [FluidSynth]")
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
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
                timeout=60,
            )
            print(f"OGG: {ogg_path}")
        return True
    except Exception as e:
        print(f"  FluidSynth failed: {e}")
        return False


# ── mode resolution ────────────────────────────────────────────────


def resolve_mode(requested: str, sf2_path: str) -> tuple[str, str]:
    """
    Returns (effective_mode, note).
    Never raises — always returns a renderable mode.
    """
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
        # hybrid-ish degradation: if we have SF2+tsf, at least hybrid drums
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

    # auto
    if sf2_ok and tsf_ok:
        return "hybrid", f"auto → hybrid ({sf2_path})"
    if sf2_ok and fs_ok:
        return "sf2", f"auto → full SF2 ({sf2_path})"
    return "chip", "auto → pure chiptune (no SF2 / FluidSynth / tinysoundfont)"


def render_chip_or_hybrid(
    data: dict,
    mode: str,
    sf2_path: str,
    out_base: str,
    loop_beats: float,
) -> None:
    if mode == "hybrid":
        print("Drums via SF2...", end=" ", flush=True)
        try:
            drums = render_drums_sf2(data["drums"], sf2_path)
        except Exception as e:
            print(f"failed ({e}) — chip drums")
            drums = render_drums_chip(data["drums"])
        else:
            print(f"peak={float(np.max(np.abs(drums))):.3f}")
    else:
        print("Drums via chiptune...", end=" ", flush=True)
        drums = render_drums_chip(data["drums"])
        print(f"peak={float(np.max(np.abs(drums))):.3f}")

    print("Melodic via chiptune...", end=" ", flush=True)
    melodic = render_melodic(data["melodic"])
    print(f"peak={float(np.max(np.abs(melodic))):.3f}")

    print("Mixing...", end=" ", flush=True)
    mixed = mix_down(drums, melodic)
    print(f"peak={float(np.max(np.abs(mixed))):.3f}")

    write_output(mixed, out_base, loop_beats, data["bpm"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render MIDI → WAV/OGG (chip / hybrid / full SF2 — never hard-fails)"
    )
    parser.add_argument("input", help="Path to .mid file")
    parser.add_argument(
        "--mode",
        choices=("auto", "chip", "hybrid", "sf2"),
        default="auto",
        help="chip=pure chiptune; hybrid=SF2 drums+chip melodic; "
        "sf2=full SoundFont; auto=best available (default)",
    )
    parser.add_argument(
        "--sf2",
        default=None,
        help="SoundFont path (default: assets/soundfonts/default.sf2 or NOBU_SF2)",
    )
    parser.add_argument("--out", default=None, help="Output path without extension")
    parser.add_argument(
        "--loop-beats",
        type=float,
        default=0,
        help="Trim to exact loop length in beats",
    )
    args = parser.parse_args()

    midi_path = args.input
    if not os.path.exists(midi_path):
        alt = MIDI_DIR / Path(midi_path).name
        if alt.exists():
            midi_path = str(alt)
        else:
            print(f"File not found: {midi_path}")
            sys.exit(1)

    sf2_path = find_soundfont(args.sf2)
    mode, note = resolve_mode(args.mode, sf2_path)

    stem = os.path.splitext(os.path.basename(midi_path))[0]
    out_base = args.out if args.out else str(OUT_DIR / stem)
    os.makedirs(os.path.dirname(out_base) or ".", exist_ok=True)

    print(f"MIDI:  {midi_path}")
    print(f"Mode:  {mode} — {note}")
    if sf2_path:
        print(f"SF2:   {sf2_path}")
    else:
        print("SF2:   (none)")

    if mode == "sf2":
        ok = render_full_sf2(midi_path, sf2_path, out_base)
        if ok:
            print("Done.")
            return
        print("Falling back to pure chiptune...")
        mode = "chip"

    data = parse_midi(midi_path)
    print(
        f"Parse: {data['bpm']:.0f} BPM, {data['duration']:.1f}s, "
        f"{len(data['drums'])} drum notes, "
        f"{sum(len(t['notes']) for t in data['melodic'])} melodic notes"
    )
    render_chip_or_hybrid(data, mode, sf2_path, out_base, args.loop_beats)
    print("Done.")


if __name__ == "__main__":
    main()
