# Coalesced Hook Intent and Contention-Neutral Retry

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0070
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: hooks, scheduling, incremental maintenance, recovery, performance
- Projection layers: hook sync queue, maintenance retry queue, session projection, graph maintenance queue
- Guard families: intent coalescing, evidence retention, fair retry, writer contention
- Posture: accepted

## Context

Lifecycle hooks may fire hundreds of times while a large live transcript stays
above the lightweight worker budget. Each signal previously became a separate
deferred executable job even though all jobs requested the same latest-source
sync. Separately, catch-up and backlog share one maintenance lease, but every
healthy lock collision consumed a bounded retry attempt. Constant live work
could therefore amplify seven sessions into hundreds of jobs and exhaust the
graph owner's retries without ever granting it a write window.

## Options Considered

- Execute one job per hook signal. Rejected because repeated intent is not
  distinct projection work and grows faster than the worker can retire it.
- Delete duplicate jobs after noticing the backlog. Rejected because it loses
  the operational receipt that the signals occurred and does not prevent new
  amplification.
- Treat shared-lock contention as an ordinary failed attempt. Rejected because
  a healthy competing owner is neither resource denial nor execution failure;
  a bounded retry cap can silently abandon still-required convergence.
- Keep one active sync intent per session/transcript, preserve redundant job
  files as superseded receipts, and reschedule writer contention without
  consuming the failure budget.

## Decision

Hook sync jobs use a stable session/transcript queue identity. New lifecycle
signals atomically update the pending or deferred intent with the latest event
snapshot while retaining the earliest queue time, contributing event names,
reasons, and total signal count. The worker migrates legacy duplicates into a
generated `superseded` lane and executes one canonical intent. A job already
running may have one pending successor to cover transcript growth during its
snapshot.

The persistent maintenance dispatcher classifies the shared maintenance lock
and heavy-lane lease as contention. A contended profile remains queued, resets
its failed-attempt cycle, increments an observable contention counter, and is
retried through the existing aged-profile fairness order. Real resource and
execution failures retain bounded exponential backoff and exhaustion.

## Rationale

The system needs to scale with unique unfinished sessions and projection
changes, not raw hook frequency. Coalescing preserves the latest executable
state without erasing evidence that earlier signals existed. Contention-neutral
retry keeps independently owned catch-up and graph work eventual under
continuous sessions while preserving one writer, bounded launches, resource
admission, and the existing fairness contract.

## Consequences

- Positive: repeated hooks for one oversized transcript occupy one active job
  rather than an unbounded deferred queue.
- Positive: old hook signals remain inspectable as superseded generated
  receipts, while only the latest snapshot executes.
- Positive: active catch-up cannot permanently exhaust backlog or graph work
  merely by holding the shared lease at unlucky retry times.
- Tradeoff: the active job records an aggregate signal count rather than
  executing each lifecycle signal as an independent sync.
- Tradeoff: contention can keep an intent queued indefinitely when the host
  truly provides no fair write window; scheduling evidence must remain honest
  about that state.

## Boundaries

Coalescing does not merge different session IDs or transcript paths, rewrite
raw evidence, declare a projection current, or suppress one successor observed
during a running job. Contention-neutral retry does not bypass resource
admission, run writers concurrently, prove fairness capacity, or make a failed
child successful.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Use hook-worker queue counts, retry-queue contention cycles, current-generation
session counts, and graph remaining work to calibrate only bounded batch sizes
and timer intervals. Keep raw evidence and projection freshness as the stronger
truth surfaces.

## Verification

Focused tests cover pending and deferred coalescing, legacy superseded receipt
migration, latest-event preservation, and last-attempt lock contention. The
decision-index builder, full source suite, portable export parity, live queue
collapse, resource-gated catch-up, and graph progress receipts remain the
release gates.
