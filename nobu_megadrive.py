"""
MIDI → Mega Drive VGM export for nobu (SGDK-friendly).

Builtin FM patches + optional BYO JSON patches / PCM WAVs (SF2-style:
nothing third-party is shipped). Drums default to PSG noise; local PCM
unlocks DAC hits when present.

Env: NOBU_MIDI_DIR, NOBU_OUTPUT_DIR (same as nobu_render).
"""
from __future__ import annotations

import json
import os
import struct
import wave
from copy import deepcopy
from pathlib import Path
from typing import Any

import mido
import numpy as np

ROOT = Path(__file__).resolve().parent
MIDI_DIR = Path(os.environ.get("NOBU_MIDI_DIR", str(ROOT / "assets" / "midi")))
OUT_DIR = Path(os.environ.get("NOBU_OUTPUT_DIR", str(ROOT / "output" / "audio")))
MD_DIR = ROOT / "assets" / "megadrive"
PATCHES_DIR = MD_DIR / "patches"
PCM_DIR = MD_DIR / "pcm"

YM2612_CLOCK = 7_670_453
PSG_CLOCK = 3_579_545
VGM_SAMPLE_RATE = 44100
PCM_RATE = 13300
VGM_HEADER_SIZE = 0x40
VGM_VERSION = 0x00000150

# GM drum pitches (match nobu_mcp.GM_DRUM_MAP)
DRUM_PITCH_TO_HIT = {
    35: "kick",
    36: "kick",
    37: "rimshot",
    38: "snare",
    39: "clap",
    40: "snare",
    41: "low_tom",
    42: "closed_hihat",
    44: "closed_hihat",
    46: "open_hihat",
    47: "mid_tom",
    49: "crash",
    50: "high_tom",
    51: "ride",
}

PCM_HIT_NAMES = ("kick", "snare", "closed_hihat", "open_hihat", "crash")

# PSG noise: (noise_ctrl_nibble_low2, duration_sec, atten_start)
# SN76489 latch noise: 1 11 0 NF FB — we use white noise (FB=1) + rate
PSG_DRUM_NOISE = {
    "kick": (0x04, 0.12, 0),  # periodic-ish low via tone; use noise rate 0
    "snare": (0x05, 0.10, 1),
    "rimshot": (0x05, 0.06, 2),
    "clap": (0x06, 0.08, 1),
    "closed_hihat": (0x06, 0.04, 2),
    "open_hihat": (0x06, 0.14, 2),
    "crash": (0x07, 0.35, 1),
    "ride": (0x07, 0.20, 2),
    "low_tom": (0x04, 0.10, 1),
    "mid_tom": (0x05, 0.10, 1),
    "high_tom": (0x05, 0.08, 2),
}

OpDict = dict[str, int]
PatchDict = dict[str, Any]


def _op(
    mul: int,
    dt: int,
    tl: int,
    rs: int,
    ar: int,
    am: int,
    d1r: int,
    d2r: int,
    rr: int,
    sl: int,
) -> OpDict:
    return {
        "mul": mul,
        "dt": dt,
        "tl": tl,
        "rs": rs,
        "ar": ar,
        "am": am,
        "d1r": d1r,
        "d2r": d2r,
        "rr": rr,
        "sl": sl,
    }


# Original MVP patches (not copied from third-party banks).
BUILTIN_PATCHES: dict[str, PatchDict] = {
    "lead": {
        "algo": 4,
        "fb": 3,
        "ops": [
            _op(5, 0, 30, 1, 31, 0, 10, 0, 8, 2),
            _op(1, 0, 18, 1, 28, 0, 8, 0, 7, 1),
            _op(1, 0, 40, 0, 25, 0, 6, 0, 6, 3),
            _op(1, 0, 8, 0, 31, 0, 12, 0, 10, 1),
        ],
    },
    "bass": {
        "algo": 0,
        "fb": 5,
        "ops": [
            _op(2, 3, 22, 2, 28, 0, 8, 2, 6, 3),
            _op(1, 0, 12, 1, 26, 0, 6, 1, 5, 2),
            _op(2, 0, 35, 1, 24, 0, 5, 0, 5, 4),
            _op(1, 0, 4, 0, 31, 0, 10, 0, 8, 1),
        ],
    },
    "harmony": {
        "algo": 5,
        "fb": 2,
        "ops": [
            _op(3, 0, 28, 0, 22, 0, 5, 0, 5, 4),
            _op(1, 1, 24, 0, 20, 0, 4, 0, 5, 3),
            _op(2, 0, 32, 0, 18, 0, 4, 0, 4, 5),
            _op(1, 0, 12, 0, 26, 0, 8, 0, 7, 2),
        ],
    },
}


