#!/usr/bin/env python3
"""
Cursor hook: keep CHANGELOG.md + pyproject version in sync with SemVer.

Policy: NEVER use [Unreleased]. Every finalize cuts a new MAJOR.MINOR.PATCH.

Events:
  sessionStart — record git baseline ONLY (never write CHANGELOG / version)
  stop         — agent turn finished → bump SemVer once per conversation
  sessionEnd   — chat ended → same bump if stop did not already finalize

Stdin: Cursor hook JSON. Stdout: optional JSON (sessionStart may return env).
Fail-open: never block the agent on changelog errors.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HOOKS_DIR.parent.parent
STATE_DIR = HOOKS_DIR / "state"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"

SKIP_PATH_PREFIXES = (
    ".cursor/hooks/state/",
    ".venv/",
    "output/",
    "assets/midi/",
    "__pycache__/",
    ".git/",
)

SKIP_EXACT = {
    "CHANGELOG.md",  # avoid self-trigger loops when only changelog touched later
    "pyproject.toml",  # version sync is the release itself, not a bullet
}

SECTION_ORDER = (
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
)

def log(msg: str) -> None:
    print(f"[nobu-changelog] {msg}", file=sys.stderr)


def read_stdin_json() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def git(*args: str) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0:
        return ""
    return (r.stdout or "").strip()


def is_git_repo() -> bool:
    return bool(git("rev-parse", "--is-inside-work-tree"))


LAST_SESSION_PATH = STATE_DIR / "last_session.json"


def session_state_path(session_id: str) -> Path:
    safe = re.sub(r"[^\w.-]+", "_", session_id or "unknown")
    return STATE_DIR / f"{safe}.json"


def resolve_session_id(payload: dict) -> str:
    """Prefer Cursor ids; fall back to last sessionStart (stop often omits ids)."""
    for key in ("session_id", "conversation_id", "composer_id"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    env = os.environ.get("NOBU_SESSION_ID")
    if env and env.strip():
        return env.strip()
    if LAST_SESSION_PATH.exists():
        try:
            data = json.loads(LAST_SESSION_PATH.read_text(encoding="utf-8"))
            sid = data.get("session_id")
            if isinstance(sid, str) and sid.strip():
                return sid.strip()
        except (json.JSONDecodeError, OSError):
            pass
    return "unknown"


def load_state(session_id: str) -> dict:
    path = session_state_path(session_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(session_id: str, data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    session_state_path(session_id).write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    LAST_SESSION_PATH.write_text(
        json.dumps({"session_id": session_id}, indent=2) + "\n",
        encoding="utf-8",
    )


def should_skip_path(path: str) -> bool:
    norm = path.replace("\\", "/").lstrip("./")
    if norm in SKIP_EXACT:
        return True
    return any(norm.startswith(p) for p in SKIP_PATH_PREFIXES)


def has_commits() -> bool:
    return bool(git("rev-parse", "--verify", "HEAD"))


def changed_paths_since(baseline: str | None) -> list[tuple[str, str]]:
    """Return list of (status, path) for session changes.

    Requires at least one commit. Without a baseline (or with an empty repo),
    we only consider tracked modifications (staged/unstaged) — never a full
    dump of every untracked file (that would spam the changelog before the
    first commit).
    """
    if not has_commits():
        return []

    entries: list[tuple[str, str]] = []
    if baseline and git("rev-parse", "--verify", baseline):
        out = git("diff", "--name-status", f"{baseline}..HEAD")
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                entries.append((parts[0].strip(), parts[-1].strip()))

    # Working tree (tracked changes only)
    for args in (
        ["diff", "--name-status"],
        ["diff", "--name-status", "--cached"],
    ):
        out = git(*args)
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                entries.append((parts[0].strip(), parts[-1].strip()))

    # Untracked: only when we have a session baseline (post-first-commit)
    # and the file looks like source/docs — never entire trees
    if baseline:
        out = git("ls-files", "--others", "--exclude-standard")
        for line in out.splitlines():
            path = line.strip().replace("\\", "/")
            if not path or should_skip_path(path):
                continue
            if path.endswith(
                (".py", ".md", ".toml", ".txt", ".json", ".mdc", ".yml", ".yaml")
            ):
                entries.append(("A", path))

    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for status, path in entries:
        if not path or should_skip_path(path):
            continue
        key = path.replace("\\", "/")
        if key in seen:
            continue
        seen.add(key)
        unique.append((status[0].upper(), key))
    return unique


def classify(paths: list[tuple[str, str]]) -> dict[str, list[str]]:
    buckets = {s: [] for s in SECTION_ORDER}
    bump = "patch"  # patch | minor | major

    added_docs = 0
    changed_docs = 0
    skill_touch = False

    for status, path in paths:
        lower = path.lower()

        if path.startswith(".claude/skills/"):
            skill_touch = True
            continue

        if status == "D":
            buckets["Removed"].append(f"Removed `{path}`")
            if "nobu_mcp" in path:
                bump = "major"
            continue

        if status == "A":
            if path.endswith(".py") or path.startswith("scripts/") or path.startswith(
                "examples/"
            ):
                buckets["Added"].append(f"Added `{path}`")
                if bump != "major":
                    bump = "minor"
            elif path.endswith(".md"):
                added_docs += 1
            elif path.startswith(".cursor/hooks"):
                buckets["Added"].append(f"Added Cursor hook `{path}`")
                if bump != "major":
                    bump = "minor"
            else:
                buckets["Added"].append(f"Added `{path}`")
            continue

        if "changelog" in lower:
            continue
        if path.endswith(".py") or path.startswith("scripts/"):
            if any(k in lower for k in ("fix", "bug", "fallback")):
                buckets["Fixed"].append(f"Updated `{path}`")
            else:
                buckets["Changed"].append(f"Updated `{path}`")
        elif path.endswith(".md"):
            changed_docs += 1
        else:
            buckets["Changed"].append(f"Updated `{path}`")

    if skill_touch:
        buckets["Changed"].append("Updated game-music-producer skill docs")
    if added_docs:
        buckets["Added"].append(
            f"Added/updated {added_docs} documentation file(s)"
        )
    if changed_docs:
        buckets["Changed"].append(
            f"Revised {changed_docs} documentation file(s)"
        )

    for key in buckets:
        buckets[key] = _dedupe(buckets[key])[:12]

    buckets["_bump"] = [bump]  # type: ignore[assignment]
    return buckets


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def read_pyproject_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', text, re.M)
    if not m:
        raise ValueError("version not found in pyproject.toml")
    return m.group(1)


def write_pyproject_version(new_version: str) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    text2, n = re.subn(
        r'^version\s*=\s*"\d+\.\d+\.\d+"',
        f'version = "{new_version}"',
        text,
        count=1,
        flags=re.M,
    )
    if n != 1:
        raise ValueError("failed to update version in pyproject.toml")
    PYPROJECT.write_text(text2, encoding="utf-8")


def bump_version(current: str, kind: str) -> str:
    major, minor, patch = (int(x) for x in current.split("."))
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def parse_semver(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def version_gt(left: str, right: str) -> bool:
    return parse_semver(left) > parse_semver(right)


def latest_changelog_version() -> str | None:
    if not CHANGELOG.exists():
        return None
    match = re.search(
        r"^## \[(\d+\.\d+\.\d+)\]",
        CHANGELOG.read_text(encoding="utf-8"),
        re.M,
    )
    return match.group(1) if match else None


def pyproject_version_at(ref: str | None) -> str | None:
    if not ref:
        return None
    text = git("show", f"{ref}:pyproject.toml")
    if not text:
        return None
    match = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', text, re.M)
    return match.group(1) if match else None


def agent_already_cut_release(baseline: str | None) -> bool:
    """Skip auto-bump when the agent already wrote matching CHANGELOG + version."""
    top = latest_changelog_version()
    current = read_pyproject_version()
    if not top or top != current:
        return False
    base = pyproject_version_at(baseline)
    if base is None:
        return False
    return version_gt(top, base)


def empty_buckets() -> dict[str, list[str]]:
    return {s: [] for s in SECTION_ORDER}


def merge_buckets(
    existing: dict[str, list[str]], incoming: dict[str, list[str]]
) -> dict[str, list[str]]:
    merged = {s: list(existing.get(s, [])) for s in SECTION_ORDER}
    for s in SECTION_ORDER:
        for item in incoming.get(s, []):
            if item not in merged[s]:
                merged[s].append(item)
    return merged


def stronger_bump(a: str, b: str) -> str:
    rank = {"patch": 0, "minor": 1, "major": 2}
    return a if rank.get(a, 0) >= rank.get(b, 0) else b


def changelog_header_end(text: str) -> int:
    """Index where the first version section starts (after intro)."""
    m = re.search(r"^## \[\d+\.\d+\.\d+\]", text, re.M)
    if m:
        return m.start()
    # After intro paragraphs, before link footers
    m2 = re.search(r"^\[\d+\.\d+\.\d+\]:", text, re.M)
    return m2.start() if m2 else len(text)


def update_version_links(text: str, new_version: str, prev_version: str) -> str:
    repo = "https://github.com/francescojr/nobu"
    # Drop legacy Unreleased link if present
    text = re.sub(r"\[Unreleased\]:\s*https://github.com/[^\n]+\n?", "", text)
    link_line = f"[{new_version}]: {repo}/releases/tag/v{new_version}\n"
    if f"[{new_version}]:" not in text:
        # Prepend to footer links (first [x.y.z]: line)
        m = re.search(r"^\[\d+\.\d+\.\d+\]:", text, re.M)
        if m:
            text = text[: m.start()] + link_line + text[m.start() :]
        else:
            text = text.rstrip() + "\n\n" + link_line
    if prev_version and f"[{prev_version}]:" not in text:
        text = text.rstrip() + f"\n[{prev_version}]: {repo}/releases/tag/v{prev_version}\n"
    return text


def cut_version(
    buckets: dict[str, list[str]], bump_kind: str, session_id: str
) -> str | None:
    """Always create ## [X.Y.Z] — never [Unreleased]."""
    if not CHANGELOG.exists():
        log("CHANGELOG.md missing — skip")
        return None

    if not any(buckets.get(s) for s in SECTION_ORDER):
        log("no changelog bullets — skip")
        return None

    text = CHANGELOG.read_text(encoding="utf-8")
    # Strip any leftover Unreleased block
    text = re.sub(
        r"## \[Unreleased\]\s*\n.*?(?=\n## \[|\n\[\d+\.\d+\.\d+\]:|\Z)",
        "",
        text,
        count=1,
        flags=re.S,
    )

    current = read_pyproject_version()
    new_version = bump_version(current, bump_kind)
    today = date.today().isoformat()

    lines = [
        f"## [{new_version}] — {today}",
        "",
    ]
    for s in SECTION_ORDER:
        items = buckets.get(s, [])
        if not items:
            continue
        lines.append(f"### {s}")
        lines.append("")
        for item in items:
            lines.append(f"- {item}")
        lines.append("")
    release_block = "\n".join(lines).rstrip() + "\n\n"

    insert_at = changelog_header_end(text)
    new_text = text[:insert_at] + release_block + text[insert_at:]
    new_text = update_version_links(new_text, new_version, current)

    CHANGELOG.write_text(new_text, encoding="utf-8")
    write_pyproject_version(new_version)
    log(f"versioned {current} → {new_version} ({bump_kind}, session={session_id})")
    return new_version


