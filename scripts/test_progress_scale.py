#!/usr/bin/env python3
"""Regression: global progress scale for render_all_modes. Run from repo root."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import nobu_mcp


class _MockCtx:
    def __init__(self) -> None:
        self.events: list[tuple[str, float]] = []

    def report_progress(self, progress: float, total: float, message: str) -> None:
        self.events.append((message, progress))


def main() -> int:
    ctx = _MockCtx()
    modes = ("chip", "hybrid", "sf2")
    pcts: list[float] = []

    for i, mode in enumerate(modes):
        nobu_mcp._report_mode_boundary(ctx, f"mode_{mode}_start", i / len(modes))
        cb = nobu_mcp._make_scaled_progress_callback(ctx, mode, i, len(modes))
        for local in (0.0, 0.3, 0.6, 1.0):
            cb("synthesizing_drums" if local < 0.5 else "writing_ogg", local)
        nobu_mcp._report_mode_boundary(ctx, f"mode_{mode}_done", (i + 1) / len(modes))

    pcts = [pct for _, pct in ctx.events]
    for i in range(1, len(pcts)):
        if pcts[i] + 1e-9 < pcts[i - 1]:
            print(f"test_progress_scale: FAIL non-monotonic at {i}: {pcts[i-1]} -> {pcts[i]}")
            return 1

    prefixes = {msg.split(":")[0] for msg, _ in ctx.events if ":" in msg}
    for mode in modes:
        if f"mode_{mode}" not in prefixes and f"mode_{mode}_start" not in {m for m, _ in ctx.events}:
            pass
    if not any(m.startswith("mode_chip:") for m, _ in ctx.events):
        print("test_progress_scale: FAIL missing mode_chip: prefix")
        return 1

    chip_end = nobu_mcp._scale_progress(0, 3, 1.0)
    hybrid_start = nobu_mcp._scale_progress(1, 3, 0.0)
    if chip_end > hybrid_start + 1e-9:
        print(f"test_progress_scale: FAIL chip end {chip_end} > hybrid start {hybrid_start}")
        return 1

    print("test_progress_scale: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
