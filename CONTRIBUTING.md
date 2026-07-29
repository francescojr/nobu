# Contributing to nobu

Thanks for helping make game audio tooling better.

## English

### How to contribute

1. Fork the repo and create a branch from `main`.
2. Keep changes focused (one feature or fix per PR).
3. Match existing style: clear docstrings, no unrelated refactors.
4. Update docs if you change MCP tools, folder conventions, or CLI flags.
5. Open a pull request describing **why** the change helps users.

### Local setup

```bash
python scripts/bootstrap.py
# or manually:
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python nobu_mcp.py
```

### Conventions

- MIDI output: `assets/midi/`
- SoundFonts: `assets/soundfonts/` (do **not** commit `.sf2` files)
- Rendered audio: `output/audio/{project}/wav/` and `.../ogg/`
- MCP server id: `nobu`
- Tool API language: **English**
- Do not add game-specific data to the MCP or skill — keep nobu game-agnostic

### Versioning & changelog

We use [Semantic Versioning](https://semver.org/) and [Keep a Changelog](https://keepachangelog.com/) **categories**.

- **No `[Unreleased]`** — every meaningful session cuts `## [X.Y.Z] — YYYY-MM-DD`
- Bump `version` in `pyproject.toml` in lockstep (hook does this automatically)
- Categories: **Added**, **Changed**, **Deprecated**, **Removed**, **Fixed**, **Security**
- Keep release links at the bottom of [CHANGELOG.md](CHANGELOG.md)
- Tag releases as `vX.Y.Z` (e.g. `v0.1.1`)

#### Cursor session hook (automatic)

Project hooks in [`.cursor/hooks.json`](.cursor/hooks.json) run:

| Event | Behavior |
|---|---|
| `sessionStart` | Saves git baseline for the conversation |
| `stop` / `sessionEnd` | Classifies diffs, bumps SemVer (`patch` / `minor` / `major`), prepends `## [X.Y.Z]` (once per session) |

Script: [`.cursor/hooks/update_changelog_session.py`](.cursor/hooks/update_changelog_session.py).  
Enable Hooks in Cursor settings if inactive. Check **Output → Hooks** if versions never bump.

If the agent already wrote a matching top `CHANGELOG` entry + `pyproject.toml` version, the hook **skips** (no second junk patch). Edit noisy auto bullets by hand when needed.

**Config gotcha:** in `.cursor/hooks.json`, `loop_limit` must be a **positive integer** or `null` (no limit). `0` is invalid and Cursor rejects the **entire** project hooks file (nothing runs).

**Note:** auto-versioning stays idle until the repo has at least one git commit.

### MCP configs after bootstrap

`scripts/bootstrap.py` rewrites machine-local configs with **absolute venv paths**.
Those files are **gitignored** — `git add -A` will not stage them:

| Generated (local only) | Portable template in git |
|---|---|
| `.cursor/mcp.json`, `.mcp.json` | `.mcp.example.json` |
| `.kilo/kilo.jsonc` | `.kilo/kilo.example.jsonc` |

Clones get working MCP/Kilo after `python scripts/bootstrap.py` (mandatory; see AGENTS.md).

### Code of conduct

By participating, you agree to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

---

## Português

### Como contribuir

1. Faça um fork e crie uma branch a partir de `main`.
2. Mantenha PRs focadas (uma feature ou correção por PR).
3. Siga o estilo existente: docstrings claras, sem refactors não relacionados.
4. Atualize a documentação se mudar tools MCP, pastas ou flags de CLI.
5. Abra um pull request explicando **por que** a mudança ajuda.

### Setup local

```bash
python scripts/bootstrap.py
```


### Convenções

- MIDI: `assets/midi/`
- SoundFonts: `assets/soundfonts/` (**não** commitar `.sf2`)
- Áudio renderizado: `output/audio/{project}/wav/` e `.../ogg/`
- Server id MCP: `nobu`
- API das tools: **inglês**
- Não adicione dados de jogo específico no MCP ou na skill — nobu é game-agnostic

### Versionamento e changelog

Usamos [Semantic Versioning](https://semver.org/) **sem** seção `[Unreleased]`. Cada sessão com mudanças gera `## [X.Y.Z]` automaticamente (hook) e atualiza `pyproject.toml`. Tag manual: `vX.Y.Z`.
