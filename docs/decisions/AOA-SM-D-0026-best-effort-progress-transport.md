# Best-Effort Progress Transport

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0026
- Original date: 2026-07-19
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `READINESS.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: maintenance coordination, runtime observability, projection freshness, recovery
- Projection layers: session index, search, episode semantic, graph, Atlas
- Guard families: progress transport isolation, atomic publication, partial failure, semantic completion
- Posture: accepted

## Context

Long projection writers emit optional JSON heartbeat events so an operator can
distinguish slow work from no progress. A progress consumer can disappear
while the writer remains healthy. An unhandled broken pipe from that
non-authoritative stream can abort the generator, discard a valid staged
projection, and make transport availability control semantic progress.

The opposite failure is also unsafe: treating a delivered heartbeat, a timer
exit, or a successful wrapper as proof that a projection became current.

## Options Considered

- Let progress-stream failures abort the writer. Rejected because observation
  transport is weaker than staged semantic work and its receipts.
- Disable progress output for long jobs. Rejected because bounded heartbeat
  evidence is useful for detecting stalls, starvation, and head-of-line
  blocking.
- Catch every output or filesystem error. Rejected because unrelated I/O
  failures can be material to correctness and must remain visible.
- Isolate only a broken progress pipe, detach that stream, suppress later
  heartbeat writes, and continue under the ordinary semantic publish gates.

## Decision

Progress events from reindex, search, episode-semantic, graph, and Atlas
writers use one best-effort JSON progress transport.

The transport catches `BrokenPipeError` only. For an operating-system stream it
redirects the broken descriptor to the null sink so interpreter shutdown
cannot convert completed semantic work into a broken-pipe exit. Later progress
events are suppressed. The returned operation packet reports whether progress
was requested, delivered, detached, failed, or suppressed, and states that the
transport is non-authoritative.

Semantic work continues through its normal transaction, producer-stability,
generation-compatibility, dependency, atomic-publication, and evidence gates.
Those gates, persisted projection receipts, and resolvable evidence determine
semantic completion. Heartbeat delivery never does.

## Rationale

This separates observability from truth without losing either. A dead reader
cannot destroy a valid rebuild, while a live reader cannot promote an
unfinished rebuild. Catching only the expected pipe-disconnect condition keeps
disk, serialization, database, and other material failures visible.

Detaching the descriptor also handles the Python shutdown-flush behavior that
can otherwise return a broken-pipe process status after the application caught
the original write error.

## Consequences

- Positive: losing a progress subscriber no longer aborts a semantic
  projection or removes a valid atomic staging result.
- Positive: operation packets distinguish progress delivery from semantic
  completion.
- Positive: progress remains available for slow-job diagnosis when a consumer
  stays connected.
- Tradeoff: after detachment, that process emits no more progress on the
  affected stream; semantic receipts or another observability route must be
  used.
- Tradeoff: final command-output pipes and non-pipe I/O failures retain their
  ordinary failure behavior and must be interpreted alongside maintenance
  receipts.

## Boundaries

This decision does not make a process exit code, systemd state, lock
acquisition, or heartbeat proof of freshness. It does not suppress database,
filesystem, producer, dependency, or evidence failures.

Host launchers may prefer durable journal capture for long jobs, but launcher
choice remains weaker than the projection's own atomic and generation-aware
contracts.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `READINESS.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Read the maintenance coordinator and the projection's persisted generation and
semantic receipt after any detached progress stream. If no semantic progress
was published, follow the ordinary retry or recovery route rather than
inferring success from process completion.

## Verification

A focused emitter contract injects a broken progress stream and verifies one
failure followed by bounded suppression. A graph integration contract requires
the same injected failure to publish a current atomic graph. A real
operating-system pipe-close probe must exit cleanly after detaching the stream.
Release proof also repeats a full projection rebuild under durable journal
capture and checks persisted semantic receipts independently of heartbeat
delivery.
