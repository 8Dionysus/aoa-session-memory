# Observed Route Refresh Is One Covering Pass

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0076
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: entity registry, search storage, query plan, automatic maintenance
- Projection layers: entity registry, search
- Guard families: exact aggregation, bounded ranking, resource admission
- Posture: accepted

## Context

When observed route terms genuinely changed, the complete registry fallback
ran one aggregation for every entity layer. Each layer started from route
terms and performed many random lookups into the wide document table. Archive
growth therefore multiplied physical reads and turned a necessary exact
refresh into a long resource-contention window.

## Options Considered

- Keep per-layer aggregation. Rejected because its random document access
  repeats the expensive side of the join.
- Bound every layer and discard the tail. Rejected because a complete registry
  dependency must not silently omit observed identities.
- Aggregate every admitted layer in one covering-index-led pass and apply an
  optional per-layer window rank only after exact grouping.

## Decision

The archived route-term fallback scans a covering document index once, joins
document routes and route terms in that order, and groups by layer, key, and
route signal in one statement. The complete route returns every group. The
bounded diagnostic route applies `ROW_NUMBER` within each layer after grouping
and preserves its existing per-layer limit contract. Cursor rows merge into
canonical entity identities immediately, so aliases combine without a second
full intermediate list.

## Rationale

The plan keeps exact counts, distinct session counts, latest dates, and all
admitted identities while replacing repeated random access to wide document
rows with one compact sequential source pass.

## Consequences

- Positive: complete refresh cost is no longer multiplied by entity-layer
  count.
- Positive: the covering index is reusable and small relative to stored
  document bodies and payloads.
- Positive: peak Python memory follows canonical registry size rather than raw
  route-signal row count.
- Positive: bounded and complete output semantics remain explicit.
- Tradeoff: the first upgraded search store must build the covering index once.

## Boundaries

This does not turn route terms into owner truth, remove exact aggregation, or
replace future incremental operational rollups. Genuine route drift still
requires a complete dependency calculation when no current rollup exists.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Prefer a current operational route rollup when available; retain this exact
one-pass query as the monolith fallback and bootstrap route.

## Verification

Run complete and bounded route-term fixtures, registry/search synchronization,
decision-index, compile, source and portable validation, then calibrate the
live wall time, physical reads, and peak memory under resource admission.