def _clamp_op(op: dict) -> OpDict:
    return _op(
        mul=max(0, min(15, int(op.get("mul", 1)))),
        dt=max(0, min(7, int(op.get("dt", 0)))),
        tl=max(0, min(127, int(op.get("tl", 0)))),
        rs=max(0, min(3, int(op.get("rs", 0)))),
        ar=max(0, min(31, int(op.get("ar", 31)))),
        am=1 if op.get("am") else 0,
        d1r=max(0, min(31, int(op.get("d1r", 0)))),
        d2r=max(0, min(31, int(op.get("d2r", 0)))),
        rr=max(0, min(15, int(op.get("rr", 7)))),
        sl=max(0, min(15, int(op.get("sl", 0)))),
    )


def _validate_patch(raw: Any) -> PatchDict | None:
    if not isinstance(raw, dict):
        return None
    ops = raw.get("ops")
    if not isinstance(ops, list) or len(ops) != 4:
        return None
    try:
        return {
            "algo": max(0, min(7, int(raw.get("algo", 0)))),
            "fb": max(0, min(7, int(raw.get("fb", 0)))),
            "ops": [_clamp_op(o) for o in ops],
        }
    except (TypeError, ValueError):
        return None


def load_patch_bank(
    patches_dir: str | Path | None = None,
) -> tuple[dict[str, PatchDict], list[str]]:
    """Builtin bank + optional JSON overlays. Never raises on bad files."""
    bank = deepcopy(BUILTIN_PATCHES)
    warnings: list[str] = []
    directory = Path(patches_dir) if patches_dir else PATCHES_DIR
    if not directory.is_dir():
        return bank, warnings
    for path in sorted(directory.glob("*.json")):
        name = path.stem.lower()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"skip patch {path.name}: {exc}")
            continue
        patch = _validate_patch(raw)
        if patch is None:
            warnings.append(f"skip patch {path.name}: invalid schema")
            continue
        bank[name] = patch
    return bank, warnings


def discover_pcm(pcm_dir: str | Path | None = None) -> dict[str, Path]:
    directory = Path(pcm_dir) if pcm_dir else PCM_DIR
    found: dict[str, Path] = {}
    if not directory.is_dir():
        return found
    for name in PCM_HIT_NAMES:
        path = directory / f"{name}.wav"
        if path.is_file():
            found[name] = path
    return found


def wav_to_pcm_u8(path: str | Path, rate: int = PCM_RATE) -> bytes:
    """Load WAV → mono → resample → unsigned 8-bit (0x80 silence)."""
    with wave.open(str(path), "rb") as wf:
        n_ch = wf.getnchannels()
        width = wf.getsampwidth()
        src_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
    if width == 2:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    elif width == 1:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported sample width {width} in {path}")
    if n_ch > 1:
        samples = samples.reshape(-1, n_ch).mean(axis=1)
    if len(samples) == 0:
        return bytes([0x80])
    if src_rate != rate and len(samples) > 1:
        new_len = max(1, int(round(len(samples) * rate / src_rate)))
        x_old = np.arange(len(samples), dtype=np.float64)
        x_new = np.linspace(0.0, float(len(samples) - 1), new_len)
        samples = np.interp(x_new, x_old, samples)
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
    if peak > 1e-6:
        samples = samples / peak
    u8 = np.clip(np.round(samples * 127.0) + 128.0, 0, 255).astype(np.uint8)
    return bytes(u8)


def vgm_output_paths(
    out_root: str | Path,
    project_name: str,
    stem: str | None = None,
) -> dict[str, str]:
    stem = stem or project_name
    vgm_dir = Path(out_root) / project_name / "vgm"
    return {
        "dir": str(vgm_dir),
        "vgm": str(vgm_dir / f"{stem}.vgm"),
    }


