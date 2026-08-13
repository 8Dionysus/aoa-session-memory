# Session Reindex Follow-Ups Stay Session Scoped

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0081
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: hook worker, graph maintenance, queue scope
- Projection layers: session index, graph
- Guard families: bounded follow-up, maintenance lock, independent live sessions
- Posture: accepted

## Context

Completion of one session-generation reindex queued `GraphMaintenance(all)`.
With continuously active sessions, these global jobs repeatedly occupied the
single maintenance lock and delayed unrelated bounded convergence.

## Options Considered

- Keep global follow-ups and increase worker parallelism. Rejected because
  concurrent writers do not remove unnecessary global work.
- Disable automatic graph follow-ups. Rejected because session graphs would
  lose automatic convergence.
- Scope each reindex follow-up to the session whose generation changed.
  Accepted.

## Decision

A session-generation reindex always queues its graph follow-up for that session,
even when a legacy caller supplies `all`. Explicit global maintenance remains
available through graph or backlog owner routes; it is not inferred from one
session predecessor transition.

## Rationale

The invalidation source is one session generation. Keeping the derived work at
that scope preserves automatic convergence while preventing live session growth
from recreating monolithic lock holders.

## Consequences

- Positive: new session activity no longer manufactures global graph jobs.
- Positive: unrelated registry rebind and bounded graph work get safe lock
  opportunities.
- Tradeoff: broad historical debt continues through its independent backlog
  route rather than hitchhiking on a live session reindex.

## Boundaries

This does not remove explicit `all` maintenance, run graph writers concurrently,
or weaken the maintenance coordinator lock.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Use explicit backlog maintenance for genuinely global debt; keep hook and
predecessor follow-ups session scoped.

## Verification

Run predecessor handoff and hook-worker regressions, decision indexes, compile,
portable/live validation, then observe a session-scoped queued follow-up.
