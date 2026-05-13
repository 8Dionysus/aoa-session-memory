# Hooks AGENTS.md

## Purpose

This directory documents and carries generated examples for Codex lifecycle
hook wiring.

Hooks preserve receipts and raw state. They must not become the heavy
understanding layer.

## Authority

- `README.md` explains the hook contract.
- `codex-hooks.user.example.json` is generated example config for selected
  roots.
- The implementation contract lives in `../scripts/aoa_session_memory.py`.

## Rules

- Hook stdout must stay schema-valid and limited to Codex protocol fields.
- Hooks must fail open and avoid blocking active Codex sessions.
- `PreCompact`, `PostCompact`, prompt, and large `Stop` paths should preserve
  and defer; deliberate indexing belongs to sync, import, or reindex.
- Do not copy absolute hook commands between machines by hand. Regenerate
  hook config from the selected roots.

## Checks

Use the narrowest applicable check:

```bash
python3 scripts/aoa_session_memory.py validate --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa
python3 scripts/aoa_session_memory.py codex-hooks-status --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa
python3 scripts/aoa_session_memory.py doctor --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa
```
