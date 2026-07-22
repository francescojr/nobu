"""
Batch-render .mid -> .ogg/.wav. Three modes (never hard-fails without SF2):

  chip    — pure chiptune (built-in synth). No SF2 / FluidSynth needed.
  sf2     — full SoundFont via FluidSynth (all GM programs). Falls back to chip.
  hybrid  — SF2 drums + chiptune melodic via render_track.py. Falls back to chip.
  auto    — sf2 if FluidSynth+SF2, else chip (batch default).

For single-file hybrid control, prefer: python scripts/render_track.py --mode ...

Usage:
  python scripts/render_midi.py
  python scripts/render_midi.py --mode chip
  python scripts/render_midi.py --mode sf2 --soundfont assets/soundfonts/default.sf2
  python scripts/render_midi.py --mode hybrid

Looks for .mid in assets/midi/ -> writes to output/audio/.

Env: NOBU_MIDI_DIR, NOBU_OUTPUT_DIR, NOBU_SF2 (or FLUID_SYNTH_SF2).
"""

import os
import sys
import glob
import struct
import wave
import math
import random
from pathlib import Path

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

ROOT = Path(__file__).resolve().parent.parent
MIDI_DIR = Path(os.environ.get("NOBU_MIDI_DIR", str(ROOT / "assets" / "midi")))
OUT_DIR = Path(os.environ.get("NOBU_OUTPUT_DIR", str(ROOT / "output" / "audio")))

SAMPLE_RATE = 22050  # Half CD quality — authentic for chiptune and lighter on memory

# --- ADSR envelopes per instrument type -----------------------------
# Times in seconds. Sustain is a fraction of peak amplitude.
ADSR = {
    "pulse_lead":    {"a": 0.008, "d": 0.04, "s": 0.70, "r": 0.04},
    "pulse_harmony": {"a": 0.015, "d": 0.06, "s": 0.55, "r": 0.08},
    "triangle_bass": {"a": 0.015, "d": 0.08, "s": 0.75, "r": 0.10},
    "kick":          {"a": 0.001, "d": 0.12, "s": 0.0,  "r": 0.02},
    "snare":         {"a": 0.001, "d": 0.08, "s": 0.0,  "r": 0.03},
    "hihat_closed":  {"a": 0.001, "d": 0.03, "s": 0.0,  "r": 0.01},
    "hihat_open":    {"a": 0.001, "d": 0.15, "s": 0.0,  "r": 0.05},
    "crash":         {"a": 0.001, "d": 0.40, "s": 0.0,  "r": 0.10},
}

# --- Drum pitch maps for synthesis ----------------------------------
KICK = 36
SNARE = 38
HIHAT_CLOSED = 42
HIHAT_OPEN = 46
CRASH = 49


def adsr_gain(t: float, dur: float, params: dict) -> float:
    """ADSR envelope at time t within a note of total duration dur."""
    a, d, s, r = params["a"], params["d"], params["s"], params["r"]
    if t < a:
        return t / a  # attack: 0 -> 1
    if t < a + d:
        return 1.0 - (1.0 - s) * ((t - a) / d)  # decay: 1 -> s
    if t < dur - r:
        return s  # sustain
    release_t = t - (dur - r)
    if release_t < r and r > 0:
        return s * (1.0 - release_t / r)
    if release_t >= r:
        return 0.0
    return 0.0


# =======================================================================
# Waveform generators
# =======================================================================

def gen_square(freq: float, t: float, duty: float = 0.5) -> float:
    """Square wave with configurable duty cycle."""
    phase = (freq * t) % 1.0
    return 1.0 if phase < duty else -1.0


def gen_triangle(freq: float, t: float) -> float:
    """Triangle wave."""
    phase = (freq * t) % 1.0
    if phase < 0.25:
        return 4.0 * phase
    elif phase < 0.75:
        return 2.0 - 4.0 * phase
    else:
        return 4.0 * phase - 4.0


def gen_sawtooth(freq: float, t: float) -> float:
    """Sawtooth wave (for bass variation)."""
    return 2.0 * ((freq * t) % 1.0) - 1.0


def gen_noise(seed: int) -> float:
    """Simple noise -- deterministic from seed for reproducibility."""
    random.seed(seed)
    return random.random() * 2.0 - 1.0


def midi_to_freq(midi_note: int) -> float:
    """MIDI note number -> Hz (A4 = 440)."""
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


# =======================================================================
# Note synthesis
# =======================================================================

