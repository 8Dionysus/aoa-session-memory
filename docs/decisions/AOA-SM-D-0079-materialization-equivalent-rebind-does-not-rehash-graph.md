# Materialization-Equivalent Rebind Does Not Rehash the Graph

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0079
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: graph dependency, generation transition, bounded rebind, performance
- Projection layers: entity registry, graph
- Guard families: complete materialization equality, exact predecessor, transaction scope, post-commit proof
- Posture: accepted

## Context

When a changed registry entry set affected only a bounded set of graph sources,
those sources could be refreshed incrementally. The final rebind nevertheless
hashed every graph table before and after a transaction that changed only
generation, dependency, and selective-registry metadata. On the live store the
redundant digest pass required several gigabytes of memory.

## Options Considered

- Run a full graph rebuild. Rejected because the changed mapping sources are
  already identified and incrementally replaceable.
- Keep whole-graph digests around every metadata-only transaction. Rejected
  because exact materialization equality and constrained SQL already prove the
  query-bearing graph rows are unchanged.
- Admit the metadata rebind only after complete registry node semantics and
  aggregate/contribution route-pair equality, then repeat that proof after the
  transaction.

## Decision

After complete graph registry materialization equality, an entity-registry
generation-only transition may advance graph bindings without whole-graph
content or semantic digest passes. The rebind still requires exact compatible
generation identities, valid source dependency bindings, current static
versions, producer stability, one transaction, and the same complete mapping
proof after commit. Any materialization mismatch retains bounded source refresh
or the existing complete refresh route.

## Rationale

The admitted transaction does not rewrite nodes, edges, or contribution
payloads. Rehashing those rows cannot strengthen the already complete mapping
proof or the SQL mutation boundary.

## Consequences

- Positive: final convergence follows registry-bearing source count rather
  than total graph payload bytes.
- Positive: bounded source refresh composes with a cheap final metadata rebind.
- Tradeoff: the complete mapping proof still scans registry-relevant node
  contributions; it is intentionally stronger than fingerprint-only routing.

## Boundaries

This does not admit unresolved mapping drift, skip post-commit proof, change
non-registry graph content, or make generated graph data owner truth.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Refresh the exact mismatching graph sources first. Use complete registry
materialization refresh only when the mismatch set cannot be bounded safely.

## Verification

Run generation-transition and materialization-equivalence regressions,
decision indexes, compile, source/export validation, and live targeted refresh
plus final rebind timing.
