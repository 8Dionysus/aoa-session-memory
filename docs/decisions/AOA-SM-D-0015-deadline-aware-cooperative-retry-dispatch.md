# Deadline-Aware Cooperative Retry Dispatch

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0015
- Original date: 2026-07-17
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `PIPELINE.md`, `docs/decisions/`
- Surface classes: automatic maintenance, retry queue, freshness orchestration, bounded scheduling
- Projection layers: maintenance coordinator, persistent retry queue, generated projection catch-up
- Guard families: head-of-line blocking, dispatch latency, heavy-work starvation, cooperative work budget, progress honesty
- Posture: accepted

## Context

Generated projection writers share one maintenance lease. The persistent retry
dispatcher previously ordered all due work only by retry time. An older
backlog item could therefore claim the lease immediately before a short hot or
catch-up repair and hold it for the profile launcher timeout. The timers and
dispatcher could continue to run successfully while a query-demanded
projection remained stale behind unrelated work.

Ordering profiles by a permanent class rank would reverse the failure rather
than solve it: recurring hot work could indefinitely postpone backlog or deep
maintenance. The worker also needs a cooperative work envelope that is
shorter than the outer launcher timeout, so bounded progress can release the
shared lease before the host safety timeout is reached.

## Options Considered

- Keep retry-time FIFO ordering and use each launcher timeout as the default
  maintenance budget. Rejected because an older heavy item can become a
  head-of-line blocker and retain the shared lease for the full outer safety
  window.
- Give hot and catch-up profiles a permanent strict priority over backlog and
  deep work. Rejected because continuous short work can starve necessary heavy
  projections indefinitely.
- Order due work by profile-aware dispatch deadlines and give automatic
  profiles cooperative work budgets distinct from launcher timeouts.

## Decision

Every due retry item receives a dispatch deadline derived from its retry-ready
time plus the configured wait target for its profile. The dispatcher selects
the earliest deadline first, then the earlier retry-ready time and stable queue
key. Hot and catch-up profiles use shorter wait targets. Backlog and deep
profiles use longer targets but age ahead once their deadlines become older,
so urgency does not remove heavy-work fairness.

Automatic profiles define a cooperative maintenance budget separately from
the host launcher timeout. The worker returns after bounded progress or its
cooperative budget, while the longer launcher timeout remains an outer safety
boundary. Explicit operator or persisted queue overrides remain honored and
visible rather than being silently rewritten.

Queue, dispatcher, and maintenance-status packets expose the policy version,
ordered due keys, dispatch deadlines, target breaches, and the selected item.
These fields describe scheduling only. A selected or successfully launched
item does not become semantically current until the owning projection
freshness state advances.

## Rationale

Deadline ordering combines bounded latency with aging. A short repair can move
ahead of a heavy item that has not exhausted its allowed wait, while an older
backlog or deep item eventually outranks newly recurring hot work. This keeps
one shared writer lease and its consistency boundary instead of introducing
concurrent generated-store writers.

Separating cooperative work from launcher safety limits shortens ordinary
lease ownership without turning a timeout into a false failure or claiming
that partial progress is completion. Exposing the calculation in generated
packets makes starvation and policy drift reviewable from the access plane.

## Consequences

- Query-demand and recent-session repairs can reach the shared writer without
  waiting behind every older heavy retry.
- Backlog and deep work retain an explicit aging route and cannot be
  permanently displaced by a fixed class priority.
- A maintenance cycle may still finish with remaining work and reschedule
  itself; that is bounded progress, not global freshness.
- Persisted or operator-supplied budgets may differ from profile defaults and
  remain visible in the launch and coordinator packets.
- Changes to wait targets or cooperative budgets remain source/config changes
  that require live orchestration review, not edits to this rationale record.

## Boundaries

This decision governs ordering and cooperative lease duration for the
persistent automatic retry queue. It does not define semantic ranking, query
relevance, graph relation truth, host resource admission, current freshness,
or a freshness SLO. The retry queue and coordinator remain generated
orchestration surfaces, not evidence authority. Session-specific queue
contents, timings, gold queries, and A/B outputs remain in session provenance
and runtime diagnostics.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`

## Follow-Up Route

Continue live automatic trials across hot, catch-up, backlog, and deep
profiles, including interrupted in-flight recovery and resource-blocked
resumption. Reopen the policy if new randomized trials show missed dispatch
targets, heavy-work starvation, unbounded lease ownership, hidden stale
results, or worse retrieval quality.

## Verification

An owner-neutral regression fixes a mixed-profile due queue, proves the
deadline order before dispatch, exercises the selected launch, advances time,
and proves that a newly due hot item and an aging backlog item retain their
intended order. The same regression verifies compact status visibility and
that a profile cooperative budget is shorter than its launcher timeout.

A live automatic A/B trial preserved the same queue and freshness demand:
retry-time FIFO selected a long backlog cycle first, while the deadline policy
selected the demanded hot repair, advanced its scoped exact projection, and
then automatically selected the waiting catch-up profile. Exact retrieval was
repeated before and after against independently sealed raw evidence. Full
source, portable, and restart/resource recovery checks remain separate gates.