# ─── MIDI parse / roles / voices ─────────────────────────────────────


def _ticks_to_seconds(abs_tick: int, ticks_per_beat: int, tempo_map: list[tuple[int, int]]) -> float:
    """tempo_map: sorted (tick, tempo_us_per_beat)."""
    if not tempo_map:
        return 0.0
    seconds = 0.0
    prev_tick = 0
    prev_tempo = tempo_map[0][1]
    for tick, tempo in tempo_map:
        if tick > abs_tick:
            break
        if tick > prev_tick:
            seconds += (tick - prev_tick) * (prev_tempo / 1_000_000.0) / ticks_per_beat
        prev_tick = tick
        prev_tempo = tempo
    if abs_tick > prev_tick:
        seconds += (abs_tick - prev_tick) * (prev_tempo / 1_000_000.0) / ticks_per_beat
    return seconds


def parse_midi_for_md(path: str | Path) -> dict[str, Any]:
    mid = mido.MidiFile(str(path))
    ticks = mid.ticks_per_beat
    tempo_map: list[tuple[int, int]] = [(0, 500000)]

    # Collect global tempo changes across all tracks
    for track in mid.tracks:
        abs_t = 0
        for msg in track:
            abs_t += msg.time
            if msg.type == "set_tempo":
                tempo_map.append((abs_t, msg.tempo))
    tempo_map.sort(key=lambda x: x[0])
    # Deduplicate: keep last tempo at each tick
    dedup: dict[int, int] = {}
    for tick, tempo in tempo_map:
        dedup[tick] = tempo
    tempo_map = sorted(dedup.items())

    tracks_out: list[dict[str, Any]] = []
    for ti, track in enumerate(mid.tracks):
        name = ""
        prog = 0
        abs_t = 0
        pending: dict[tuple[int, int], dict] = {}
        notes: list[dict[str, Any]] = []
        saw_ch9 = False
        for msg in track:
            abs_t += msg.time
            if msg.type == "track_name":
                name = (msg.name or "").strip()
            elif msg.type == "program_change":
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
                    saw_ch9 = True
            elif msg.type == "note_off" or (
                msg.type == "note_on" and msg.velocity == 0
            ):
                key = (msg.channel, msg.note)
                if key not in pending:
                    continue
                n = pending.pop(key)
                start = _ticks_to_seconds(n["start_tick"], ticks, tempo_map)
                end = _ticks_to_seconds(abs_t, ticks, tempo_map)
                n["start_sec"] = start
                n["dur_sec"] = max(end - start, 0.01)
                notes.append(n)
        for n in pending.values():
            start = _ticks_to_seconds(n["start_tick"], ticks, tempo_map)
            n["start_sec"] = start
            n["dur_sec"] = 0.1
            notes.append(n)
        if not notes and not name:
            continue
        tracks_out.append(
            {
                "index": ti,
                "name": name or f"track{ti}",
                "program": prog,
                "notes": notes,
                "is_drums": saw_ch9
                or any(n.get("ch") == 9 for n in notes),
            }
        )

    duration = 0.0
    for tr in tracks_out:
        for n in tr["notes"]:
            duration = max(duration, n["start_sec"] + n["dur_sec"])
    bpm = 60_000_000 / tempo_map[0][1] if tempo_map else 120.0
    return {
        "tracks": tracks_out,
        "ticks_per_beat": ticks,
        "tempo_map": tempo_map,
        "bpm": bpm,
        "duration": duration,
        "path": str(path),
    }


def infer_role(track: dict[str, Any]) -> str:
    if track.get("is_drums"):
        return "drums"
    name = (track.get("name") or "").lower()
    prog = int(track.get("program") or 0)
    if "drum" in name or "perc" in name or "bater" in name:
        return "drums"
    if prog == 38 or "bass" in name or "baixo" in name:
        return "bass"
    if prog == 81 or "harmon" in name or "pad" in name:
        return "harmony"
    if prog == 80 or "melody" in name or "melod" in name or "lead" in name:
        return "lead"
    return "lead"


