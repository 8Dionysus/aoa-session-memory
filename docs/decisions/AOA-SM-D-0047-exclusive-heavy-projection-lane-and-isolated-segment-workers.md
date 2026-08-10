# Exclusive Heavy Projection Lane and Isolated Segment Workers

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0047
- Original date: 2026-08-09
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `DESIGN.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: session indexing, freshness, incremental maintenance, orchestration, resource control
- Projection layers: session segments, session projection work
- Guard families: cooperative deadline, deterministic parallelism, resource admission, starvation prevention, atomic publish, privacy
- Posture: accepted

## Context

Content-addressed checkpoints made a single large session resumable, but
per-session leases did not prevent catch-up, backlog, and size-banded Codex
sweeps from processing different large sessions concurrently. Each projection
builder retained a reconciled
whole-session event graph, and segment workers created with `fork` inherited
that graph. Concurrent profiles could therefore multiply resident memory even
though each individual builder stayed within its worker-count bound.

Short heavy slices also repeated ephemeral sensitive-literal discovery and
whole-session classification rehydration. Those values cannot be persisted,
so restartability alone cannot remove that setup cost.

## Options Considered

- Rely only on the host resource gate. Rejected because independently admitted
  profiles can overlap after admission and the organ still owns its internal
  memory topology.
- Reduce every heavy build to one worker. Rejected because it discards useful
  segment parallelism and does not prevent two full parent graphs from
  overlapping.
- Persist the sensitive-literal policy or complete hydrated event graph.
  Rejected because it expands the secret and duplicated-raw surface.
- Serialize automatic heavy construction, keep ordinary maintenance
  independent, lengthen the resumable slice, and isolate segment workers from
  the parent heap.

## Decision

All automatic oversized session builders share one nonblocking heavy-projection
lease across hot, catch-up, backlog, and deep profiles. The lease covers only
the CPU- and memory-heavy resumable construction. A profile that cannot acquire
it records the blocking owner, excludes every heavy candidate from its ordinary
locked scope, and continues with eligible small-session and metadata work.
Applying Codex sweeps acquire the same lease per selected source at or above the
heavy raw-size threshold, including mirror-only capture; smaller candidates in
the same sweep remain independent.

The catch-up, backlog, and deep heavy lanes may use at most 900 seconds or the
remaining enclosing cooperative budget, whichever is smaller. This keeps one
process alive across many segment waves and amortizes its process-local privacy
policy and whole-session hydration. Hot maintenance retains a short slice.
This supersedes only the 300-second automatic heavy-slice calibration recorded
in AOA-SM-D-0044; its content-addressed work, checkpoint, lease, and atomic
publication decisions remain active.

Segment process pools use an isolated interpreter start method. Each task
transfers only one bounded event slice plus its projection inputs, rather than
inheriting the complete reconciled parent graph. Worker count remains
configurable from one through six and must be calibrated from target-host wall,
CPU, memory, I/O, and swap evidence. Final publication retains the existing
short global maintenance lease and atomic validation.

## Rationale

The resource controller, heavy construction, per-session ownership, and atomic
publication are distinct boundaries. Cross-profile serialization prevents
memory multiplication inside the organ, while a nonblocking lease preserves
freshness opportunities for ordinary sessions. A longer continuous slice is
the only safe way to reuse an exact sensitive-literal policy without writing
secret values to disk. Isolated segment workers preserve parallelism while
making memory cost proportional to their bounded task rather than the complete
session.

## Consequences

- Positive: only one automatic whole-session heavy parent and worker pool may
  run at a time.
- Positive: large raw capture sweeps cannot overlap a heavy projection build.
- Positive: ordinary recent sessions and global metadata projections do not
  wait for the heavy lease.
- Positive: fewer restarts repeat privacy discovery and full-session
  rehydration.
- Positive: segment workers no longer inherit the parent's whole-session heap.
- Tradeoff: two independent large sessions cannot consume otherwise idle CPU
  concurrently through automatic profiles.
- Tradeoff: isolated interpreter startup and bounded task serialization add
  overhead that must be included in worker calibration.
- Follow-up: retain a target-host four-versus-six-worker benchmark receipt and
  revisit the default only when wall-time improves without harmful memory,
  swap, or small-session latency effects.

## Boundaries

The heavy lease is host-local orchestration state, not evidence authority or a
freshness claim. It does not replace the per-session lease, host resource gate,
global atomic publication lease, content receipts, privacy policy, or raw
authority. A longer cooperative slice does not authorize an unbounded process
or bypass its hard timeout.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `DESIGN.md`
- `docs/decisions/`

## Follow-Up Route

The target-host calibration receipts are
`docs/benchmarks/session-projection-isolated-workers-v4-workers4.json` and
`docs/benchmarks/session-projection-isolated-workers-v4-workers6.json`. On the
same 30,052,537-byte, 120-segment synthetic fixture, six workers reduced cold
parallel wall time from 19.71 to 18.73 seconds and segment generation from 6.27
to 5.39 seconds. CPU time rose from 42.64 to 47.37 seconds and the resource
launcher cgroup peak rose from 466.3 to 561.6 MiB; neither run swapped and both
matched their serial semantic digest. The roughly five-percent whole-build
wall improvement does not justify increasing the portable default, so four
workers remain the balanced default and six remain an explicit bounded
calibration option.

Export through the owner bundle route and verify source, standalone, and
live-installed surfaces before claiming rollout.

## Verification

Focused tests cover cross-profile heavy-lease deferral, continued ordinary
scope, 900-second budget propagation, isolated-worker semantic parity, and
reported process start method. Both benchmark receipts report raw preservation,
serial/parallel semantic parity, and zero swaps. Source validation, portable
export, and a resource-admitted live continuation remain required for complete
rollout.
