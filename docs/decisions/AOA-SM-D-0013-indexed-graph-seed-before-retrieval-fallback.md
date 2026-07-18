# Indexed Graph Seed Before Retrieval Fallback

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0013
- Original date: 2026-07-17
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `DESIGN.AGENTS.md`, `docs/decisions/`
- Surface classes: query routing, graph retrieval, access contract
- Projection layers: graph anchor resolution, bounded trace search, graph timeline
- Guard families: indexed exact seed, absent-anchor latency, bounded retrieval fallback, route-selection visibility
- Posture: accepted

## Context

The durable graph store is a traversal projection with indexed node identities
and indexed edge endpoints. Its anchor resolver also searched every node
payload with leading-wildcard `LIKE` terms when exact node and route identities
were absent. That fallback duplicated the lexical retrieval layer and made the
cost of proving an absent anchor grow with the complete graph node table.

On a large live store, a typed graph-timeline query could therefore exhaust the
MCP access-plane budget before reaching the existing bounded trace/search
fallback. The same query completed through that retrieval fallback once it was
allowed to run. Exact graph identities did not need the payload scan.

## Options Considered

- Keep the payload substring scan as a graph-local fuzzy fallback. Rejected
  because absent-anchor cost scales with total graph cardinality, the query
  cannot use the node primary-key index, and MCP timeout can prevent the
  cheaper bounded fallback from running.
- Add a second full-text or alias index inside the graph store. Rejected for
  this lane because the session-memory search and trace projections already
  own bounded lexical recall. A second index would add schema, freshness,
  storage, and parity obligations without evidence that graph-local fuzzy
  lookup improves the intended relation routes.
- Resolve only indexed graph identities in the graph store, then use bounded
  trace/search retrieval to produce an evidence-bearing seed when exact graph
  identity is unavailable.

## Decision

Graph-store anchor resolution is exact and index-backed.

The direct store route may resolve:

- an exact graph node ID;
- an exact typed route key;
- an exact canonical route candidate;
- a session-scoped event node;
- or an explicitly diagnosed ambiguous raw-line reference.

It does not scan `payload_json` or perform leading-wildcard node-table search.
When indexed resolution misses, the resolver returns
`indexed_exact_miss_requires_retrieval_seed` and the graph consumer escalates
to the existing bounded trace/search route. The resulting graph packet exposes
the first route, its resolution, the selected seed route, and the fallback
reason. Exact graph anchors continue to use the direct SQLite traversal path.

MCP compaction preserves this route-selection block. MCP remains an access
plane; the archive route and its raw, segment, and session refs remain the
evidence handoff.

## Rationale

This keeps one owner for each retrieval job. The graph store resolves stable
topology identities and traverses indexed edges. Search and trace projections
perform lexical or fuzzy recall and already carry bounded budgets, freshness,
and evidence refs.

An explicit miss is safer than an unbounded resemblance scan. It prevents
absence from becoming the most expensive graph case, makes escalation
observable, and retains the option to introduce a dedicated graph alias index
later only if independent manual trials prove a relation-lane benefit that the
existing retrieval seed cannot provide.

## Consequences

- Missing and payload-only fuzzy anchors leave the direct graph-store route
  immediately and enter bounded retrieval seeding.
- Exact route identities retain the direct indexed graph path.
- Graph packets distinguish direct-store resolution from the transient
  in-memory resolution performed over bounded retrieval hits.
- A payload-only alias no longer gains graph identity merely because its text
  occurs inside an event node.
- If future trials show that a stable alias cannot be represented by canonical
  route identity or bounded retrieval, a dedicated indexed alias projection
  must be evaluated rather than restoring a full payload scan.

## Boundaries

This decision governs graph-store anchor resolution and fallback routing. It
does not prove that a retrieved event is relevant, admit a graph relation,
make a stale graph current, define causal or temporal edge semantics, authorize
graph pruning, or replace raw, segment, and session evidence. Session-specific
anchors, corpus coordinates, timings, cardinalities, and experiment history
remain in session provenance.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.AGENTS.md`
- `docs/decisions/`
- `mcp/services/aoa-session-memory-mcp/src/aoa_session_memory_mcp/core.py` in
  the stack-owned access-plane consumer

## Follow-Up Route

Continue independently seeded graph-timeline, bridge, cooccurrence, and
shortest-path trials across exact, alias, absent, collision, stale, and
multilingual anchors. Reopen the decision if bounded retrieval loses a valid
graph-only alias or if a dedicated indexed alias projection proves a better
quality, freshness, storage, and latency tradeoff.

## Verification

A gold-first live trial separated an absent typed anchor from an existing exact
tool anchor. The broken resolver performed an unindexed payload scan and the
MCP query timed out before bounded fallback; the selected route returned the
same evidence refs through bounded retrieval while the exact anchor stayed on
the direct store path. Owner-neutral regressions reject payload-only fuzzy
resolution, prove the broken query shape is absent, preserve exact and path
alias resolution, and keep route-selection metadata through MCP compaction.
Full source, portable, and configured-access-plane suites remain supporting
mechanical gates rather than substitutes for manual graph adjudication.