def handle_session_start(payload: dict) -> dict:
    session_id = resolve_session_id(payload)
    baseline = git("rev-parse", "HEAD") or None
    save_state(
        session_id,
        {
            "baseline": baseline,
            "started": True,
            "finalized": False,
            "pending": empty_buckets(),
            "pending_bump": "patch",
            "composer_mode": payload.get("composer_mode"),
        },
    )
    log(f"sessionStart baseline={baseline} session={session_id}")
    return {
        "env": {
            "NOBU_SESSION_ID": session_id,
            "NOBU_SESSION_BASELINE": baseline or "",
        }
    }


def _collect_session_buckets(
    state: dict, baseline: str | None
) -> tuple[dict[str, list[str]], str, list[tuple[str, str]]]:
    paths = changed_paths_since(baseline)
    classified = classify(paths) if paths else empty_buckets()
    bump_kind = "patch"
    if paths:
        bump_kind = classified.pop("_bump", ["patch"])[0]
        session_buckets = {s: classified.get(s, []) for s in SECTION_ORDER}
    else:
        session_buckets = empty_buckets()

    pending = state.get("pending") or empty_buckets()
    # normalize pending keys
    pending_norm = {s: list(pending.get(s, [])) for s in SECTION_ORDER}
    merged = merge_buckets(pending_norm, session_buckets)
    bump_kind = stronger_bump(state.get("pending_bump") or "patch", bump_kind)
    return merged, bump_kind, paths


