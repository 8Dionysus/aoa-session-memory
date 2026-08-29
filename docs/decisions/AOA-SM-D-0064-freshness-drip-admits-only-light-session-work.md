# Freshness Drip Admits Only Light Session Work

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0064
- Original date: 2026-08-11
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: freshness, scheduling, incremental maintenance, performance
- Projection layers: route indexes, search, maintenance diagnostics
- Guard families: cost-class admission, raw-size bound, explicit handoff, bounded timer
- Posture: accepted

## Context

After global post-gates were removed, a live preferred drip selected one old
88 MiB session classified as `warm`. The global work was gone, but the single
session search transaction still consumed more than two minutes and read over
one gigabyte before operator cancellation. A repair-count limit cannot bound a
single selected unit whose own cost exceeds the freshness envelope.

## Options Considered

- Keep `auto`/heavy cost admission and rely on the 600-second budget. Rejected
  because the search budget is cooperative between sessions and cannot safely
  interrupt one transaction at an arbitrary internal point.
- Lower only the repair count. Rejected because the observed failure already
  occurred with a repair count of one.
- Add forced mid-session termination. Rejected as the primary route because it
  creates rollback work and still occupies the timer until timeout.
- Admit only `light` search candidates and cap route raw repair at 32 MiB in
  the recurring drip; hand warm/heavy work to targeted live-tail, backlog, or
  deep routes.

## Decision

The catch-up index drip passes `search-max-cost-class=light` and
`route-max-raw-mb=32` to bounded index maintenance. Query-demand priority does
not override this cost ceiling. Warm and heavy candidates remain visible as
deferred work and continue through the existing explicit target and
backlog/deep owners.

## Rationale

Freshness timers need a bound on the largest admitted unit, not only on unit
count. The existing search cost classifier already combines raw bytes, indexed
document count, and source-path count. Reusing it keeps the boundary explicit
and testable while preserving eventual convergence under profiles designed for
larger work.

## Consequences

- Positive: one historical session cannot monopolize recurring freshness.
- Positive: repeated dirty-first discovery can advance across light sessions
  while retaining warm/heavy debt as honest remaining work.
- Tradeoff: a new session that has already crossed the light boundary needs
  targeted live-tail or backlog/deep capacity before full search convergence.
- Tradeoff: the 32 MiB boundary is an owner policy and should be tuned only
  from complete live receipts, not from available RAM alone.

## Boundaries

This decision does not discard, rewrite, or downgrade warm/heavy raw evidence.
It does not remove their maintenance routes, bypass resource admission, or
claim global freshness after a light slice.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Measure consecutive timer slices over mixed light, warm, and heavy debt. Raise
the boundary only if the worst admitted session remains inside the timer
latency and resource envelope.

## Verification

Wrapper tests require both light search admission and the 32 MiB route bound in
the exact child command and report. Live proof must show a mixed-backlog slice
finishing without opening a warm/heavy session transaction.
