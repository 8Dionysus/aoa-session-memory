# Graph Blockers Transfer to the Upstream Owner

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0074
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: automatic maintenance, graph drip, hook worker, predecessor handoff
- Projection layers: session index, graph
- Guard families: generation compatibility, no-progress circuit, bounded queue, owner transfer
- Posture: accepted

## Context

Graph maintenance cannot repair a contribution whose session-index generation
changed. The hook-worker graph lane already transferred these named blockers
to deduplicated session reindex jobs, but the periodic resource fallback only
opened its no-progress circuit. It could therefore keep the graph safe while
leaving the repair route unowned.

## Options Considered

- Keep the circuit operator-only. Rejected because the diagnostic already
  names a bounded, supported predecessor route.
- Let graph maintenance rebuild session indexes itself. Rejected because that
  crosses owner boundaries and weakens generation admission.
- Reuse the hook worker's bounded predecessor queue from every automatic graph
  entry point.

## Decision

An automatic graph fallback that returns named session-generation blockers,
or observes an applicable no-progress circuit containing those blockers,
queues the same bounded and deduplicated `session_generation_reindex` jobs used
by the hook worker. The wrapper reports the handoff as a mutation with
remaining work and preserves retry intent. Each predecessor job may enqueue
graph continuation only after a direct probe proves its session generation is
current. Pending predecessor work is processed before probing deferred graph
jobs, and all deferred graph jobs in one worker wave share one circuit
snapshot.

## Rationale

The graph remains fail-closed while actionable repair moves to the owner that
can perform it. Reusing one queue contract avoids a second recovery mechanism
and turns the no-progress circuit from a terminal observation into bounded
forward motion.

## Consequences

- Positive: periodic graph maintenance no longer stalls on known upstream
  generation blockers.
- Positive: repeated observations deduplicate rather than flood the queue.
- Positive: graph continuation still requires current-generation proof.
- Positive: a backlog of deferred graph jobs cannot multiply the cost of one
  identical dependency probe or delay its own predecessor.
- Tradeoff: a bounded pass transfers only the predecessors named by its current
  result or circuit evidence; later passes discover the rest.

## Boundaries

This does not make graph maintenance the owner of session indexes, bypass the
shared maintenance lock, treat a queued predecessor as freshness, or authorize
a full graph rebuild.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Run the periodic resource wrapper against a live no-progress graph circuit,
let the hook worker complete its bounded predecessor jobs, and verify that the
successor graph queue resumes only for current generations.

## Verification

Run focused circuit, handoff, retry, hook-worker, decision-index, compile, and
portable-source validation; then exercise the live circuit without a graph
rebuild.