def synth_note_melodic(freq: float, duration: float, volume: float,
                       wave_type: str, adsr_name: str, duty: float = 0.5):
    """Synthesize a single melodic note. Returns numpy array or list."""
    n_samples = int(duration * SAMPLE_RATE)
    adsr_p = ADSR[adsr_name]

    if HAS_NUMPY:
        t = np.arange(n_samples, dtype=np.float32) / SAMPLE_RATE
        # ADSR envelope as numpy array
        env = np.zeros(n_samples, dtype=np.float32)
        a, d, s, r = adsr_p["a"], adsr_p["d"], adsr_p["s"], adsr_p["r"]
        # Attack
        mask_a = t < a
        env[mask_a] = t[mask_a] / a
        # Decay
        mask_d = (t >= a) & (t < a + d)
        env[mask_d] = 1.0 - (1.0 - s) * ((t[mask_d] - a) / d)
        # Sustain
        mask_s = (t >= a + d) & (t < duration - r)
        env[mask_s] = s
        # Release
        mask_r = (t >= duration - r)
        release_t = t[mask_r] - (duration - r)
        env[mask_r] = s * (1.0 - np.minimum(release_t / max(r, 0.001), 1.0))

        # Waveform
        phase = (freq * t) % 1.0
        if wave_type == "square":
            wav = np.where(phase < duty, 1.0, -1.0).astype(np.float32)
        elif wave_type == "triangle":
            wav = np.where(phase < 0.25, 4.0 * phase,
                   np.where(phase < 0.75, 2.0 - 4.0 * phase,
                   4.0 * phase - 4.0)).astype(np.float32)
        elif wave_type == "sawtooth":
            wav = (2.0 * phase - 1.0).astype(np.float32)
        else:
            wav = np.where(phase < 0.5, 1.0, -1.0).astype(np.float32)

        return wav * env * (volume / 127.0) * 0.2  # lowered so drums dominate
    else:
        # Pure Python fallback
        samples = [0.0] * n_samples
        for i in range(n_samples):
            t_i = float(i) / SAMPLE_RATE
            env = adsr_gain(t_i, duration, adsr_p)
            if env <= 0.001:
                continue
            if wave_type == "square":
                wav = gen_square(freq, t_i, duty)
            elif wave_type == "triangle":
                wav = gen_triangle(freq, t_i)
            elif wave_type == "sawtooth":
                wav = gen_sawtooth(freq, t_i)
            else:
                wav = gen_square(freq, t_i, 0.5)
            samples[i] = wav * env * (volume / 127.0) * 0.3
        return samples


def synth_kick(duration: float, volume: float) -> list[float]:
    """Synthesize kick drum: deep pitch-dropping sine + attack click + body."""
    n_samples = int(duration * SAMPLE_RATE)
    adsr_p = ADSR["kick"]
    samples = [0.0] * n_samples
    vol = volume / 127.0

    for i in range(n_samples):
        t = i / SAMPLE_RATE
        env = adsr_gain(t, duration, adsr_p)
        if env <= 0.001:
            continue
        # Pitch drops from 100 Hz to 35 Hz — deeper, more sub-bass
        freq = 100.0 - (65.0 * (t / max(duration, 0.001)))
        freq = max(freq, 30.0)
        # Body: sine wave
        body = math.sin(2.0 * math.pi * freq * t)
        # Click transient: short 1kHz burst in first 2ms for attack definition
        click = 0.0
        if t < 0.002:
            click = math.sin(2.0 * math.pi * 1000.0 * t) * (1.0 - t / 0.002) * 0.3
        # Subtle harmonics via soft clipping for punch
        wav = body + click
        wav = math.tanh(wav * 2.0)
        samples[i] = wav * env * vol * 1.2  # boosted for DnB

    return samples


def synth_snare(duration: float, volume: float) -> list[float]:
    """Synthesize snare: dual-tone body + bandpassed noise for snare-wire sizzle."""
    n_samples = int(duration * SAMPLE_RATE)
    adsr_p = ADSR["snare"]
    samples = [0.0] * n_samples
    vol = volume / 127.0
    # For bandpass: running averages at different windows
    noise_ring = [0.0] * 4

    for i in range(n_samples):
        t = i / SAMPLE_RATE
        env = adsr_gain(t, duration, adsr_p)
        if env <= 0.001:
            continue
        # Dual tone body: 180Hz fundamental + 400Hz ring
        tone = math.sin(2.0 * math.pi * 180.0 * t) * 0.4
        ring = math.sin(2.0 * math.pi * 400.0 * t) * 0.15
        # Bandpassed noise for snare-wire texture (~1-6kHz)
        raw = random.random() * 2.0 - 1.0
        # Simple FIR bandpass: recent samples difference
        noise_ring = noise_ring[1:] + [raw]
        bp_noise = (noise_ring[0] - noise_ring[3]) * 0.7  # crude 1-6kHz bandpass
        wav = tone + ring + bp_noise
        # Fast attack compression
        if t < 0.003:
            wav *= 1.3
        samples[i] = wav * env * vol * 1.0  # boosted for DnB

    return samples


