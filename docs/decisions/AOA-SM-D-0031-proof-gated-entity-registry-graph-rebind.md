# Proof-Gated Entity-Registry Graph Rebind

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0031
- Original date: 2026-07-26
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: graph indexing, entity canonicalization, freshness, atomic publication, recovery
- Projection layers: entity registry, graph nodes, graph edges, graph source contributions, graph metadata
- Guard families: dependency pinning, complete materialization, semantic digest, mutation rollback, full-rebuild fallback
- Posture: accepted

## Context

The graph pins one entity-registry generation because registry
canonicalization affects node identity and relation endpoints. A current
registry refresh therefore makes the graph stale even when all session
contributions, graph producer code, and relation policy are unchanged.

Always rebuilding every source is safe but expensive. Updating only the graph
metadata is cheap but unsafe: registry-derived node IDs, incident edges,
high-fanout aggregates, and per-source dependency identities could still
contain the old materialization.

## Options Considered

- Always perform a complete graph rebuild. Kept as the universal fallback, but
  rejected as the only route because registry-only drift can be reconciled
  without re-reading every session source.
- Rewrite only the global dependency metadata. Rejected because payload rows
  and contribution pins would still represent the older registry.
- Rewrite nodes found by a sampled alias lookup. Rejected because an omitted
  endpoint or aggregate row would create a mixed-generation graph.
- Build a complete old-to-current registry materialization plan, prove every
  affected node and edge mapping, preserve the non-registry semantic digest,
  and publish the rebind atomically.

## Decision

Registry-only graph drift may use a dedicated rebind route only after a complete
materialization proof.

The route enumerates every registry-derived graph node, every incident edge,
every affected source contribution, and every generated high-fanout aggregate.
It derives the current canonical materialization from the pinned registry and
rejects unresolved identities, endpoint collisions, duplicate destinations,
unknown generations, or incomplete source coverage.

Dry-run is the default. Apply performs all row rewrites and dependency updates
inside one transaction under the maintenance coordinator. The graph's
non-registry semantic digest is measured before and after. A mismatch rolls the
transaction back. The current registry dependency is checked before mutation
and again before commit.

A full graph rebuild may invoke the same reconciliation only when the observed
drift is registry-only and the proof passes. Otherwise it continues through
the normal full candidate build and atomic publication route.

## Rationale

Complete enumeration makes the optimization a semantic migration rather than a
metadata relabel. Preserving the non-registry digest proves that session,
episode, relation, and evidence-ref content did not change while registry
identity materialization was updated.

Atomic mutation preserves the last published graph for concurrent readers and
turns an interrupted or rejected rebind into a recoverable no-change outcome.
Keeping full rebuild as the fallback prevents the narrow route from becoming a
second graph implementation.

## Consequences

- Positive: registry-only freshness can be restored without recomputing every
  session contribution.
- Positive: graph metadata, source pins, node identities, edges, and aggregates
  advance together or not at all.
- Positive: dry-run exposes cardinality and mismatch evidence before mutation.
- Tradeoff: the proof must scan all registry-derived materialization and can be
  substantial on a large graph.
- Tradeoff: any unexplained semantic difference forces the more expensive full
  rebuild.
- Follow-up: retain cardinality, before/after digest, rollback, and post-commit
  query evidence in runtime diagnostics rather than this decision record.

## Boundaries

Rebind does not assert that registry canonicalization is semantically correct
or promote the registry above its owner sources. It cannot repair changed graph
producer logic, relation policy, task-episode sources, missing evidence refs,
or mixed unknown generations. It does not authorize inferred usage, ownership,
causality, or consequence.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Run dry-run and apply on the owner graph, verify the complete materialization
counts and unchanged non-registry digest, reobserve graph freshness, and fall
back to atomic full rebuild on any rejected proof.

## Verification

Focused regressions cover complete rebind, collision and incomplete-coverage
rejection, pre-commit dependency drift, transactional rollback,
high-fanout-aggregate refresh, unchanged non-registry digest, and automatic
full-rebuild reconciliation. Runtime proof additionally opens returned
evidence refs after post-commit freshness admission.
