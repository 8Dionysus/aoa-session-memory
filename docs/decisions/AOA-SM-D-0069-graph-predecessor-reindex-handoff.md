# Graph Predecessor Reindex Handoff

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0069
- Original date: 2026-08-12
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: graph indexing, incremental maintenance, scheduling, recovery, freshness
- Projection layers: session index, graph source contributions, graph maintenance queue
- Guard families: predecessor compatibility, bounded handoff, checkpoint resume, fail closed
- Posture: accepted

## Context

Graph maintenance correctly rejects an archived session whose session-index
generation is not compatible with the current graph producer. The blocked
result names the required session reindex, but the background graph worker
previously completed its own job without preserving that predecessor work.
Recurring graph retries therefore encountered the same source indefinitely
until an operator manually reindexed the session.

## Options Considered

- Keep retrying the blocked graph source. Rejected because the graph consumer
  cannot repair its upstream generation and repeated work makes no semantic
  progress.
- Let graph maintenance reindex the session inside its graph transaction.
  Rejected because it mixes owner stages, lengthens the graph critical section,
  and weakens rollback and resource boundaries.
- Persist a bounded predecessor job, resume it from its checkpoint when needed,
  and enqueue graph continuation only after the session-index generation is
  observed current.

## Decision

The hook worker translates only explicit
`graph_source_generation_incompatible` results caused by
`session_index_generation_identity_changed` into deduplicated, bounded
session-generation reindex jobs. This applies both to a new graph result and to
the latest still-applicable no-progress report held by the graph drip circuit;
the circuit schedules its named predecessor instead of reopening the same
graph attempt. Each job owns one session, uses the existing split publish lock
and cooperative checkpoint route, and remains in the deferred queue while
checkpointed. A global or scoped graph continuation is queued only after a
direct session-index generation probe reports current.

## Rationale

The graph projection should fail closed on an incompatible predecessor, but
automatic maintenance must retain the recovery edge as durable work. Keeping
the reindex in a separate worker job preserves projection ownership and lets
the graph transaction finish before the upstream mutation starts. Dedupe and a
small handoff limit prevent one graph batch from flooding the worker queue;
checkpoint retention makes a large session resumable rather than terminal.

## Consequences

- Positive: a blocked graph queue advances without operator intervention once
  its archived session can be reindexed.
- Positive: graph and session-index producer identities do not change because
  the handoff lives outside both projection producer source ranges.
- Positive: the successor graph job is never admitted from attempted or
  selected work; it requires an observed current predecessor generation.
- Tradeoff: the predecessor and successor require separate worker invocations,
  so convergence is eventual rather than one-process immediate.
- Follow-up: calibrate the per-session cooperative budget from live receipts;
  do not replace the bounded chain with an all-session rebuild.

## Boundaries

This decision does not make a blocked source current, relax graph generation
compatibility, bypass the shared publish lock, or claim that the whole graph
queue is drained. Hard reindex failures remain visible and do not enqueue a
successor graph mutation.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Run the ordinary hook worker until it records a current predecessor generation
and a queued graph continuation, then verify committed graph progress and the
remaining queue through the standard freshness route.

## Verification

Focused tests cover blocked-result extraction, bounded job creation,
checkpoint retention, automatic promotion, current-generation admission, and
successor graph enqueue. Decision-index regeneration/check, `py_compile`, the
full source suite, portable parity, and a live chained receipt remain the
release gates.
