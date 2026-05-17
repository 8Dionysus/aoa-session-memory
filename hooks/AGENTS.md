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
- `SessionStart`, prompt, `PreCompact`, `PostCompact`, and large `Stop` paths
  should preserve and queue. Foreground hooks stay light, but `PostCompact`
  must route automatic interval sealing to `hook-worker`.
- Lifecycle hooks may use a bounded raw mirror for small transcripts, but they
  must defer large transcripts and registry lock contention instead of waiting.
- Deferred lifecycle work should be queued for `hook-worker` so collection
  remains automatic without running heavy sync/index work inside Codex's hook
  timeout window. Manual sync/import/reindex are recovery and rebuild paths,
  not the normal PostCompact archive path.
- Do not copy absolute hook commands between machines by hand. Regenerate
  hook config from the selected roots.

## Checks

Use the narrowest applicable check:

```bash
python3 scripts/aoa_session_memory.py validate --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa
python3 scripts/aoa_session_memory.py codex-hooks-status --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa
python3 scripts/aoa_session_memory.py doctor --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa
```