def synth_hihat(duration: float, volume: float, open_hat: bool = False) -> list[float]:
    """Synthesize hi-hat: bandpassed noise for metallic sizzle."""
    n_samples = int(duration * SAMPLE_RATE)
    adsr_name = "hihat_open" if open_hat else "hihat_closed"
    adsr_p = ADSR[adsr_name]
    samples = [0.0] * n_samples
    vol = volume / 127.0
    ring_buf = [0.0] * 6  # Ring buffer for metallic resonance

    for i in range(n_samples):
        t = i / SAMPLE_RATE
        env = adsr_gain(t, duration, adsr_p)
        if env <= 0.001:
            continue
        raw = random.random() * 2.0 - 1.0
        # Metallic resonance: feed ring buffer at ~8kHz equivalent
        ring_buf = ring_buf[1:] + [raw]
        # Comb-like metallic filter using ring buffer
        metallic = raw * 0.6 + ring_buf[0] * 0.25 - ring_buf[3] * 0.2 + ring_buf[5] * 0.1
        # High-pass: remove low end for crispness
        hp = metallic
        if i > 1:
            hp = metallic - samples[max(0, i - 2)] * 0.25
        wav = hp
        samples[i] = wav * env * vol * (0.8 if open_hat else 0.55)  # boosted for DnB

    return samples


def synth_crash(duration: float, volume: float) -> list[float]:
    """Synthesize crash cymbal: noise with long decay."""
    n_samples = int(duration * SAMPLE_RATE)
    adsr_p = ADSR["crash"]
    samples = [0.0] * n_samples

    for i in range(n_samples):
        t = i / SAMPLE_RATE
        env = adsr_gain(t, duration, adsr_p)
        if env <= 0.001:
            continue
        noise = random.random() * 2.0 - 1.0
        # Slight coloration
        if i > 1:
            noise = (noise + samples[i - 2] * 0.15) * 0.87
        samples[i] = noise * env * (volume / 127.0) * 0.5

    return samples


def synth_note_drum(pitch: int, duration: float, volume: float) -> list[float]:
    """Route drum note to correct synthesizer based on GM drum map."""
    if pitch == KICK:
        return synth_kick(duration, volume)
    elif pitch == SNARE:
        return synth_snare(duration, volume)
    elif pitch == HIHAT_CLOSED:
        return synth_hihat(duration, volume, open_hat=False)
    elif pitch == HIHAT_OPEN:
        return synth_hihat(duration, volume, open_hat=True)
    elif pitch == CRASH:
        return synth_crash(duration, volume)
    else:
        # Generic percussion: short noise burst
        return synth_hihat(duration * 0.5, volume, open_hat=False)


# =======================================================================
# MIDI parsing
# =======================================================================

def parse_midi_track(track, ticks_per_beat: int, tempo: int) -> tuple[list, int, int]:
    """
    Parse one MIDI track. Returns:
      - list of {pitch, start_sec, duration_sec, velocity, channel}
      - program number
      - channel (deduced from first note or program_change)
    """
    notes = []
    program = 0
    channel = 0
    abs_ticks = 0
    pending_notes: dict[tuple[int, int], dict] = {}  # (channel, pitch) -> note info

    for msg in track:
        abs_ticks += msg.time

        if msg.type == "program_change":
            program = msg.program
            channel = msg.channel

        elif msg.type == "note_on" and msg.velocity > 0:
            key = (msg.channel, msg.note)
            pending_notes[key] = {
                "pitch": msg.note,
                "velocity": msg.velocity,
                "start_tick": abs_ticks,
                "channel": msg.channel,
            }

        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            key = (msg.channel, msg.note)
            if key in pending_notes:
                n = pending_notes.pop(key)
                n["duration_ticks"] = abs_ticks - n["start_tick"]
                notes.append(n)

    # Convert ticks to seconds
    sec_per_tick = (tempo / 1_000_000.0) / ticks_per_beat
    for n in notes:
        n["start_sec"] = n["start_tick"] * sec_per_tick
        n["duration_sec"] = n["duration_ticks"] * sec_per_tick
        # Remove temp fields
        del n["start_tick"]
        del n["duration_ticks"]

    return notes, program, channel