def handle_finalize(payload: dict, event: str) -> dict:
    session_id = resolve_session_id(payload)
    state = load_state(session_id)
    if state.get("finalized"):
        log(f"{event}: already versioned for session — skip")
        return {}

    if payload.get("is_background_agent"):
        log(f"{event}: background agent — skip")
        return {}

    if not is_git_repo():
        log("not a git repo — skip")
        return {}

    if not has_commits():
        log(
            f"{event}: repo has no commits yet — skip auto-changelog "
            "(make an initial commit first)"
        )
        return {}

    baseline = state.get("baseline") or os.environ.get("NOBU_SESSION_BASELINE") or None
    if baseline == "":
        baseline = None

    if agent_already_cut_release(baseline):
        log(
            f"{event}: agent already cut "
            f"{latest_changelog_version()} — skip auto-bump"
        )
        state["finalized"] = True
        state["pending"] = empty_buckets()
        save_state(session_id, state)
        return {}

    merged, bump_kind, paths = _collect_session_buckets(state, baseline)

    # stop + sessionEnd: always cut a SemVer entry (never [Unreleased]).
    # finalized flag ensures one version bump per conversation.
    if not any(merged[s] for s in SECTION_ORDER):
        log(f"{event}: nothing to version — skip")
        return {}

    cut_version(merged, bump_kind, session_id)
    state["finalized"] = True
    state["bump"] = bump_kind
    state["pending"] = empty_buckets()
    save_state(session_id, state)
    return {}


