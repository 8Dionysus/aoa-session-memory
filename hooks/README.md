# AoA Session Memory hooks

This directory owns the portable Codex hook example and explains the lifecycle
boundary. The committed example contains placeholder paths; a live user or
project configuration must be rendered for the selected workspace and AoA
roots.

## Supported events

- `SessionStart` records the opening receipt and defers heavy work.
- `UserPromptSubmit` records prompt-boundary metadata without copying prompt
  text into public projections.
- `PreCompact` records the pre-compaction receipt and bounded source state.
- `PostCompact` queues sealing of the closed compaction interval.
- `Stop` may finish a small archive and defers large work.

## Runtime contract

Hooks are fail-open and return only schema-valid Codex fields. Raw transcript
unavailability creates an incident and diagnostic route instead of blocking the
agent. Foreground mirror and lock waits are bounded; heavy archive, indexing,
and graph work belongs to `hook-worker`.

Deferred jobs live under runtime diagnostics and can be recovered by the
worker, maintenance, or session sweep. Manual sync and import remain recovery
routes, not the normal compaction lifecycle.

User-level and project-level hooks may coexist. Archive generation is
idempotent for the same raw source, but duplicate lifecycle receipts can remain
visible.

Codex hook trust, user configuration placement, and optional typing bridges are
host state. They do not belong in the portable example or source readiness
claim.

Exact rendering, trust inspection, and live compaction-probe syntax belongs to
the executable CLI. The hook-focused procedures and short verification routes
live in `hooks/AGENTS.md` and the corresponding `skills/` entries.
