#!/usr/bin/env python3
"""Regression: builtin FM bank + JSON overlay loader."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import nobu_megadrive as md


def main() -> int:
    failures = 0

    bank, warnings = md.load_patch_bank(ROOT / "assets" / "megadrive" / "patches")
    for key in ("lead", "bass", "harmony"):
        if key not in bank:
            print(f"FAIL missing builtin {key}")
            failures += 1
        else:
            ops = bank[key]["ops"]
            if len(ops) != 4:
                print(f"FAIL {key} ops len {len(ops)}")
                failures += 1
            elif not (0 <= ops[0]["tl"] <= 127 and 0 <= ops[0]["ar"] <= 31):
                print(f"FAIL {key} op ranges")
                failures += 1
            else:
                print(f"OK  builtin {key}")

    with tempfile.TemporaryDirectory() as tmp:
        tdir = Path(tmp)
        override = {
            "algo": 2,
            "fb": 1,
            "ops": [
                {"mul": 1, "dt": 0, "tl": 10, "rs": 0, "ar": 31, "am": 0, "d1r": 0, "d2r": 0, "rr": 8, "sl": 0},
                {"mul": 1, "dt": 0, "tl": 10, "rs": 0, "ar": 31, "am": 0, "d1r": 0, "d2r": 0, "rr": 8, "sl": 0},
                {"mul": 1, "dt": 0, "tl": 10, "rs": 0, "ar": 31, "am": 0, "d1r": 0, "d2r": 0, "rr": 8, "sl": 0},
                {"mul": 1, "dt": 0, "tl": 5, "rs": 0, "ar": 31, "am": 0, "d1r": 0, "d2r": 0, "rr": 8, "sl": 0},
            ],
        }
        (tdir / "lead.json").write_text(json.dumps(override), encoding="utf-8")
        (tdir / "bad.json").write_text("{not json", encoding="utf-8")
        (tdir / "broken.json").write_text(json.dumps({"algo": 1}), encoding="utf-8")
        bank2, warns2 = md.load_patch_bank(tdir)
        if bank2["lead"]["algo"] != 2 or bank2["lead"]["ops"][3]["tl"] != 5:
            print("FAIL override did not win")
            failures += 1
        else:
            print("OK  JSON override wins for lead")
        if not any("bad.json" in w for w in warns2):
            print(f"FAIL expected bad.json warning, got {warns2}")
            failures += 1
        else:
            print("OK  bad JSON skipped with warning")
        if not any("broken.json" in w for w in warns2):
            print(f"FAIL expected broken.json warning, got {warns2}")
            failures += 1
        else:
            print("OK  invalid schema skipped")

    # Role / assign smoke
    roles = [
        ({"is_drums": True, "name": "x", "program": 0}, "drums"),
        ({"is_drums": False, "name": "bass_line", "program": 0}, "bass"),
        ({"is_drums": False, "name": "t", "program": 81}, "harmony"),
        ({"is_drums": False, "name": "t", "program": 80}, "lead"),
        ({"is_drums": False, "name": "misc", "program": 0}, "lead"),
    ]
    for tr, expect in roles:
        got = md.infer_role(tr)
        if got != expect:
            print(f"FAIL role {tr} -> {got} expected {expect}")
            failures += 1
        else:
            print(f"OK  role {expect}")

    # apply_patch non-empty
    cmds = md.apply_patch_commands(0, md.BUILTIN_PATCHES["lead"])
    if len(cmds) < 10:
        print(f"FAIL apply_patch too short: {len(cmds)}")
        failures += 1
    else:
        print(f"OK  apply_patch bytes={len(cmds)}")

    if md.discover_pcm(ROOT / "assets" / "megadrive" / "pcm") != {}:
        print("FAIL unexpected pcm files in clean tree")
        failures += 1
    else:
        print("OK  empty pcm discovery")

    # Scheduler must keep FM note duration when PSG drums overlap (no embedded waits).
    assignment = {
        "fm": [
            {
                "channel": 0,
                "patch": "lead",
                "name": "lead",
                "notes": [{"pitch": 60, "start_sec": 0.0, "dur_sec": 1.0, "vel": 100}],
            }
        ],
        "drums": [
            {"hit": "kick", "start_sec": 0.0, "vel": 100},
            {"hit": "closed_hihat", "start_sec": 0.25, "vel": 90},
            {"hit": "snare", "start_sec": 0.5, "vel": 100},
            {"hit": "closed_hihat", "start_sec": 0.75, "vel": 90},
        ],
        "duration": 1.2,
        "warnings": [],
        "pcm_reserved": False,
        "bpm": 120,
    }
    stream, total_samples, meta = md.schedule_to_vgm(assignment, md.BUILTIN_PATCHES, {})
    wait_samples = _count_wait_samples_between_fm_gate(stream)
    min_expected = int(0.8 * md.VGM_SAMPLE_RATE)
    if wait_samples < min_expected:
        print(
            f"FAIL FM note crushed by drums: wait_samples={wait_samples} "
            f"(need >= {min_expected})"
        )
        failures += 1
    else:
        print(f"OK  FM sustains through drums (wait_samples={wait_samples})")
    if total_samples < min_expected:
        print(f"FAIL total_samples too short: {total_samples}")
        failures += 1
    if not meta.get("psg_fallback_hits"):
        print(f"FAIL expected psg hits in meta: {meta}")
        failures += 1

    print()
    if failures:
        print(f"{failures} failure(s)")
        return 1
    print("all patch/role tests passed")
    return 0


def _count_wait_samples_between_fm_gate(stream: bytes) -> int:
    """Sum wait samples between first YM2612 key-on (0x28 | 0xF0) and next key-off."""
    i = 0
    counting = False
    total = 0
    while i < len(stream):
        c = stream[i]
        if c == 0x66:
            break
        if c in (0x52, 0x53) and i + 2 < len(stream):
            reg, data = stream[i + 1], stream[i + 2]
            if c == 0x52 and reg == 0x28:
                if data & 0xF0:
                    counting = True
                    total = 0
                elif counting:
                    return total
            i += 3
            continue
        if c == 0x50:
            i += 2
            continue
        if c == 0x61 and i + 2 < len(stream):
            n = stream[i + 1] | (stream[i + 2] << 8)
            if counting:
                total += n
            i += 3
            continue
        if c == 0x62:
            if counting:
                total += 735
            i += 1
            continue
        if c == 0x63:
            if counting:
                total += 882
            i += 1
            continue
        if 0x70 <= c <= 0x7F:
            if counting:
                total += (c - 0x70) + 1
            i += 1
            continue
        # Skip other cmds conservatively
        if c == 0x4F:
            i += 2
        elif 0x51 <= c <= 0x5F:
            i += 3
        elif c == 0x67 and i + 6 < len(stream):
            size = int.from_bytes(stream[i + 3 : i + 7], "little")
            i += 7 + size
        else:
            i += 1
    return total


if __name__ == "__main__":
    raise SystemExit(main())
