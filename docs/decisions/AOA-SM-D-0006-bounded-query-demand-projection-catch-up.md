# Bounded Query-Demand Projection Catch-Up

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0006
- Original date: 2026-07-16
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `docs/decisions/`
- Surface classes: automatic maintenance, freshness orchestration, bounded scheduling
- Projection layers: search repair, episode semantic, agent atlas, dense vectors, graph maintenance queue
- Guard families: query-demand priority, scoped-window expansion, queue top-up, starvation prevention, generated-state honesty
- Posture: accepted

## Context

Automatic maintenance normally narrows work by date, activity, cost, and a
generated queue. Those bounds protect interactive latency and host resources,
but two individually reasonable rules can combine into starvation:

- a long-running or older session requested by a query can fall outside the
  profile's ordinary date window; and
- an actionable graph source can remain outside a perpetually nonempty queue
  because ledger seeding occurs only when that queue is empty.

Observing query demand after either scope has already discarded the requested
session is too late. Sorting the remaining candidates correctly cannot repair
a missing candidate, and timer or launcher success does not prove that the
requested projection advanced.

## Options Considered

- Keep date windows and existing queue membership strict. Rejected because a
  needed old or heavy projection can remain stale while unrelated bounded work
  continues successfully.
- Widen every automatic profile to the full archive or rebuild every dirty
  projection. Rejected because it removes useful resource bounds and turns a
  local demand signal into global work.
- Append a new full batch of demanded graph sources on every retry. Rejected
  because stalled workers could grow the generated queue without bound.
- Admit only a bounded set of observed query-demand sessions across the normal
  scope boundary, and top up an actionable graph queue to a fixed demand
  reserve before selection.

## Decision

Treat observed query demand as a bounded scheduling input that may cross an
automatic profile's ordinary candidate boundary.

For an automatic all-session profile with date or count filters, the scheduler
starts with the normal scoped records and prepends only the configured bounded
set of demanded sessions that are present in the archive. The report names the
added session IDs and preserves the original scope metadata.

For an applying graph queue consumer, demanded sessions receive an actionable
queue reserve no larger than one maintenance batch. The reserve is topped up
from the generated source-state ledger even when unrelated queue items already
exist. Existing actionable demanded items count toward the reserve, so a
blocked or failed cycle does not append another full batch indefinitely.
Normal priority and cost selection then operate on the combined queue.

Query demand changes scheduling only. It does not establish relevance, truth,
freshness, usage, causality, or acceptance of any graph relation. Projection
currentness still comes from source fingerprints, generation identity, and
post-maintenance state.

## Rationale

The chosen route fixes candidate admission rather than weakening freshness or
resource law. A small number of explicitly observed targets can advance even
when they are old, heavy, or absent from a nonempty generated queue, while the
ordinary window and background queue remain intact for all other work.

Counting existing demanded queue entries toward a one-batch reserve makes the
operation idempotent and restart-safe. Keeping demand as generated scheduling
metadata prevents retrieval activity from becoming evidence authority. Honest
selected, deferred, remaining, and freshness fields continue to distinguish
progress from completion.

## Consequences

- Needed sessions can make bounded progress without waiting for an unrelated
  date window or for the graph queue to become empty.
- Automatic reports expose which sessions were admitted by demand and which
  graph sources were added to the bounded reserve.
- A large demanded projection may receive several consecutive batches and can
  delay cheaper background work; remaining counts and the unchanged background
  queue make that tradeoff visible.
- Query demand that points to a missing archive, a recent live source still in
  its quiet window, or a non-actionable ledger row does not manufacture work.
- Global rebuild and heavy recovery routes remain available for structural
  incompatibility or corruption, not as the default response to starvation.

## Boundaries

This decision governs candidate admission and scheduling for generated
projection catch-up. It does not define query ranking, semantic relevance,
graph edge meaning, host resource policy, MCP mutation authority, or a
freshness SLO. It does not make the maintenance queue or source-state ledger
evidence authority. Session-specific demand counts, timings, paths, and gold
queries remain in runtime diagnostics and session provenance.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`

## Follow-Up Route

Observe repeated timer and retry cycles until demanded search and graph
projections become current, then compare source and portable behavior. Reopen
the scheduling policy if randomized trials show background starvation,
unbounded queue growth, hidden stale results, or worse retrieval quality.

## Verification

Owner-neutral regressions reproduce both failures before the fix: a demanded
session outside an automatic date scope and demanded graph sources absent from
a nonempty queue. They then verify bounded scope admission, one-batch queue
top-up, demanded-source selection, successful removal, and preservation of the
background queue. Live automatic progress and final freshness remain separate
runtime gates rather than claims made by this record.
