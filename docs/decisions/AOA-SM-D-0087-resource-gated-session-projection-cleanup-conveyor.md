# Resource-Gated Session Projection Cleanup Conveyor

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0087
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: maintenance orchestration, generated storage, cleanup scheduling, operator controls
- Projection layers: session projection stage, resumable projection work, raw authority
- Guard families: bounded verification, inactive producer, inactive lease, generation incompatibility, quiet-age guard
- Posture: accepted

## Context

Interrupted builders can leave PID-owned pre-journal projection stages, while
producer-generation changes can leave older resumable projection-work
directories. Exact cleanup was already safe, but ordinary hot planning
intentionally omitted raw identity work and the apply CLI omitted
projection-work inspection. Repeated maintenance therefore produced generated
debris faster than an operator-only cleanup route consumed it.

## Options Considered

- Restore complete cleanup classification to every hot status read. Rejected
  because status latency and memory would again scale with large raw sessions.
- Delete stages or work by age, name, or missing PID alone. Rejected because
  none proves stronger raw authority or protects a current resumable build.
- Keep cleanup manual. Rejected because a safe but unconsumed recovery route
  permits unbounded generated-storage growth.
- Expose separate bounded stage and explicit resource-gated projection-work
  controls, then let the host scheduler run them at different cadences.

## Decision

`maintenance-cleanup --apply` remains a bounded operational drip. A scheduled
owner may set `--session-stage-verification-limit` to a small positive bound so
one unresolved candidate cannot indefinitely starve later verified stages.
Projection-work inspection during apply requires the explicit
`--inspect-session-projection-work` flag and belongs behind resource admission
at a slower cadence.

Both routes retain the existing maintenance lease and repeat their deletion
proof immediately before mutation. The stage route requires an absent encoded
producer and verified stronger raw authority. The projection-work route
requires current raw identity, an inactive per-session lease, incompatible work
identity, matching directory/checkpoint shape, and the quiet-age guard.
Scheduled invocations may map only `deferred_active_writer` to a successful
timer tick; the result remains an explicit no-mutation deferral and is retried
at the next cadence.

## Rationale

Separate cadences preserve cheap hot observation while making storage recovery
automatic. Small bounded stage verification drains frequent crash debris.
Resource-gated exact work classification handles rarer producer-generation
turnover without placing full transcript parsing on the request or status path.

## Consequences

- Positive: safe generated debris no longer depends on a human noticing disk
  pressure.
- Positive: one blocked stage need not prevent later safe candidates from
  advancing when the scheduled verification bound is greater than one.
- Tradeoff: exact projection-work cleanup remains comparatively expensive and
  requires an admitted slower scheduler.
- Follow-up: runtime health should report cleanup age, remaining bytes, last
  action counts, and blocked candidates without claiming semantic freshness.

## Boundaries

This decision does not authorize deletion of raw sessions, preserved captures,
published projections, current resumable work, or live index stores. It does
not make timer success a freshness claim and does not prescribe one portable
systemd layout; host scheduling remains an explicit installation concern.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Use the owner CLI from an admitted host scheduler, retain compact reports under
runtime diagnostics, and use explicit `maintenance-cleanup` dry-run for any
blocked or legacy-unowned candidate.

## Verification

Run focused parser and cleanup safety regressions, decision-index generation,
compile, source validation, portable export/audit, and live dry-runs. Runtime
proof additionally requires one bounded stage cycle and one resource-gated
projection-work cycle with before/after storage and unchanged raw/last-good
evidence.