def assign_voices(
    parsed: dict[str, Any],
    pcm_reserved: bool = False,
) -> dict[str, Any]:
    """Map tracks to FM channels + drum events. Monophonic note-steal per FM ch."""
    max_fm = 5 if pcm_reserved else 6  # ch 0..4 or 0..5
    role_preferred = {"lead": 0, "harmony": 1, "bass": 2}
    warnings: list[str] = []
    fm_slots: dict[int, dict[str, Any]] = {}
    next_extra = 3
    drum_events: list[dict[str, Any]] = []

    melodic_tracks = []
    for tr in parsed["tracks"]:
        role = infer_role(tr)
        if role == "drums" or tr.get("is_drums"):
            for n in tr["notes"]:
                hit = DRUM_PITCH_TO_HIT.get(n["pitch"], "snare")
                drum_events.append(
                    {
                        "hit": hit,
                        "pitch": n["pitch"],
                        "start_sec": n["start_sec"],
                        "dur_sec": n["dur_sec"],
                        "vel": n["vel"],
                    }
                )
            continue
        melodic_tracks.append((role, tr))

    for role, tr in melodic_tracks:
        if role in role_preferred and role_preferred[role] not in fm_slots:
            ch = role_preferred[role]
        else:
            while next_extra < max_fm and next_extra in fm_slots:
                next_extra += 1
            if next_extra >= max_fm:
                warnings.append(
                    f"dropped track '{tr['name']}' ({role}): FM channel cap "
                    f"({max_fm})"
                )
                continue
            ch = next_extra
            next_extra += 1

        patch_key = role if role in ("lead", "bass", "harmony") else "lead"
        # Note-steal: sort by start, cut overlaps
        notes_sorted = sorted(tr["notes"], key=lambda n: n["start_sec"])
        stolen = 0
        cleaned: list[dict[str, Any]] = []
        for n in notes_sorted:
            if cleaned:
                prev = cleaned[-1]
                prev_end = prev["start_sec"] + prev["dur_sec"]
                if n["start_sec"] < prev_end:
                    prev["dur_sec"] = max(n["start_sec"] - prev["start_sec"], 0.01)
                    stolen += 1
            cleaned.append(dict(n))
        if stolen:
            warnings.append(
                f"FM ch{ch} '{tr['name']}': {stolen} overlapping note(s) stolen"
            )
        fm_slots[ch] = {
            "channel": ch,
            "role": role,
            "patch": patch_key,
            "track_name": tr["name"],
            "program": tr["program"],
            "notes": cleaned,
        }

    drum_events.sort(key=lambda e: e["start_sec"])
    return {
        "fm": [fm_slots[k] for k in sorted(fm_slots)],
        "drums": drum_events,
        "warnings": warnings,
        "pcm_reserved": pcm_reserved,
        "duration": parsed["duration"],
        "bpm": parsed["bpm"],
    }


# ─── VGM low-level ───────────────────────────────────────────────────


