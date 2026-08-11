# Bounded Freshness Defers Global Derivatives

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0063
- Original date: 2026-08-11
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: freshness, incremental maintenance, performance, scheduling
- Projection layers: search, search catalog, entity registry, maintenance diagnostics
- Guard families: bounded scope, fail-closed routing, explicit handoff, deadline ownership
- Posture: accepted

## Context

The preferred bounded index drip made its selected session searchable early,
then spent almost six minutes in global post-gates. Profiling attributed about
291 seconds to rebuilding the search catalog across archived projections and
about 49 seconds to global entity-registry synchronization. The useful selected
session publication had already completed. Bounded selection alone therefore
did not produce bounded end-to-end latency.

## Options Considered

- Keep global post-gates in every bounded slice. Rejected because archive
  growth determines freshness latency and the declared budget cannot bound a
  phase that starts a global semantic scan.
- Skip the post-gates without recording state. Rejected because shard readers
  could trust stale topology and maintenance could overclaim completion.
- Incrementally patch every global derivative in the same change. Deferred
  because catalog and registry have different complete-source and retirement
  contracts; coupling both implementations back into the freshness process
  would preserve the same ownership error.
- Publish the selected monolith update, persist global derivatives as stale,
  fail shard routing closed to the monolith, and hand global convergence to
  backlog/deep or explicit owner routes.

## Decision

A bounded-discovery maintenance cycle owns selected route, exact/lexical
search, and selected post-write coherence only. Its search update disables the
global catalog rebuild and entity-registry synchronization. After the monolith
transaction commits, it marks the generated search catalog stale with the
affected session IDs and an exact global refresh route.

The catch-up demand key advances to a new resource epoch so the bounded route
does not inherit peak learning from the removed global post-gates. A new owner
floor is admitted only from live observations of this execution shape.

Shard fan-out and structured multi-class shard readers require both compatible
catalog generation and `status=current`; otherwise they fall back to the
monolith. Bounded maintenance reports its final snapshot as selected scope and
states that catalog and registry truth remain unresolved. Non-bounded manual,
backlog, and deep routes retain the existing complete global gates.

## Rationale

Immediate evidence availability and global navigation convergence are
different obligations. The monolith update is transactional and sufficient to
make the selected session queryable. Persisting catalog staleness and forcing a
monolith fallback preserves honest routing while removing archive-wide work
from the recurring latency boundary. The complete-source catalog and registry
contracts remain intact under their global owners.

## Consequences

- Positive: bounded freshness latency no longer scales with the complete
  catalog or entity-registry source set.
- Positive: newly indexed sessions remain available even to callers that ask
  for shards, because stale topology fails closed to the current monolith.
- Positive: resource admission learns the scoped route independently from the
  obsolete archive-wide execution shape.
- Tradeoff: shard acceleration and registry navigation may remain stale until
  backlog, deep, or an explicit owner route converges them.
- Tradeoff: bounded completion must not be read as global derivative
  completion.

## Boundaries

This decision does not weaken raw evidence authority, transactionality,
complete-source rebuild rules, source-set retirement, resource admission, the
maintenance lock, or global validation. It does not claim that a selected
snapshot proves archive-wide freshness.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Measure two consecutive live timer slices. Evolve catalog and registry
incremental consumers independently only if their owner-complete retirement
and identity contracts can be preserved.

## Verification

Tests forbid bounded search and bounded planning from calling the global
catalog builder or entity-registry status route, require the catalog to be
marked stale, require shard search to fall back to the current monolith, and
retain full-route catalog and registry tests. Live receipts must show selected
publication and process completion within the bounded timer envelope.
