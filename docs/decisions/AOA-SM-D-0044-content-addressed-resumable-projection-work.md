# Content-Addressed Resumable Projection Work

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0044
- Original date: 2026-08-08
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `DESIGN.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: session indexing, graph indexing, freshness, incremental maintenance, orchestration, resource control
- Projection layers: raw blocks, session segments, session index, token accounting, entity registry, graph source contributions
- Guard families: content identity, cooperative deadline, atomic publish, dependency pinning, selective invalidation, starvation prevention
- Posture: accepted

## Context

One large raw session could require hundreds of serial segment builds while a
single global maintenance lease remained held. Cooperative budgets were checked
between sessions, not inside one build, so timeout discarded completed work and
prevented smaller fresh sessions from advancing. Token-accounting drift could
repeat the same full build. Registry content growth could also invalidate graph
sources that never used the changed entity.

These were not independent timeout problems. The implementation treated all
derived work as one dependency and one transaction even though only final
publication requires a global atomic boundary.

## Options Considered

- Increase timeouts and global maintenance budgets. Rejected because it keeps
  starvation, loses interrupted work, and does not reduce computation.
- Publish segments independently as they finish. Rejected because readers could
  observe mixed raw, segment, manifest, and session-index generations.
- Reuse generated artifacts by path or timestamp. Rejected because neither
  proves semantic compatibility with raw, producer, or policy inputs.
- Address build work by its actual dependencies, checkpoint verified artifacts,
  and retain one short atomic publication boundary.

## Decision

A session projection build has a content-addressed work identity containing the
raw publish identity, session and segment producer generations, task-episode
source generation, and privacy, redaction, and token-accounting policies.
Completed raw blocks and segments are checkpointed with artifact hashes. A
cooperative deadline may stop between phases or bounded segment waves without
discarding compatible progress.

One nonblocking per-session lease owns construction. Independent segments may
run in a deterministic bounded process pool, initially four workers and
configurable from one through six. Unchanged published segments are reused only
when their input digest and artifact receipts match. A growing session rebuilds
its changed tail and new segments.

The global maintenance lease is not held during CPU construction. A completed
work directory is revalidated against current raw and producer identity, then
the global lease covers only atomic publication, registry update, and dirty
propagation. Any race abstains and preserves last-good.

Token-only drift uses a dedicated atomic metadata backfill when a complete
compatible session projection exists. Initial materialization still performs a
full build.

Graph sources store route tokens actually used plus a digest of their resolved
registry records. Registry-wide transaction pins and proof-gated rebind remain,
but per-source dirty state changes only when the source's selective dependency
changes. Existing graph stores receive this state through an idempotent
migration.

Oversized initial projections use a resumable heavy lane with bounded slices.
All oversized deferred or generation-stale candidates, not only the one
admitted by fairness for the current slice, are removed from that maintenance
cycle's locked scope. Compatible indexed sessions remain eligible for bounded
metadata/search work; an indexed session is routed heavy only when its session
projection generation actually requires rebuilding.
Catch-up permits a 300-second per-session slice because target-host live proof
showed 91.7-110.9 seconds of mandatory parse/classification cost on a real
68.2-MB event-dense archive; the former 120-second slice preserved work but
could repeatedly finish before the next segment wave. Ordinary fresh sessions
remain eligible. Automatic launches stay subject to the host resource
controller and persistent bounded retry queue.

## Rationale

Computation, dependency compatibility, and publication are different
boundaries. Content-addressed work makes interruption and reuse safe;
per-session leases isolate ownership; a short global publish lease preserves the
existing reader contract. Selective dependency digests apply the same principle
to graph invalidation: unrelated content growth must not create semantic work.

This preserves raw evidence and fail-closed freshness while making backlog cost
proportional to changed inputs rather than total history.

## Consequences

- Positive: completed segment work survives cooperative timeout and restart.
- Positive: unrelated sessions can publish while a heavy session is building.
- Positive: live growth reuses stable segments and token-only drift avoids full
  parsing and segmentation.
- Positive: unrelated registry additions no longer create global per-source
  graph rebuild debt.
- Tradeoff: resumable work consumes temporary storage until published or proven
  incompatible and old enough for guarded cleanup.
- Tradeoff: process parallelism increases short-lived CPU and memory demand and
  therefore remains resource-gated and bounded.
- Follow-up: calibrate worker count and segment-wave size from target-host RSS,
  CPU, I/O, and wall-time receipts rather than hardware count alone.

## Boundaries

A checkpoint proves only verified generated work for one exact dependency
identity. It is not published freshness and is never raw authority. Selective
graph dependency state does not establish that an entity or alias is correct;
owner sources and registry canonicalization remain authoritative for that
decision. A successful resource launcher, timer, or test does not prove live
freshness without post-publication route evidence.

The decision does not permit rewriting historical raw evidence, weakening
generation checks, exposing mixed projection generations, or bypassing host
resource admission.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `DESIGN.md`
- `docs/decisions/`

## Follow-Up Route

Run serial and four-worker representative benchmarks under the host resource
controller, retain phase and resource receipts, calibrate the default, then
verify recurring hot, catch-up, and heavy cycles against live freshness routes.

The final target-host 99,096,456-byte synthetic receipt is retained at
`docs/benchmarks/session-projection-incremental-v3-final-100mb.json`. Cold
serial completed in 101.84 seconds and the four-worker cold build in 84.54
seconds; the segment phase itself improved from 45.75 to 20.41 seconds (2.24x),
while mandatory serial parse, privacy, raw-block accounting, token accounting,
session-index, and validation phases bound total speedup to 1.20x. The growing
session completed in 45.20 seconds while reusing 220 raw blocks and 220 segment
artifacts and rebuilding only two of each. A fresh session completed in 0.46
seconds. Serial/parallel semantic digests matched, every measured raw SHA was
unchanged, and the benchmark reported no swaps. This is target-host synthetic
performance evidence, not live archive-freshness proof. The earlier v2 receipt
is retained as pre-final optimization evidence and is not the release receipt.

## Verification

Focused tests cover serial/parallel semantic parity, phase checkpoint and
resume, source and generation/policy drift, duplicate session leases, concurrent
heavy and fresh publication, atomic-publish failure preservation, guarded stale
work cleanup, growing-session reuse, token-only backfill, stale-route split
publication, selective graph invalidation and migration, resource retry, and
heavy-lane starvation exclusion. The target-host benchmark receipt is present;
full source validation and live runtime freshness proof remain required before
live rollout claims.
