# Bounded Generated-Reader Process Boundary

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0098
- Original date: 2026-08-26
- Owner surfaces: `scripts/aoa_session_memory.py`, `DESIGN.md`, `DESIGN.AGENTS.md`, `PIPELINE.md`, `INSTALL.md`, `READINESS.md`, `tests/test_session_memory.py`
- Surface classes: query admission, storage isolation, exact fallback, runtime safety
- Projection layers: portable SQLite search, bounded archived/live raw navigation
- Guard families: process deadline, result transport, cleanup/reap, parent-death, source-only fallback
- Posture: accepted

## Context

The SQLite progress handler is cooperative: it is called by SQLite's virtual
machine after control has returned from lower-level storage operations. A
generated-reader search can therefore remain blocked in kernel file I/O after
the requested query deadline, preventing the serving function from returning a
packet or reaching its bounded raw fallback.

## Options Considered

- Extend the Python thread timeout or rely only on the SQLite progress handler.
  Rejected because neither can reclaim a caller blocked below the cooperative
  query callback.
- Copy or rebuild the generated store before each read. Rejected because it
  adds another unbounded storage operation and changes the read-only query
  boundary into a maintenance path.
- Start the generated read in an isolated process, let the parent own the hard
  deadline and cleanup, and use the existing bounded source/raw route after a
  timeout. Accepted.

## Decision

Timed `portable_sqlite` searches enter a dedicated reader process before
generated-storage connection or query work begins. The serving parent waits only
until the derived query deadline, terminates and reaps the child through a
bounded cleanup window, and records whether cleanup was verified. The child has
a parent-death signal as a best-effort protection against a normal serving
process exit. Result transport uses a child-written temporary result file with
atomic replacement, so a large result cannot block the parent on a pipe read.

The ordinary generated result path remains unchanged inside the reader and keeps
its refs, route, and freshness fields. A timeout, process failure, or invalid
reader result returns through the parent-owned bounded archived raw route for a
session-scoped exact query. An unscoped exact query uses source-only recent
registry and transcript-clock candidate selection before bounded live/archive
scans; it never reopens the generated store after the reader boundary failed.
These routes remain read-only and cannot claim global absence or downstream
freshness. If child cleanup is not verified, the result remains failed even when
the bounded source route recovers evidence.

## Rationale

The process boundary is the first boundary in the route that can contain a
non-cooperative generated reader without making a Python timeout look like
completion. Parent-owned cleanup and explicit transport state make the lifecycle
observable. Reusing the existing source/raw authority preserves exact evidence,
budgets, and no-mutation guarantees while retaining the normal generated fast
path.

## Consequences

- Positive: a blocked generated connection or query cannot prevent the serving
  parent from returning a bounded timeout packet and fallback route.
- Positive: session and global fallback have an explicit guarantee not to reopen
  the failed generated reader.
- Tradeoff: each timed portable search pays process startup and result transport
  cost, and a reader stuck in uninterruptible kernel I/O may require an
  explicit failed cleanup posture until the kernel releases it.
- Follow-up: live acceptance must prove reader cleanup, normal generated
  success, source/raw fallback, and separated freshness axes on a new natural
  session while maintenance continues.

## Boundaries

This decision does not make a timeout, fallback result, process exit, timer,
retry receipt, or top-level `ok` flag proof that all projections, consumers, or
global recall are current. It does not authorize reindex, retry, drain, sweep,
queue or raw mutation, service quiescence, observer/wake/Goal mutation, or
remote/GitHub work. The process boundary contains the reader; it does not turn
an unverified kernel cleanup into verified absence of a process.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.md`
- `DESIGN.AGENTS.md`
- `PIPELINE.md`
- `INSTALL.md`
- `READINESS.md`
- `docs/decisions/`

## Follow-Up Route

Run source compilation, focused reader/fallback and existing exact-search tests,
the owner suite, decision index validation, clean portable export and public
safety/trust admission, then activate the admitted source through the owner
install route. Capture runtime identity, natural post-activation search, reader
cleanup, maintenance posture, and semantic freshness separately before
independent reacceptance.

## Verification

Focused tests cover non-cooperative reader timeout, storage-acquisition timeout,
session raw recovery, global source-only recovery, large result transport, and
the existing exact-search success/locking/fallback routes. Source identity,
export/admission, live activation, and natural successor evidence remain
separate claims in the actor report and handoff.
