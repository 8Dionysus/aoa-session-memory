# Scoped Graph Evidence Freshness

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0008
- Original date: 2026-07-16
- Owner surfaces: `scripts/aoa_session_memory.py`, `DESIGN.AGENTS.md`, `PIPELINE.md`, `READINESS.md`, `docs/decisions/`
- Surface classes: query presentation, graph freshness, evidence provenance
- Projection layers: graph neighborhood, graph timeline, typed graph bridge
- Guard families: global recall honesty, scoped contribution freshness, ledger fingerprint verification, conservative unverified fallback
- Posture: accepted

## Context

A generated graph can have a large actionable backlog while the bounded source
contributions behind one returned packet are already current. One global
freshness label cannot express both facts safely. Reporting only `stale` hides
useful evidence quality from a consumer; reporting the bounded result as
globally current hides missing recall and can make an incomplete projection
look complete.

The graph store row alone is also insufficient for a local currentness claim.
Its source fingerprint, schema, policy, and classifier identity can disagree
with the generated source-state ledger even while the stored node remains
readable.

## Options Considered

- Expose only the global hot-gate status. Rejected because it cannot
  distinguish current returned evidence from stale global recall.
- Replace the global status with a status derived from returned nodes and
  edges. Rejected because a bounded sample cannot prove completeness or
  currentness of omitted graph sources.
- Treat an existing graph-store contribution row as current without checking
  its source ledger and generation identity. Rejected because readable rows can
  survive source, classifier, schema, or policy drift.
- Preserve global freshness and add a separate conservative freshness axis for
  the exact evidence contributions represented in the returned packet.

## Decision

Graph packets keep global recall freshness and bounded returned-evidence
freshness as separate axes.

The existing top-level graph status and hot-gate fields continue to describe
the graph projection as a whole. They are never upgraded by a current bounded
result. When a bounded neighborhood or timeline returns evidence-bearing nodes
or edges, the reader maps them through graph contribution tables to their
source keys and compares those sources with the graph store and source-state
ledger.

`scope_current` is allowed only when every identified contributing source is
stored as current, uses the active graph schema, store schema, edge policy, and
classifier version, has a matching source fingerprint, and has a clean ledger
state. Dirty, missing, deferred-live, blocked, retired, unmapped, or truncated
scope is reported explicitly and conservatively; missing verification cannot
be converted into currentness.

A compact bridge timeline computes scope from the events it actually returns.
If it was derived from a broader neighborhood, the packet preserves the
neighborhood scope separately. Thus an unreturned stale neighbor cannot make a
current selected timeline look stale, and a current selected timeline cannot
hide stale recall in the wider neighborhood or global graph.

Scoped currentness describes contribution freshness only. It does not prove
relation truth, graph completeness, current owner truth, or the correctness of
an accepted claim. Raw, segment, and session refs remain the evidence handoff.

## Rationale

Two explicit axes preserve both useful local evidence and global recall
honesty. Contribution lookup is bounded by the returned packet, while the
existing ledger and generation checks remain the source of freshness rather
than timestamps or payload appearance. Conservative `unverified` behavior
prevents truncation or missing contributor mappings from becoming false green
states.

Keeping neighborhood scope alongside selected-timeline scope also matches the
actual evidence boundary presented to the consumer. This avoids both forms of
overclaim: attributing unrelated stale neighbors to the returned events and
using a clean event sample to imply complete graph recall.

## Consequences

- Consumers can distinguish “these returned evidence contributions are
  current” from “the graph can currently provide complete recall.”
- A packet may correctly contain a globally stale status, a current selected
  timeline scope, and a stale broader neighborhood scope at the same time.
- Scope lookup adds bounded contribution and ledger work to graph reads; its
  latency and memory posture must remain part of A/B review.
- Older or third-party consumers that inspect only the global status remain
  conservative and do not receive a false currentness claim.
- Contributor lookup failure or a scope larger than the supported bound
  reduces precision to `scope_unverified` rather than weakening freshness law.

## Boundaries

This decision governs freshness presentation for bounded graph evidence. It
does not define graph edge admission, repair scheduling, freshness SLOs,
semantic ranking, causal truth, pruning permission, or owner truth. It does not
make graph packets proof authority and does not authorize MCP mutation.
Session-specific anchors, seeds, timings, source counts, and diagnostics remain
in session provenance.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.AGENTS.md`
- `PIPELINE.md`
- `READINESS.md`

## Follow-Up Route

Keep global hot-gate recovery and scoped evidence verification independent.
Reopen this decision if randomized graph packets expose a false-current scope,
an omitted contributor that should have changed the scope, or material query
cost that cannot be bounded without losing provenance.

## Verification

A gold-first archived-session case first showed a globally stale graph whose
returned evidence contributions were current. A later return review found a
compact timeline inheriting stale state from neighbors it did not return.
Owner-neutral regressions now cover global-stale plus scoped-current behavior,
dirty-ledger scoped-stale behavior, and selected-timeline isolation from
unreturned stale neighbors. Manual positive and negative packets resolve their
raw and segment refs, and the candidate is compared with the prior global-only
reader under equal bounded queries. Private coordinates and measurements stay
in session provenance.
