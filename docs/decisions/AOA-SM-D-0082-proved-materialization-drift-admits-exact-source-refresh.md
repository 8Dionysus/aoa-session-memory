# Proved Materialization Drift Admits Exact Source Refresh

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0082
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: graph maintenance, registry rebind, recovery
- Projection layers: graph, entity registry
- Guard families: exact source scope, complete proof, maintenance lock
- Posture: accepted

## Context

The compact registry compatibility proof can prove that a bounded set of graph
source contributions disagrees with the current entity-registry route pairs.
The ordinary graph version ledger may still call those sources clean, so an
exact maintenance request would otherwise select nothing and leave the proved
materialization drift unresolved.

## Options Considered

- Force a full graph rebuild. Rejected because the proof already identifies the
  smaller repair set and live sessions make global work needlessly expensive.
- Rewrite the ledger to manufacture version drift. Rejected because it obscures
  the actual recovery reason and changes a broader scheduling surface.
- Admit a forced refresh only for exact source keys derived from the complete
  proof. Accepted.

## Decision

An explicit graph-maintenance apply request with source keys may mark that exact
set dirty for one materialization repair even when its version state is clean.
An empty or omitted set never widens to all sources. Blocked and orphaned
sources keep their existing owner state.

## Rationale

The registry proof owns the mismatch set while graph maintenance owns source
replacement. Passing that exact set between the two surfaces repairs the read
model without changing archive authority, manufacturing ledger drift, or
returning to monolithic rebuilds.

## Consequences

- Positive: proved registry drift can converge through bounded source
  replacement.
- Positive: continuously arriving sessions do not enlarge an already computed
  repair set.
- Tradeoff: the operator or recovery route must retain the proof that produced
  the exact source keys.

## Boundaries

This does not admit an unbounded force flag, bypass blocked-source policy,
change raw/session authority, or permit concurrent graph writers. Mutation
remains transactional under the shared maintenance lock.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Compute the complete compact registry/materialization mismatch, force-refresh
only its exact source-key set, then rerun the same proof before registry rebind.

## Verification

Run the exact-scope unit regression, focused graph/registry regressions,
decision-index checks, source and portable validation, then prove the live
mismatch set empty before applying registry rebind.
