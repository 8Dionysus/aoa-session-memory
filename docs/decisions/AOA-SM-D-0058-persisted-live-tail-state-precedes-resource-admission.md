# Persisted Live-Tail State Precedes Resource Admission

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0058
- Original date: 2026-08-11
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: freshness, incremental maintenance, orchestration, resource control
- Projection layers: search freshness state, graph source ledger, maintenance diagnostics
- Guard families: pre-admission boundedness, persisted scheduling state, live-path recheck, fail-closed child validation
- Posture: accepted

## Context

The catch-up resource wrapper selected a live-tail command by invoking the full
maintenance-status route before asking the host resource controller for
admission. That status route intentionally validates global entity-registry
dependencies and classifies cleanup candidates. On a large archive those
checks can reconstruct observed route terms and hash staged raw authority.

This made a denied automatic launch more expensive than the work it was denied
permission to start. Repeated timers could spend a long interval reading
generated and raw-backed state, publish no semantic progress, then repeat the
same preflight. Content-addressed projection checkpoints did not help because
the cost occurred before the admitted child reached them.

## Options Considered

- Keep the full maintenance-status call and cache only its final recommendation.
  Rejected because the first call and every cache invalidation retain the global
  scan, while a recommendation is not a safe resource-admission identity.
- Increase the timer or launcher timeout. Rejected because it permits more
  pre-admission work without reducing repeated computation or proving progress.
- Skip live-tail selection and always launch general maintenance. Rejected
  because a ready recent session would lose its bounded priority route.
- Select the candidate from persisted scheduling state, recheck only the named
  live transcript with bounded filesystem metadata, and leave complete
  validation to the resource-admitted child.

## Decision

The automatic catch-up wrapper performs live-tail selection before resource
admission from the persisted search freshness state. When that state contains
no search live-tail candidate, it may consult the generated graph hot state and
source ledger. It rechecks a sampled live transcript only with the existing
bounded filesystem `stat` route for quiet-window truth.

This pre-admission route must not invoke global maintenance status, rebuild an
observed entity-registry dependency, classify maintenance-cleanup candidates,
hash projection stages, parse raw events, or compute raw content digests. Its
packet declares `source_scan=false` and identifies persisted scheduling state
as its scope.

Missing, invalid, or insufficient scheduling state does not invent a targeted
command. It falls through to the ordinary host resource gate. Only an admitted
child may perform the wider maintenance checks, acquire writer leases, inspect
projection dependencies, resume checkpoints, or publish generated state. The
child revalidates the selected source and generation, so cached scheduling
state never becomes freshness or evidence authority.

## Rationale

Scheduling identity, host admission, semantic validation, and atomic
publication are separate boundaries. Persisted search freshness and graph
ledger state already exist to make recurring discovery bounded. Using them for
candidate navigation preserves recent-session priority without paying global
validation cost before the host decides whether work may run.

Failing closed inside the admitted child preserves raw evidence, generation
checks, and publication safety. A stale scheduling hint can cause a cheap
abstention or redundant admitted validation; it cannot publish stale data.

## Consequences

- Positive: a resource-blocked catch-up no longer reads or hashes large session
  and projection payloads before the denial.
- Positive: search live-tail selection avoids graph-state loading when the
  persisted search state already names the bounded candidate.
- Positive: timer cost before host admission is proportional to compact
  scheduling state plus at most a bounded live-path metadata recheck.
- Tradeoff: the fast status is navigation, not current global maintenance
  truth, and may conservatively miss a candidate until persisted state is
  refreshed.
- Tradeoff: an admitted child may still need expensive validation or projection
  work; its cooperative budget, hard timeout, checkpoints, and receipts remain
  mandatory.
- Follow-up: retain a real recurring-cycle receipt proving bounded pre-admission
  wall time and then restore the catch-up timer.

## Boundaries

This decision does not weaken host resource admission, raw or segment evidence
authority, generation checks, maintenance cleanup, entity-registry validation,
or atomic publication. It does not call a persisted scheduling hint fresh and
does not make timer completion semantic progress.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Run focused source tests, validate the generated decision indexes, export the
portable bundle, and measure the read-only fast path plus one resource-gated
live catch-up cycle before re-enabling recurring catch-up.

## Verification

Focused tests must prove that a persisted search live-tail candidate is routed
without calling global maintenance status or graph status, that the packet
declares no source scan, and that targeted, graph, explicit-skip, and oversized
routes preserve their existing behavior. Live proof must compare pre-admission
wall time and memory with the prior recurring route while preserving raw hashes
and publication gates.