KNOWN_EVENTS = frozenset(
    {
        "sessionStart",
        "SessionStart",
        "sessionEnd",
        "SessionEnd",
        "stop",
        "Stop",
    }
)


def resolve_event(payload: dict) -> str:
    """Decide which hook fired. Never guess 'finalize' on ambiguous start payloads.

    Priority:
      1. stdin hook_event_name (Cursor source of truth)
      2. CURSOR_HOOK_EVENT env
      3. argv token if it is a known event name (not a file path)
      4. Heuristics: reason → sessionEnd; start-shaped payload → sessionStart
      5. Otherwise empty (skip — do NOT version)
    """
    raw = (
        payload.get("hook_event_name")
        or os.environ.get("CURSOR_HOOK_EVENT")
        or ""
    )
    if isinstance(raw, str) and raw in KNOWN_EVENTS:
        return raw

    for arg in sys.argv[1:]:
        if arg in KNOWN_EVENTS:
            return arg

    # sessionEnd uniquely carries reason (+ usually duration_ms)
    if payload.get("reason") is not None:
        return "sessionEnd"

    # sessionStart: new composer — has session/composer fields, no reason/duration
    if (
        "duration_ms" not in payload
        and payload.get("reason") is None
        and (
            payload.get("composer_mode") is not None
            or "session_id" in payload
            or "conversation_id" in payload
            or payload.get("is_background_agent") is not None
        )
    ):
        return "sessionStart"

    # stop often includes loop_count; never infer stop from silence
    if "loop_count" in payload:
        return "stop"

    return ""


def main() -> int:
    payload = read_stdin_json()
    event = resolve_event(payload)
    # Normalize casing used in branches
    event_norm = (
        event.replace("SessionStart", "sessionStart")
        .replace("SessionEnd", "sessionEnd")
        .replace("Stop", "stop")
    )

    try:
        if event_norm == "sessionStart":
            # Baseline only — NEVER cut a SemVer entry here
            out = handle_session_start(payload)
            print(json.dumps(out))
            return 0
        if event_norm == "sessionEnd":
            handle_finalize(payload, "sessionEnd")
            print("{}")
            return 0
        if event_norm == "stop":
            handle_finalize(payload, "stop")
            print("{}")
            return 0

        log(
            f"skip: unknown event (argv={sys.argv[1:]!r} "
            f"hook_event_name={payload.get('hook_event_name')!r} "
            f"keys={sorted(payload.keys())})"
        )
        print("{}")
        return 0
    except Exception as e:
        log(f"error (fail-open): {e}")
        print("{}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
