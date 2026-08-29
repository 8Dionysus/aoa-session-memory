# Hot Status Does Not Parse Raw Projection Work

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0078
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: maintenance status, cleanup planning, session projection work, operator diagnostics
- Projection layers: raw session, stable session projection, maintenance coordinator
- Guard families: bounded hot read, explicit deep verification, fail-closed cleanup
- Posture: accepted

## Context

The ordinary hot `maintenance-status` planner called the complete cleanup
classifier. Its projection-work branch recomputed current work identities by
parsing full raw transcripts. A read-only health check could therefore consume
minutes and substantial memory while active sessions continued to grow.

## Options Considered

- Keep exact cleanup proof inside every hot status read. Rejected because a
  status surface must not hide work proportional to raw transcript volume.
- Infer obsolete projection work from timestamps or checkpoint names alone.
  Rejected because deletion safety requires comparison with current raw and
  producer identity.
- Omit only projection-work identity verification from the hot planner while
  retaining exact verification in explicit cleanup and apply routes.

## Decision

Hot maintenance planning requests cleanup status without inspecting session
projection-work identities. Graph, search, coordinator, and staged-projection
metadata remain visible. Explicit `maintenance-cleanup` keeps complete raw
identity verification by default, and apply repeats the safety proof before
removal.

## Rationale

Projection-work cleanup is not required to answer whether current search and
graph routes are usable. Omitting that one deep branch makes the operator read
bounded without weakening any deletion guard.

## Consequences

- Positive: routine status latency no longer grows with raw transcript size.
- Positive: no cleanup candidate can be admitted from incomplete metadata.
- Tradeoff: obsolete projection-work discovery is deferred to the explicit
  cleanup route instead of appearing in every hot status response.

## Boundaries

This does not skip exact identity verification during cleanup, authorize
removal from timestamps, change raw authority, or make hot status a proof of
global semantic freshness.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Use explicit `maintenance-cleanup` when projection-work recovery or removal is
the operator's target; keep ordinary status and automatic routing metadata-
bounded.

## Verification

Run the regression that makes projection-work inspection fail if hot status
calls it, cleanup safety tests, decision indexes, compile, source/export
validation, and a live hot-status timing.
