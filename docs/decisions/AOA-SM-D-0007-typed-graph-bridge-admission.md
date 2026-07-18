# Typed Graph Bridge Admission

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0007
- Original date: 2026-07-16
- Owner surfaces: `scripts/aoa_session_memory.py`, `DESIGN.AGENTS.md`, `READINESS.md`, `docs/decisions/`
- Surface classes: query routing, graph semantics, evidence reading
- Projection layers: typed graph bridge, shortest path, route-signal rollups
- Guard families: exact anchor resolution, discovery-only edge rejection, typed relation admission, candidate preservation
- Posture: accepted

## Context

A bounded shortest path can be mechanically real in the generated graph while
still being semantically insufficient for a relationship claim. Route-signal
mentions, session or segment rollups, entity mentions, and cooccurrence can
join two exact anchors through a generic session, segment, event, or namespace
node. That path is useful for discovery, but it does not show that either
entity caused, produced, verified, owned, depended on, resolved, superseded,
or otherwise related to the other.

Returning such a path as `path_found=true` collapses the existing owner law
that mention and cooccurrence are hints rather than relations. It also lets a
shorter high-fanout route outrank a missing but necessary typed edge.

## Options Considered

- Accept every bounded shortest path between exactly resolved anchors and rely
  on consumers to inspect its edge types. Rejected because the packet-level
  success claim remains stronger than the evidence and is easy to misuse.
- Remove mention and route-rollup edges from the graph immediately. Rejected
  because those projections still support discovery and because pruning is
  separately gated on replacement quality, provenance, freshness,
  cardinality, storage, and rollback proof.
- Penalize generic or high-degree nodes but continue accepting the winning
  path. Rejected because ranking can reduce noise without changing the
  semantics of a discovery-only edge.
- Treat the shortest path as a candidate, then admit a typed bridge only when
  the path contains no discovery-only edge and includes at least one
  non-structural relation edge.

## Decision

Separate graph path discovery from typed bridge admission.

The bounded shortest-path calculation may find and retain a candidate path.
For `graph-bridge`, that candidate becomes an accepted relation path only when:

- typed source and target anchors resolve exactly;
- no edge in the path is a mention, cooccurrence, entity-mention, segment
  route-rollup, or session route-rollup edge; and
- at least one edge is relation-bearing rather than only structural
  containment such as `has_segment` or `has_event`.

A rejected candidate remains visible under bounded candidate context with its
edge types, nodes, refs, admission status, and reason. It does not populate the
accepted bridge, does not set `path_found=true`, and does not contribute path
refs to the accepted evidence set. Independent source and target usage refs may
still be returned as navigation, but they do not manufacture a relation.

The raw shortest-path route remains a navigation surface. Typed bridge
admission is the consumer boundary that decides whether a candidate path can
answer a relationship question.

## Rationale

This route preserves useful discovery evidence without presenting graph
connectivity as semantic truth. A boolean gate on edge meaning is more robust
than a score penalty: high-degree noise cannot become an accepted relation
merely because no better path exists.

Keeping the rejected path bounded and auditable supports return review and
future graph redesign. Requiring an actual relation-bearing edge also makes
missing typed projections visible as abstention pressure instead of hiding the
gap behind session membership.

## Consequences

- Typed graph bridges abstain when the current store has only mention,
  cooccurrence, rollup, or containment connectivity.
- Consumers can still inspect the rejected discovery path and follow its
  evidence refs without confusing it with an accepted relation.
- Bridge recall may decrease until entity-use, causal, temporal, owner, and
  dependency relations are materialized with evidence-backed edge types.
- Graph pruning and route-signal replacement remain separate decisions and
  retain their existing proof gates.
- A future relation edge must be classified deliberately; adding a new edge
  type cannot silently gain authority through a generic shortest-path score.

## Boundaries

This decision governs typed `graph-bridge` admission. It does not make graph
paths reviewed truth, define every future relation type, prove causality from
adjacency, authorize graph pruning, change raw or segment authority, or make a
stale graph current. Session-specific paths, gold spans, seeds, counts, and
latencies remain in session provenance.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.AGENTS.md`
- `READINESS.md`

## Follow-Up Route

Use typed usage chains and raw refs to design evidence-backed entity-use,
causal, temporal, authority, and dependency relations. Reopen this decision if
manual positive cases show that a discovery edge is indispensable to a valid
typed relation; do not weaken the gate without an owner-neutral A/B case and
preserved provenance.

## Verification

A gold-first archived-session trial first exposed an accepted bridge composed
only of route-signal rollups. An owner-neutral regression reproduces two exact
tool anchors joined solely through a session rollup and proves that the broken
behavior returned `path_found=true`. After the change, the accepted bridge is
empty, the candidate path remains auditable, and a direct typed dependency is
still admitted. The original live query is repeated against the current graph
and its usage routes; private coordinates and experiment details remain in
session provenance.