def read_midi(path: str) -> dict:
    """Read a MIDI file and return structured note data."""
    try:
        import mido
    except ImportError:
        sys.exit(
            "mido not installed. Run: pip install mido\n"
            "Or install FluidSynth for soundfont-based rendering."
        )

    mid = mido.MidiFile(path)
    ticks_per_beat = mid.ticks_per_beat

    # Find tempo from first track
    tempo = 500000  # default 120 BPM
    for track in mid.tracks:
        abs_t = 0
        for msg in track:
            abs_t += msg.time
            if msg.type == "set_tempo":
                tempo = msg.tempo
                break

    tracks = []
    for track in mid.tracks:
        notes, program, channel = parse_midi_track(track, ticks_per_beat, tempo)
        if notes:  # skip empty tracks
            tracks.append({
                "notes": notes,
                "program": program,
                "channel": channel,
            })

    # Total duration: latest note end across all tracks
    total_dur = 0.0
    for t in tracks:
        for n in t["notes"]:
            end = n["start_sec"] + n["duration_sec"]
            if end > total_dur:
                total_dur = end

    return {
        "tracks": tracks,
        "duration": total_dur,
        "bpm": 60_000_000 / tempo,
        "sample_rate": SAMPLE_RATE,
    }


# =======================================================================
# Rendering
# =======================================================================

def render_track(track: dict, total_samples: int):
    """Render one track to sample buffer (numpy array)."""
    if HAS_NUMPY:
        buf = np.zeros(total_samples, dtype=np.float32)
    else:
        buf = [0.0] * total_samples
    is_drums = track["channel"] == 9
    program = track["program"]

    # Determine waveform type from program
    if is_drums:
        wave_type = "drums"
    elif program == 80:  # pulse_lead
        wave_type = "square"
        adsr_key = "pulse_lead"
        duty = 0.375
    elif program == 81:  # pulse_harmony
        wave_type = "square"
        adsr_key = "pulse_harmony"
        duty = 0.5
    elif program == 38:  # triangle_bass
        wave_type = "triangle"
        adsr_key = "triangle_bass"
        duty = 0.5
    else:
        wave_type = "square"
        adsr_key = "pulse_lead"
        duty = 0.5

    for n in track["notes"]:
        start = int(n["start_sec"] * SAMPLE_RATE)
        dur = max(n["duration_sec"], 0.005)

        if is_drums:
            samples = synth_note_drum(n["pitch"], dur, n["velocity"])
        else:
            freq = midi_to_freq(n["pitch"])
            samples = synth_note_melodic(freq, dur, n["velocity"], wave_type, adsr_key, duty)

        # Mix into track buffer
        n_s = len(samples)
        end = start + n_s
        if end > total_samples:
            n_s = total_samples - start
        if n_s > 0:
            if HAS_NUMPY:
                buf[start:start + n_s] += np.asarray(samples[:n_s], dtype=np.float32)
            else:
                for i in range(n_s):
                    buf[start + i] += samples[i]

    return buf


def mix_tracks(track_buffers, total_samples: int):
    """Mix multiple track buffers with normalization."""
    if HAS_NUMPY:
        mixed = np.zeros(total_samples, dtype=np.float32)
        for buf in track_buffers:
            mixed += np.asarray(buf, dtype=np.float32)

        peak = float(np.max(np.abs(mixed)))
        if peak > 0.95:
            mixed *= (0.90 / peak)

        # Soft clipping via tanh
        mixed = np.tanh(mixed * 1.2)
        return mixed
    else:
        mixed = [0.0] * total_samples
        for buf in track_buffers:
            for i in range(total_samples):
                mixed[i] += buf[i] if isinstance(buf, list) else float(buf[i])

        peak = max(abs(s) for s in mixed) if mixed else 1.0
        if peak > 0.95:
            gain = 0.90 / peak
            for i in range(total_samples):
                mixed[i] *= gain

        for i in range(total_samples):
            mixed[i] = math.tanh(mixed[i] * 1.2)
        return mixed