def midi_to_fnum(note: int, clock: int = YM2612_CLOCK) -> tuple[int, int]:
    """Return (block, fnumber) for MIDI note."""
    note = max(0, min(127, int(note)))
    freq = 440.0 * (2.0 ** ((note - 69) / 12.0))
    block = max(0, min(7, (note // 12) - 1))
    # fnum = freq * 2^20 * 144 / (clock * 2^block)
    denom = clock * (2**block)
    fnum = int(round(freq * (1 << 20) * 144.0 / denom)) if denom else 0
    fnum = max(0, min(0x7FF, fnum))
    return block, fnum


def _ym_port(channel: int) -> int:
    return 0 if channel < 3 else 1


def _ym_ch(channel: int) -> int:
    return channel % 3


def _key_on_channel(channel: int) -> int:
    # Key-on channel field: 0-2 and 4-6
    return channel if channel < 3 else channel + 1


def ym_write(port: int, reg: int, data: int) -> bytes:
    op = 0x52 if port == 0 else 0x53
    return bytes([op, reg & 0xFF, data & 0xFF])


def psg_write(data: int) -> bytes:
    return bytes([0x50, data & 0xFF])


def vgm_wait_samples(samples: int) -> bytes:
    out = bytearray()
    while samples > 0:
        if samples == 735:
            out.append(0x62)
            samples = 0
        elif samples == 882:
            out.append(0x63)
            samples = 0
        elif samples <= 16:
            out.append(0x70 + (samples - 1))
            samples = 0
        elif samples <= 65535:
            out += bytes([0x61, samples & 0xFF, (samples >> 8) & 0xFF])
            samples = 0
        else:
            out += bytes([0x61, 0xFF, 0xFF])
            samples -= 65535
    return bytes(out)


def vgm_wait_seconds(seconds: float) -> bytes:
    if seconds <= 0:
        return b""
    return vgm_wait_samples(max(1, int(round(seconds * VGM_SAMPLE_RATE))))


def apply_patch_commands(channel: int, patch: PatchDict) -> bytes:
    """
    Emit YM2612 register writes for a patch.
    Logical ops[0..3] = op1..op4; chip register slots are op1,op3,op2,op4
    → write order indices [0, 2, 1, 3].
    """
    port = _ym_port(channel)
    ch = _ym_ch(channel)
    out = bytearray()
    algo = int(patch["algo"]) & 7
    fb = int(patch["fb"]) & 7
    out += ym_write(port, 0xB0 + ch, (fb << 3) | algo)
    out += ym_write(port, 0xB4 + ch, 0xC0)  # L+R, AMS/FMS 0

    logical = patch["ops"]
    # register slot order: 0=op1, 1=op3, 2=op2, 3=op4
    reg_ops = [logical[0], logical[2], logical[1], logical[3]]
    for slot, op in enumerate(reg_ops):
        off = ch + slot * 4
        out += ym_write(port, 0x30 + off, ((op["dt"] & 7) << 4) | (op["mul"] & 15))
        out += ym_write(port, 0x40 + off, op["tl"] & 127)
        out += ym_write(port, 0x50 + off, ((op["rs"] & 3) << 6) | (op["ar"] & 31))
        out += ym_write(port, 0x60 + off, ((op["am"] & 1) << 7) | (op["d1r"] & 31))
        out += ym_write(port, 0x70 + off, op["d2r"] & 31)
        out += ym_write(port, 0x80 + off, ((op["sl"] & 15) << 4) | (op["rr"] & 15))
        out += ym_write(port, 0x90 + off, 0)
    return bytes(out)


def fm_key_on(channel: int, note: int) -> bytes:
    block, fnum = midi_to_fnum(note)
    port = _ym_port(channel)
    ch = _ym_ch(channel)
    out = bytearray()
    out += ym_write(port, 0xA4 + ch, ((block & 7) << 3) | ((fnum >> 8) & 7))
    out += ym_write(port, 0xA0 + ch, fnum & 0xFF)
    out += ym_write(0, 0x28, 0xF0 | _key_on_channel(channel))
    return bytes(out)


def fm_key_off(channel: int) -> bytes:
    return ym_write(0, 0x28, _key_on_channel(channel))


def _psg_drum_params(hit: str, velocity: int = 100) -> tuple[int, float, int]:
    """Return (noise_bits, duration_sec, atten)."""
    cfg = PSG_DRUM_NOISE.get(hit, PSG_DRUM_NOISE["snare"])
    noise_bits, dur, base_att = cfg
    att = max(0, min(15, base_att + (0 if velocity >= 90 else 2)))
    return noise_bits & 0x07, float(dur), att


def psg_drum_on(hit: str, velocity: int = 100) -> bytes:
    """Instantaneous PSG noise trigger (no embedded wait)."""
    noise_bits, _dur, att = _psg_drum_params(hit, velocity)
    out = bytearray()
    out += psg_write(0xE0 | noise_bits)
    out += psg_write(0xF0 | (att & 0x0F))
    return bytes(out)


def psg_drum_off() -> bytes:
    """Silence PSG noise channel."""
    return psg_write(0xF0 | 0x0F)


def psg_drum_hit(hit: str, velocity: int = 100) -> bytes:
    """Self-contained hit with wait (tests/debug only — not used by scheduler)."""
    _bits, dur, _att = _psg_drum_params(hit, velocity)
    return psg_drum_on(hit, velocity) + vgm_wait_seconds(dur) + psg_drum_off()


def build_vgm_header(data_len: int, total_samples: int) -> bytes:
    """VGM 1.50 header; data begins at 0x40."""
    file_size = VGM_HEADER_SIZE + data_len
    buf = bytearray(VGM_HEADER_SIZE)
    buf[0:4] = b"Vgm "
    struct.pack_into("<I", buf, 0x04, file_size - 4)
    struct.pack_into("<I", buf, 0x08, VGM_VERSION)
    struct.pack_into("<I", buf, 0x0C, PSG_CLOCK)
    struct.pack_into("<I", buf, 0x14, 0)  # GD3
    struct.pack_into("<I", buf, 0x18, max(0, int(total_samples)))
    struct.pack_into("<I", buf, 0x1C, 0)  # loop offset
    struct.pack_into("<I", buf, 0x20, 0)  # loop samples
    struct.pack_into("<I", buf, 0x24, 60)  # rate
    struct.pack_into("<H", buf, 0x28, 0x0009)  # SN76489 feedback
    buf[0x2A] = 16  # shift register width
    buf[0x2B] = 0
    struct.pack_into("<I", buf, 0x2C, YM2612_CLOCK)
    struct.pack_into("<I", buf, 0x34, 0x0C)  # data at 0x40 (= 0x34+0x0C)
    return bytes(buf)


def write_vgm_file(path: str | Path, data_stream: bytes, total_samples: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = build_vgm_header(len(data_stream), total_samples)
    path.write_bytes(header + data_stream)


def _pcm_data_block(sample: bytes) -> bytes:
    # 0x67 0x66 type size[4] data — type 0x00 uncompressed
    size = len(sample)
    return bytes([0x67, 0x66, 0x00]) + struct.pack("<I", size) + sample


def _dac_enable() -> bytes:
    return ym_write(0, 0x2B, 0x80)


def _dac_disable() -> bytes:
    return ym_write(0, 0x2B, 0x00)


def _dac_write_byte(value: int) -> bytes:
    return ym_write(0, 0x2A, value & 0xFF)


def _dac_play_sample(sample: bytes) -> bytes:
    """Self-contained DAC stream with waits (debug only — not used by scheduler)."""
    out = bytearray()
    out += _dac_enable()
    step = max(1, int(round(VGM_SAMPLE_RATE / PCM_RATE)))
    for b in sample:
        out += _dac_write_byte(b)
        out += vgm_wait_samples(step)
    out += _dac_disable()
    return bytes(out)


# Event priority at the same timestamp (lower runs first).
# Off MUST precede On: when a note ends exactly as the next begins, the old
# note must be released before the new one is keyed, or the new note is
# keyed on and instantly killed by the pending key-off.
_PRIO_FM_OFF = 0
_PRIO_FM_ON = 1
_PRIO_DRUM_ON = 2
_PRIO_DAC_BYTE = 3
_PRIO_DRUM_OFF = 4
_PRIO_DAC_OFF = 5


def schedule_to_vgm(
    assignment: dict[str, Any],
    patch_bank: dict[str, PatchDict],
    pcm_samples: dict[str, bytes] | None = None,
) -> tuple[bytes, int, dict[str, Any]]:
    """Build timed VGM data stream (without header).

    All musical time advances through the shared event timeline. Drum/DAC hits
    are instantaneous register writes scheduled at start/end (or per PCM byte);
    they must not embed waits that desync FM note on/off.
    """
    pcm_samples = pcm_samples or {}
    events: list[tuple[float, int, str, Any]] = []

    meta = {
        "pcm_hits": [],
        "psg_fallback_hits": [],
        "patches_used": [],
    }

    stream = bytearray()
    used_patches: set[str] = set()
    for voice in assignment["fm"]:
        key = voice["patch"]
        patch = patch_bank.get(key) or BUILTIN_PATCHES["lead"]
        stream += apply_patch_commands(voice["channel"], patch)
        used_patches.add(key)
    meta["patches_used"] = sorted(used_patches)

    for hit, data in pcm_samples.items():
        stream += _pcm_data_block(data)

    for voice in assignment["fm"]:
        ch = voice["channel"]
        for n in voice["notes"]:
            events.append(
                (n["start_sec"], _PRIO_FM_ON, "fm_on", (ch, n["pitch"], n["vel"]))
            )
            events.append(
                (n["start_sec"] + n["dur_sec"], _PRIO_FM_OFF, "fm_off", (ch,))
            )

    # Generation tokens: only the latest PSG/DAC owner may silence the channel.
    psg_gen = 0
    dac_gen = 0
    for d in assignment["drums"]:
        hit = d["hit"]
        start = float(d["start_sec"])
        vel = int(d.get("vel", 100))
        if hit in pcm_samples:
            sample = pcm_samples[hit]
            if not sample:
                continue
            dac_gen += 1
            gen = dac_gen
            if hit not in meta["pcm_hits"]:
                meta["pcm_hits"].append(hit)
            events.append((start, _PRIO_DRUM_ON, "dac_on", gen))
            for i, b in enumerate(sample):
                events.append(
                    (start + i / float(PCM_RATE), _PRIO_DAC_BYTE, "dac_byte", (gen, b))
                )
            end = start + len(sample) / float(PCM_RATE)
            events.append((end, _PRIO_DAC_OFF, "dac_off", gen))
        else:
            _bits, dur, _att = _psg_drum_params(hit, vel)
            psg_gen += 1
            gen = psg_gen
            if hit not in meta["psg_fallback_hits"]:
                meta["psg_fallback_hits"].append(hit)
            events.append((start, _PRIO_DRUM_ON, "psg_on", (gen, hit, vel)))
            events.append((start + dur, _PRIO_DRUM_OFF, "psg_off", gen))

    events.sort(key=lambda e: (e[0], e[1]))

    t = 0.0
    active_psg_gen = 0
    active_dac_gen = 0
    for abs_t, _prio, kind, payload in events:
        if abs_t > t:
            stream += vgm_wait_seconds(abs_t - t)
            t = abs_t
        if kind == "fm_on":
            ch, pitch, _vel = payload
            stream += fm_key_on(ch, pitch)
        elif kind == "fm_off":
            (ch,) = payload
            stream += fm_key_off(ch)
        elif kind == "psg_on":
            gen, hit, vel = payload
            active_psg_gen = gen
            stream += psg_drum_on(hit, vel)
        elif kind == "psg_off":
            if payload == active_psg_gen:
                stream += psg_drum_off()
        elif kind == "dac_on":
            active_dac_gen = payload
            stream += _dac_enable()
        elif kind == "dac_byte":
            gen, b = payload
            if gen == active_dac_gen:
                stream += _dac_write_byte(b)
        elif kind == "dac_off":
            if payload == active_dac_gen:
                stream += _dac_disable()

    for voice in assignment["fm"]:
        stream += fm_key_off(voice["channel"])
    if active_psg_gen:
        stream += psg_drum_off()
    if active_dac_gen:
        stream += _dac_disable()
    stream += vgm_wait_seconds(0.05)
    stream.append(0x66)

    total_samples = int(round(max(t, assignment.get("duration", 0)) * VGM_SAMPLE_RATE))
    return bytes(stream), total_samples, meta


def export_midi_to_vgm(
    midi_path: str | Path,
    out_path: str | Path | None = None,
    *,
    project_name: str | None = None,
    patches_dir: str | Path | None = None,
    pcm_dir: str | Path | None = None,
    destination_dir: str | Path | None = None,
) -> dict[str, Any]:
    midi_path = Path(midi_path)
    if not midi_path.is_file():
        raise FileNotFoundError(f"MIDI not found: {midi_path}")

    stem = midi_path.stem
    project = project_name or stem
    out_root = Path(destination_dir) if destination_dir else OUT_DIR
    if out_path is None:
        paths = vgm_output_paths(out_root, project, stem)
        out_path = paths["vgm"]
    else:
        out_path = Path(out_path)

    patch_bank, patch_warnings = load_patch_bank(patches_dir)
    pcm_files = discover_pcm(pcm_dir)
    pcm_samples: dict[str, bytes] = {}
    convert_warnings: list[str] = []
    for name, path in pcm_files.items():
        try:
            pcm_samples[name] = wav_to_pcm_u8(path)
        except Exception as exc:  # noqa: BLE001 — BYO never fatal
            convert_warnings.append(f"pcm {name}: {exc}")

    # Reserve ch6 only if we will actually use at least one PCM hit present
    parsed = parse_midi_for_md(midi_path)
    # Peek drum hits to see if any PCM applies
    temp_assign = assign_voices(parsed, pcm_reserved=False)
    used_hits = {d["hit"] for d in temp_assign["drums"]}
    pcm_usable = {h: pcm_samples[h] for h in used_hits if h in pcm_samples}
    pcm_reserved = bool(pcm_usable)

    assignment = assign_voices(parsed, pcm_reserved=pcm_reserved)
    stream, total_samples, meta = schedule_to_vgm(
        assignment, patch_bank, pcm_samples=pcm_usable
    )
    write_vgm_file(out_path, stream, total_samples)

    pcm_hits = meta["pcm_hits"]
    psg_hits = meta["psg_fallback_hits"]
    if pcm_hits and not psg_hits:
        drums_mode = "pcm"
    elif pcm_hits and psg_hits:
        drums_mode = "mixed"
    else:
        drums_mode = "psg"

    warnings = list(patch_warnings) + list(assignment["warnings"]) + convert_warnings
    return {
        "file": str(Path(out_path).resolve()),
        "project": project,
        "drums_mode": drums_mode,
        "patches_used": meta["patches_used"],
        "pcm_hits": pcm_hits,
        "psg_fallback_hits": psg_hits,
        "fm_channels_used": [v["channel"] for v in assignment["fm"]],
        "warnings": warnings,
        "duration_sec": round(float(parsed["duration"]), 3),
        "output_layout": f"output/audio/{project}/vgm/",
        "total_samples": total_samples,
        "pcm_reserved": pcm_reserved,
    }


def get_megadrive_capabilities_impl(
    patches_dir: str | Path | None = None,
    pcm_dir: str | Path | None = None,
) -> dict[str, Any]:
    bank, _ = load_patch_bank(patches_dir)
    directory = Path(patches_dir) if patches_dir else PATCHES_DIR
    overrides = []
    if directory.is_dir():
        overrides = sorted(p.stem.lower() for p in directory.glob("*.json"))
    pcm = discover_pcm(pcm_dir)
    hints = [
        "Place optional FM patch JSON in assets/megadrive/patches/{lead,bass,harmony}.json",
        "Place optional PCM drums in assets/megadrive/pcm/{kick,snare,closed_hihat,open_hihat,crash}.wav",
        "Without PCM, drums use PSG noise (always works).",
        "SGDK: add XGM my_bgm \"path/to/track.vgm\" in your .res — rescomp runs xgmtool.",
        "See assets/megadrive/README.md — nobu ships no third-party sample kits.",
    ]
    drums_default = "psg" if not pcm else "mixed"
    return {
        "vgm_export": True,
        "builtin_patches": sorted(BUILTIN_PATCHES.keys()),
        "override_patches": overrides,
        "pcm_hits_found": sorted(pcm.keys()),
        "drums_default": drums_default,
        "pcm_rate": PCM_RATE,
        "output_layout": "output/audio/{project}/vgm/",
        "install_hints": hints,
        "patch_bank_size": len(bank),
    }


def dump_voices(midi_path: str | Path, pcm_reserved: bool = False) -> dict[str, Any]:
    parsed = parse_midi_for_md(midi_path)
    assignment = assign_voices(parsed, pcm_reserved=pcm_reserved)
    return {
        "path": str(midi_path),
        "duration": parsed["duration"],
        "bpm": parsed["bpm"],
        "roles": [
            {
                "name": t["name"],
                "program": t["program"],
                "role": infer_role(t),
                "notes": len(t["notes"]),
                "is_drums": t.get("is_drums"),
            }
            for t in parsed["tracks"]
        ],
        "assignment": {
            "fm": [
                {
                    "channel": v["channel"],
                    "role": v["role"],
                    "patch": v["patch"],
                    "track_name": v["track_name"],
                    "notes": len(v["notes"]),
                }
                for v in assignment["fm"]
            ],
            "drums": len(assignment["drums"]),
            "warnings": assignment["warnings"],
            "pcm_reserved": assignment["pcm_reserved"],
        },
    }
