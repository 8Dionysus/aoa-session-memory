# Neutral Derived Route-Signal Graph Relations

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0033
- Original date: 2026-07-26
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: graph semantics, relation taxonomy, evidence provenance, migration
- Projection layers: event route signals, registered-entity signals, typed graph, graph quality
- Guard families: derived-anchor admission, usage-state separation, literal-mention separation, generation compatibility
- Posture: accepted

## Context

The graph materializes classifier and registry route signals so an exact skill,
tool, goal, command, or other operational anchor can reach source events
without a payload-wide fuzzy scan. Those signals are derived from structured
event fields, classifiers, registries, and bounded lexical rules.

The original edge names described the same links as mentions. That name was
false for signals such as an operation-state classifier: an event can be
classified under a goal-completion route without literally mentioning that
route label. It also made a discovery edge look closer to observed use than
its evidence permits. Metadata and downstream admission gates limited the
claim, but the relation identity itself remained misleading.

## Options Considered

- Keep the existing mention-shaped names and rely on metadata to explain their
  weaker meaning. Rejected because relation identity is a public retrieval
  contract and must not make a false observation before a consumer reads
  optional metadata.
- Remove event route-signal edges entirely. Rejected because exact graph
  navigation still benefits from them and no replacement proof currently
  preserves the same bounded recall and evidence refs.
- Promote classifier signals into usage, completion, ownership, causality, or
  consequence relations. Rejected because a derived route label does not prove
  any of those observed states.
- Represent the links as neutral, directed `derived_anchor` relations whose
  payload preserves signal source, confidence, evidence refs, and an explicit
  claim boundary.

## Decision

Materialize event route signals as neutral derived anchors.

The graph relation names are:

- `event_has_route_signal` for a derived event-to-route signal; and
- `event_has_registered_entity_signal` for the registry-normalized form of
  that signal.

Both belong to the `derived_anchor` relation family. They are directed,
versioned, evidence-backed navigation links. Their edge payload records the
signal source and confidence when available and states that the edge does not
prove literal mention, selection, loading, reading, procedure observation,
invocation, completion, verification, consequence, causality, or ownership.

Literal mention remains a source-reading claim. Usage and consequence remain
admissible only through their dedicated structured state and correlation
contracts. Cooccurrence and rollup consumers may use the neutral edges for
bounded navigation but may not promote them to a typed bridge relation.

This is an incompatible generated-relation transition. The graph relation
contract advances to version 4 and the event route-signal materialization
policy advances to version 5. Stores built under the earlier relation identity
are stale and require a full atomic graph rebuild; old and new relation names
must not be mixed in one admitted generation.

## Rationale

The new names state only what the projection actually knows: the event has a
derived navigation signal. This preserves exact retrieval value while keeping
observed language, operational state, and causal consequence with their
stronger source-aware routes.

A generation-breaking migration is preferable to a silent semantic rewrite.
Readers can reject incompatible rows before candidate admission, and a
deterministic rebuild can reproduce the new graph from preserved session and
owner sources without altering raw evidence.

## Consequences

- Positive: graph packets no longer call classifier-derived operational state
  a literal mention.
- Positive: answer admission and typed bridge logic can distinguish
  `derived_anchor` from mention, usage, status, result, and consequence
  families.
- Positive: signal provenance and confidence remain visible for review.
- Tradeoff: every graph contribution must be rebuilt under relation contract
  version 4 before the graph can report current.
- Tradeoff: consumers that inspect relation names or family counts must adopt
  the new contract explicitly.
- Follow-up: retain manual positive and negative review across literal
  mentions, classifier-only route signals, correlated actions/results, and
  registered-entity normalization.

## Boundaries

This decision does not declare every route classifier correct, turn graph
navigation into reviewed truth, prove a skill or tool was used, authorize
pruning, or make a stale store current. It does not replace raw, segment,
session, receipt, or external owner evidence. Ordinary timeline order remains
outside the graph unless a separately justified relation improves a query
lane.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Perform a full atomic graph rebuild, verify that no legacy relation rows remain,
repeat bounded graph and usage evaluations against independently selected raw
evidence, then check source, portable, skill, and MCP packet parity.

## Verification

Owner-neutral regressions require both new relation names, the
`derived_anchor` family, signal provenance, and explicit negative claim
boundaries. They also require route-signal edges to remain outside usage and
consequence admission. A full source suite, deterministic double graph
rebuild, randomized graph-quality audit, manual raw-ref review, portable
export, and read-only access-plane parity provide the supporting mechanical
and runtime proof.
