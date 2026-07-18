# Bounded Background Graph Queue Reserve

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0012
- Original date: 2026-07-17
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `PIPELINE.md`, `docs/decisions/`
- Surface classes: automatic maintenance, graph maintenance, bounded scheduling
- Projection layers: graph maintenance queue, graph source-state ledger, resource-block fallback
- Guard families: background starvation, head-of-line blocking, bounded queue growth, progress honesty
- Posture: accepted

## Context

The graph maintenance queue is a bounded generated work surface. Resource-block
fallbacks previously seeded it from the source-state ledger only when the queue
was empty. That rule fails when the remaining queued source is individually
larger than the fallback's node or edge budget: the source stays queued, the
queue never becomes empty, and cheaper actionable ledger sources never enter
the candidate set. The fallback can then exit successfully without advancing
the graph.

Query-demand catch-up already has a one-batch reserve for explicitly demanded
sessions under `AOA-SM-D-0006`. Background work without a demand signal needs a
separate bounded admission rule; query demand must not be manufactured merely
to bypass head-of-line blocking.

## Options Considered

- Continue draining the existing queue before ledger seeding. Rejected because
  one oversized source can starve the entire background backlog indefinitely.
- Append a complete candidate window on every retry. Rejected because stalled
  retries can grow the generated queue without bound.
- Evict or mark the oversized source complete. Rejected because size is a
  scheduling constraint, not evidence that the projection is current or
  invalid; the source still belongs to a heavier route.
- Maintain a fixed background candidate reserve, add only its missing entries
  from the ledger, use normal priority and cost selection, and preserve
  oversized entries for a compatible route.

## Decision

An all-session resource-blocked graph fallback maintains a bounded background
queue reserve that covers its configured candidate window. Existing queue
entries count toward the reserve. Before selection, the fallback requests from
the source-state ledger only the difference between the target reserve and the
current queue size. A queue already at or above the reserve is not expanded.

Normal graph priority and exact refresh-cost selection run on the combined
queue. Individually oversized sources remain queued for a heavier compatible
route, while cheaper candidates may advance around them.

Fallback execution success and graph progress remain distinct. When the child
completed but no actionable source advanced and actionable work remains, the
outer status is a retryable `resource_blocked_graph_drip_no_progress`, not
`resource_blocked_graph_drip_completed`. Reports expose the previous queue
size, target reserve, requested top-up, processed source count, and remaining
actionable count.

## Rationale

The selected route repairs candidate admission without weakening graph
freshness, removing evidence, or widening every fallback into a full archive
scan. Counting existing entries makes repeated retries idempotently bounded.
Keeping an oversized source preserves its provenance and future heavy-lane
route, while cost-aware selection prevents it from becoming a global
head-of-line blocker.

Separating process completion from semantic progress prevents timer and
launcher success from masquerading as projection advancement. The retry queue
can continue bounded recovery while operators and query consumers see the
truthful stalled state.

## Consequences

- Background graph work can advance while an incompatible heavy source remains
  queued.
- A successful fallback may add candidates and process only part of the
  reserve; later cycles refill only the bounded deficit.
- The queue may contain a persistent oversized source until a heavy route has
  sufficient resources. That debt remains visible rather than being discarded.
- A no-progress cycle with remaining work is observable and retryable instead
  of being classified as completed.
- Query-demand reserve semantics remain unchanged and continue to prioritize
  explicitly observed targets separately.

## Boundaries

This decision governs generated background queue admission and progress status
for resource-blocked graph fallback. It does not define graph relation
semantics, retrieval relevance, query-demand truth, host resource policy,
heavy-job admission, or a freshness SLO. It does not make the queue, ledger, or
runtime report evidence authority. Session-specific source IDs, timings,
counts, and laboratory history remain in session provenance.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`

## Follow-Up Route

Observe repeated timer and retry cycles, including full-reserve, partially
drained, oversized-only, and newly dirty states. Reopen the policy if
randomized trials show unbounded growth, background unfairness, repeated
no-progress without escalation, or loss of a heavy source's recovery route.

## Verification

A live resource-blocked fallback first demonstrated a nonempty queue with
actionable ledger work, zero processed sources, and repeated false completion.
After the change, the ordinary retry dispatcher topped up only the missing
reserve, selected and processed cheaper sources, retained the oversized source,
and rescheduled the remaining work. Owner-neutral regressions cover a
partially filled reserve, a full reserve that must not grow, progress with
remaining work, and no progress with remaining work. Source and portable test
suites and the portable audit verify parity; live graph quality and final
freshness remain separate gates.
