# CLAUDE.md — nobu

You are in the **nobu** repo (game-agnostic MCP for chiptune/retro MIDI).

## Do this first (no questions)

1. Read [AGENTS.md](AGENTS.md) (source of truth for agents).
2. From the repo root, run:

   ```bash
   python scripts/bootstrap.py
   ```

3. Tell the user to reload MCP / restart the client if tools are not visible yet.
4. Confirm MCP server id `nobu` and tools: `start_project`, `suggest_scale_for_mood`, `add_layer`, `export_midi`.
5. When composing, follow `.claude/skills/game-music-producer/` and deliver real `.mid` files under `assets/midi/`.

Do **not** wait for the user to ask for install. Bootstrap is mandatory after clone.
