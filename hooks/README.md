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
agent. Generated hook configurations enter through the small standard-library
`scripts/aoa_session_hook.py` adapter. It atomically stores the exact private
stdin bytes under `diagnostics/hook-ingress/` before returning to Codex; it does
not import the projection engine in the foreground process. Queue files and
directories are owner-private.

The ingress digest coalesces byte-identical user- and project-level signals
while retaining their signal count and first/last observation times. The
single-flight background dispatcher replays the envelope through the ordinary
owner handler, verifies byte count and digest, writes the normal hook receipt,
and then processes bounded follow-up jobs. Lifecycle events wake the dispatcher
immediately. The persistent retry dispatcher also drains remaining ingress, so
a maintenance-lock collision does not strand capture. Foreground mirror and
lock waits are bounded; heavy archive, indexing, and graph work belongs to the
worker path.

`AOA_SESSION_MEMORY_HOOK_FAST_INGRESS=0` is the exact synchronous rollback.
If durable enqueue itself fails, the adapter tries that owner route before it
fails open. Queue success means capture is durable and pending; it does not
claim that an archive or projection is already current.

Deferred jobs live under runtime diagnostics and can be recovered by the
worker, maintenance, or session sweep. Manual sync and import remain recovery
routes, not the normal compaction lifecycle.

User-level and project-level hooks may coexist. Byte-identical ingress is
coalesced without losing its signal count. Different event bytes remain
separate, and archive generation remains idempotent for the same raw source.

Codex hook trust, user configuration placement, and optional typing bridges are
host state. They do not belong in the portable example or source readiness
claim.

Exact rendering, trust inspection, and live compaction-probe syntax belongs to
the executable CLI. The hook-focused procedures and short verification routes
live in `hooks/AGENTS.md` and the corresponding `skills/` entries.