def write_wav(path: str, samples) -> str:
    """Write 16-bit PCM WAV file. Returns the path written."""
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if HAS_NUMPY:
        arr = np.asarray(samples, dtype=np.float32)
        peak = float(np.max(np.abs(arr)))
        scale = 32767.0 / max(peak, 0.0001)
        arr = np.clip(arr * scale, -32767, 32767).astype(np.int16)
        with wave.open(path, "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(arr.tobytes())
        return path
    else:
        peak = max(abs(s) for s in samples) if len(samples) > 0 else 1.0
        scale = 32767.0 / max(peak, 0.0001)
        with wave.open(path, "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            for s in samples:
                clamped = max(-1.0, min(1.0, s))
                w.writeframes(struct.pack("<h", int(clamped * scale)))
        return path


def write_ogg(path: str, samples) -> str:
    """Write OGG Vorbis file. Falls back to WAV on any error."""
    try:
        import soundfile as sf
        os.makedirs(os.path.dirname(path), exist_ok=True)
        arr = np.asarray(samples, dtype=np.float32)
        sf.write(path, arr, SAMPLE_RATE, format="OGG", subtype="VORBIS")
        return path
    except Exception:
        wav_path = path.replace(".ogg", ".wav")
        return write_wav(wav_path, samples)


def render_chip_synth(midi_path: Path) -> str | None:
    """Pure Python chiptune rendering path. Returns output path or None."""
    out_path = OUT_DIR / f"{midi_path.stem}.ogg"

    print(f"  Synthesizing {midi_path.name}...")
    midi_data = read_midi(str(midi_path))

    total_samples = int(midi_data["duration"] * SAMPLE_RATE) + SAMPLE_RATE  # 1s padding

    # Render each track
    track_buffers = []
    for t in midi_data["tracks"]:
        buf = render_track(t, total_samples)
        # Boost drum tracks (channel 9) for DnB — drums must dominate
        if t.get("channel") == 9 and HAS_NUMPY:
            buf = np.asarray(buf, dtype=np.float32) * 2.5
        track_buffers.append(buf)

    # Mix
    mixed = mix_tracks(track_buffers, total_samples)
    result_path = write_ogg(str(out_path), mixed)

    size_kb = os.path.getsize(result_path) / 1024
    print(f"    -> {os.path.basename(result_path)} ({size_kb:.0f} KB, {midi_data['duration']:.1f}s)")
    return result_path


# =======================================================================
# FluidSynth path (optional, auto-detected)
# =======================================================================

def find_soundfont(custom: str | None = None) -> str:
    """Find a usable soundfont, preferring the custom path if given."""
    if custom and os.path.exists(custom):
        return custom

    for env_key in ("NOBU_SF2", "FLUID_SYNTH_SF2"):
        env_sf = os.environ.get(env_key)
        if env_sf and os.path.exists(env_sf):
            return env_sf

    local = ROOT / "assets" / "soundfonts" / "default.sf2"
    if local.exists():
        return str(local)

    return ""


def has_fluidsynth() -> bool:
    """Check if FluidSynth CLI is available."""
    import shutil
    return shutil.which("fluidsynth") is not None


def render_fluidsynth(midi_path: Path, soundfont: str) -> bool:
    """Render via FluidSynth CLI. Returns True on success."""
    import subprocess
    out_path = OUT_DIR / f"{midi_path.stem}.ogg"

    cmd = [
        "fluidsynth", "-ni", soundfont, str(midi_path),
        "-F", str(out_path), "-O", "s3m",
        "-r", str(SAMPLE_RATE), "-R", "0", "-g", "1.5",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
        size_kb = os.path.getsize(out_path) / 1024
        print(f"    -> {out_path.name} ({size_kb:.0f} KB) [FluidSynth]")
        return True
    except FileNotFoundError:
        return False
    except subprocess.CalledProcessError as e:
        print(f"    X FluidSynth error: {e.stderr[:150]}")
        return False


# =======================================================================
# Main
# =======================================================================

def render_via_track_script(midi_path: Path, mode: str, soundfont: str) -> bool:
    """Delegate hybrid/sf2/chip single-file render to render_track.py."""
    import subprocess

    script = ROOT / "scripts" / "render_track.py"
    cmd = [sys.executable, str(script), str(midi_path), "--mode", mode]
    if soundfont:
        cmd.extend(["--sf2", soundfont])
    try:
        subprocess.run(cmd, check=True, cwd=str(ROOT))
        return True
    except subprocess.CalledProcessError as e:
        print(f"    X render_track failed ({e.returncode})")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Batch render .mid -> audio (chip / hybrid / full SF2)"
    )
    parser.add_argument("--soundfont", help="Path to .sf2 file")
    parser.add_argument(
        "--mode",
        choices=("auto", "chip", "hybrid", "sf2"),
        default="auto",
        help="chip | hybrid | sf2 | auto (default: sf2 if available else chip)",
    )
    parser.add_argument(
        "--force-chip",
        action="store_true",
        help="Deprecated alias for --mode chip",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help="Single .mid file (default: all .mid in assets/midi/)",
    )
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    if args.input:
        midi_path = Path(args.input)
        if not midi_path.is_absolute():
            midi_path = Path.cwd() / midi_path
        if not midi_path.exists():
            alt = MIDI_DIR / midi_path.name
            if alt.exists():
                midi_path = alt
            else:
                print(f"File not found: {midi_path}")
                return
        midi_files = [str(midi_path)]
    else:
        midi_files = sorted(glob.glob(str(MIDI_DIR / "*.mid")))
        if not midi_files:
            print(f"No .mid files found in {MIDI_DIR}")
            print("Run: python examples/demo_biome_ost.py  (or use the nobu MCP)")
            return

    mode = "chip" if args.force_chip else args.mode
    soundfont = find_soundfont(args.soundfont)

    if mode == "hybrid":
        print(f"Rendering {len(midi_files)} file(s) via render_track --mode hybrid")
        ok = sum(
            1
            for path in midi_files
            if render_via_track_script(Path(path), "hybrid", soundfont)
        )
    elif mode == "sf2":
        if soundfont and has_fluidsynth():
            print(f"Rendering {len(midi_files)} file(s) with FluidSynth (full SF2)")
            print(f"Soundfont: {soundfont}")
            ok = 0
            for path in midi_files:
                try:
                    if render_fluidsynth(Path(path), soundfont):
                        ok += 1
                    else:
                        print(f"  fallback chip: {Path(path).name}")
                        if render_chip_synth(Path(path)):
                            ok += 1
                except Exception as e:
                    print(f"  X {Path(path).name}: {e}")
        else:
            print(
                "SF2 mode unavailable "
                f"(sf2={'yes' if soundfont else 'no'}, "
                f"fluidsynth={'yes' if has_fluidsynth() else 'no'}) "
                "— falling back to pure chiptune"
            )
            ok = 0
            for path in midi_files:
                try:
                    if render_chip_synth(Path(path)):
                        ok += 1
                except Exception as e:
                    print(f"  X {Path(path).name}: {e}")
    elif mode == "chip":
        print(f"Rendering {len(midi_files)} file(s) with pure chiptune synth")
        print(f"  Sample rate: {SAMPLE_RATE} Hz, mono")
        ok = 0
        for path in midi_files:
            try:
                if render_chip_synth(Path(path)):
                    ok += 1
            except Exception as e:
                print(f"  X {Path(path).name}: {e}")
    else:
        # auto: prefer full SF2, else chip (hybrid is opt-in for batch)
        if soundfont and has_fluidsynth():
            print(f"Rendering {len(midi_files)} file(s) with FluidSynth [auto]")
            print(f"Soundfont: {soundfont}")
            ok = 0
            for path in midi_files:
                try:
                    if render_fluidsynth(Path(path), soundfont):
                        ok += 1
                    elif render_chip_synth(Path(path)):
                        ok += 1
                except Exception as e:
                    print(f"  X {Path(path).name}: {e}")
        else:
            print(f"Rendering {len(midi_files)} file(s) with pure chiptune synth [auto]")
            if args.soundfont and not soundfont:
                print(f"  (soundfont not found at '{args.soundfont}')")
            print(f"  Sample rate: {SAMPLE_RATE} Hz, mono")
            ok = 0
            for path in midi_files:
                try:
                    if render_chip_synth(Path(path)):
                        ok += 1
                except Exception as e:
                    print(f"  X {Path(path).name}: {e}")

    print(f"\nDone: {ok}/{len(midi_files)} rendered -> {OUT_DIR}")

    if mode in ("auto", "chip") and not (soundfont and has_fluidsynth()):
        print("Tip: for full SF2 or hybrid drums, add assets/soundfonts/default.sf2")
        print("  https://www.williamkage.com/snes_soundfonts/")
        print("  Then: python scripts/render_midi.py --mode sf2")
        print("     or: python scripts/render_track.py FILE.mid --mode hybrid")


if __name__ == "__main__":
    main()

