# Compact Route-Token Proof Replaces Payload Scan

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0080
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: graph dependency, bounded rebind, performance
- Projection layers: entity registry, graph
- Guard families: selective dependency digest, exact route-pair equality, referential integrity
- Posture: accepted

## Context

The graph already stores normalized registry route tokens and a selective
registry digest for every source. Registry rebind compatibility nevertheless
parsed every non-registry contribution payload to reconstruct the same route
pairs. On a multi-gigabyte store that proof took longer than five minutes even
after whole-graph content hashing was removed.

## Options Considered

- Keep parsing every contribution payload. Rejected because it repeats work
  already represented by guarded source indexes.
- Trust only the selective digest. Rejected because a digest alone does not
  prove materialized edge rows or endpoint existence.
- Combine recomputed selective digests with complete edge-pair, node-semantic,
  and referential equality. Accepted.

## Decision

Rebind compatibility derives expected registry edges from each graph source's
normalized route-token set, recomputes its selective digest against the current
registry, and compares the complete aggregate and contribution edge-pair sets.
It scans payloads only for registry nodes whose semantic fields must match the
current registry. Registry edges must also have existing source and target
nodes. Missing or malformed route tokens, digest drift, pair drift, dangling
edges, or registry-node semantic drift fail closed.

## Rationale

Route tokens and selective digests are maintained source-contribution indexes,
not a second authority. Combining them with complete edge-pair equality and
referential checks proves the same registry materialization boundary without
deserializing unrelated evidence payloads.

## Consequences

- Positive: compatibility cost follows source route tokens and registry edges,
  not total contribution payload bytes.
- Positive: corrupt or stale compact indexes are detected before metadata
  binding changes.
- Tradeoff: stores without complete selective digests require source refresh
  before this rebind route is admitted.

## Boundaries

This does not skip registry-node semantic comparison, admit missing endpoints,
or make generated graph indexes owner truth.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Refresh only source contributions whose route tokens, selective digests, or
registry edge pairs mismatch; then retry the compact proof.

## Verification

Run graph registry rebind regressions, decision-index checks, portable/live
validation, and a timed live dry-run plus atomic apply.
