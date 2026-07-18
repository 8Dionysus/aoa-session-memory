# Semantic Projection Generation Identity

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0002
- Original date: 2026-07-14
- Owner surfaces: `scripts/aoa_session_memory.py`, `DESIGN.AGENTS.md`, `PIPELINE.md`
- Surface classes: freshness contract, semantic indexing, entity routing, queue recovery
- Projection layers: episode semantic, episode entity state, dense vectors, maintenance queue
- Guard families: generation identity, stale abstention, raw evidence fallback, retry recovery
- Posture: accepted

## Context

A gold-first live retrieval case exposed a freshness failure: an episode
projection generated under an older route-signal classifier could still be
reported as current after classifier behavior changed. Because the schema,
source fingerprint, and row count remained compatible, a stale typed relation
was allowed into the answer path.

The failure is broader than one query. Semantic classification can change
without changing storage shape or source cardinality. Dense vectors, typed
entity state, and exhausted retry entries can all remain internally consistent
with the old classifier while being invalid for the current consumer.

## Options Considered

- Invalidate only when the database schema changes. Rejected because semantic
  producer behavior can change without a schema migration.
- Infer freshness from source fingerprint and row count. Rejected because old
  and current projections may contain the same sources and number of rows.
- Serve older semantic rows with a freshness warning. Rejected because known
  invalid relations can still contaminate accepted answers.
- Persist the semantic producer/classifier epoch in every dependent projection,
  exclude mismatched rows from answer candidates, abstain explicitly, and
  requeue work under the new epoch.

## Decision

Projection freshness uses a generation identity, not schema compatibility
alone.

Episode semantic state, typed entity state, dense vectors, and their persistent
queue carry the route-signal classifier epoch that generated them. A row is an
answer candidate only when its projection version, source fingerprint mode,
dependency state, and classifier epoch match the current consumer. Missing or
older epochs make the projection stale and produce
`insufficient_projection_coverage` rather than a stale semantic answer.

Changing the classifier epoch dirties dependent projections and resets retry
work that was exhausted under the superseded epoch. Raw, segment, session, and
exact-evidence routes remain available while derived projections catch up.

## Rationale

Generation identity binds semantic meaning to the code that produced it. This
prevents a successful timer, stable row count, or unchanged source fingerprint
from masquerading as semantic freshness. Abstention is safer than serving a
relation already known to have been classified under obsolete rules, while the
raw and exact routes preserve evidence access during recomputation.

## Consequences

- Classifier changes cause bounded recomputation even when source data did not
  change.
- Search may temporarily return insufficient coverage instead of a semantic
  result.
- Queue entries exhausted under an older epoch become eligible again.
- Dense projection freshness is tied to the semantic source epoch rather than
  document count alone.
- Operators and MCP consumers must distinguish stale projection coverage from
  absence of evidence.

## Boundaries

This decision governs derived projection admissibility. It does not make
classifier output reviewed truth, prove semantic quality, or prove that the
automatic catch-up loop has completed. Runtime currentness remains a live
maintenance and manual-evidence question. Exact and raw evidence remain
stronger than the generated semantic state.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.AGENTS.md`
- `PIPELINE.md`

## Follow-Up Route

Verify automatic schema/epoch catch-up on live archived sessions, then export
and validate the standalone bundle and configured read-only MCP access plane.

## Verification

The observed broken case was reproduced before implementation and repeated
afterward. Owner-neutral regression cases cover stale semantic/entity
exclusion, explicit insufficiency, queue reset, and dense epoch invalidation.
Live automatic catch-up, source/bundle parity, and MCP transport proof remain
separate runtime gates.
