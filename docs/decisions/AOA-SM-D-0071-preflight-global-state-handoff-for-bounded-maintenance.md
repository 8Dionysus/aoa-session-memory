# Preflight Global State Handoff for Bounded Maintenance

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0071
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: incremental maintenance, entity registry, graph readiness, scheduling
- Projection layers: entity registry, search index, graph dependency binding
- Guard families: bounded discovery, preflight evidence, derivative ownership, explicit deferral
- Posture: accepted

## Context

Backlog maintenance deliberately selects a bounded session set and does not
rescan global derivatives inside that planner. The outer auto-maintenance
coordinator already observes global entity-registry freshness before selecting
the batch, but previously discarded that state at the bounded planning
boundary. The planner therefore reported the registry as deferred even when
the preflight proved it stale, omitted the registry refresh action, and left
the graph registry dependency circuit permanently open across otherwise
successful bounded cycles.

A bounded search update also emits an entity-registry document count while
explicitly deferring global derivatives. Treating the presence of that count
as proof that the registry refresh was covered can suppress the dedicated
owner action without materializing it.

## Options Considered

- Rescan global derivative state inside every bounded planner. Rejected because
  it defeats the bounded discovery contract and repeats work already performed
  by the coordinator.
- Ignore registry staleness until an unbounded manual maintenance run. Rejected
  because automatic graph convergence would depend on operator intervention.
- Treat any search result count as registry coverage. Rejected because bounded
  search explicitly declares global derivatives deferred.
- Hand the coordinator's observed registry state to the owning profiles and
  require explicit non-deferred evidence before search may cover the refresh.

## Decision

The auto-maintenance coordinator may pass its already-observed preflight
entity-registry state to bounded index planning only for the `backlog` and
`deep` owner profiles. The bounded planner does not reread global state. When
that supplied state proves maintenance is needed, it schedules the existing
atomic `entity-registry-search-sync` action.

A completed search action covers the registry refresh only when the action is
verified successful, exposes registry document accounting, and neither its
global derivative result nor its entity-registry derivative declares a
deferred state. Explicit bounded or budget deferral keeps the dedicated
registry action executable.

## Rationale

This preserves bounded discovery while carrying evidence across the layer
that already owns it. It restores an automatic path from owner-source changes
to registry refresh, guarded graph dependency rebind, and graph drain without
promoting a partial search count into global completion proof.

## Consequences

- Positive: backlog and deep cycles can retire registry staleness without an
  unbounded rediscovery pass.
- Positive: graph registry circuits can become rebindable through automatic
  owner maintenance rather than permanent manual intervention.
- Positive: bounded search remains honest about deferred global derivatives.
- Tradeoff: a preflight snapshot can become stale during a long cycle; the
  existing post-maintenance probe and successor cycle remain authoritative.

## Boundaries

The handoff does not make selected session records globally complete, bypass
the maintenance lock or resource admission, apply to hot/catchup ownership, or
declare the graph current. Raw sessions and current owner sources remain
stronger than generated registry, search, and graph state.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Observe an admitted backlog cycle with stale preflight registry state, verify
that `refresh_entity_registry` is applied or honestly deferred by budget, then
run guarded graph registry rebind and bounded graph maintenance. Preserve the
persistent backlog successor until all remaining owner work is proven current.

## Verification

Focused tests cover bounded planning without a global reread, supplied
preflight state admission, and refusal to treat deferred search derivatives as
registry coverage. Run decision-index regeneration/check, `py_compile`,
focused maintenance and retry tests, source validation, live source parity,
and graph circuit evidence before local landing.
