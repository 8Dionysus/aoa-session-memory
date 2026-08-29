# Runtime Owner Overlay Does Not Rescan Observed Routes

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0075
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: entity registry, automatic maintenance, search synchronization, bounded refresh
- Projection layers: entity registry, search, graph
- Guard families: observed dependency, semantic digest, generation compatibility, producer stability
- Posture: accepted

## Context

Runtime owner surfaces change more often than the archived route-term
projection. The registry already overlays those sources for read access, but
its write route rebuilt observed entities by aggregating the complete search
store. On a large archive this made a small runtime change compete with active
sessions for several gigabytes of memory and delayed the graph behind a stale
registry dependency.

## Options Considered

- Always rebuild from route terms. Rejected because it couples a bounded owner
  change to the size of the entire session archive.
- Ignore runtime drift when the graph epoch is unchanged. Rejected because new
  or retired runtime identities are real registry content revisions.
- Persist the runtime overlay only after proving the observed dependency and
  existing snapshot unchanged, then incrementally synchronize registry search
  documents.

## Decision

The atomic entity-registry/search sync uses a runtime-only fast path when its
verified persisted snapshot has exactly one stale cause: a changed runtime
owner fingerprint. The path preserves the exact observed-source dependency,
recomputes runtime entries, fingerprints, counts, and semantic digest, writes
the registry atomically, and updates only changed registry search documents.
Any observed dependency drift, generation mismatch, unverified semantic
digest, requested source or history-policy change, or producer instability
falls back to the complete builder.

## Rationale

Archive growth no longer determines the cost of a routine runtime-owner
refresh. The strict preconditions retain the distinction between owner truth,
observed navigation, and graph dependency content instead of declaring an old
observed projection current by convenience.

## Consequences

- Positive: routine registry refresh is proportional to registry/runtime size,
  not the complete search route-term corpus.
- Positive: graph maintenance can resume after a bounded registry refresh and
  its existing proof-gated dependency rebind.
- Positive: search updates only added, changed, or retired registry documents.
- Tradeoff: actual observed-route drift still requires the heavier complete
  aggregation route.

## Boundaries

This does not make generated registry entries owner truth, skip search
synchronization, weaken graph dependency pinning, or authorize reuse of an
unverified observed projection.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Keep the complete builder as the fail-closed route for observed dependency or
policy changes, and use the graph registry rebind only after the refreshed
dependency is current.

## Verification

Run focused runtime-overlay, registry/search synchronization, graph dependency,
decision-index, compile, source validation, portable export validation, and a
live bounded resource probe that proves no archived route-term rescan occurs.
