# Source-Owned Persistent Retry Dispatch Activation

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0096
- Original date: 2026-08-24
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `INSTALL.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: freshness orchestration, retry queue, scheduling, installation, systemd contract
- Projection layers: capture-watch ingress, persistent retry queue, resource-gated session projection
- Guard families: current-epoch priority, queue identity, one-lane dispatch, resource admission, restart recovery, source activation
- Posture: accepted

## Context

The owner already has one persistent retry queue and one bounded
`auto-maintenance-retry` dispatcher. It reconciles strict capture identity
under the queue lock, recovers interrupted claims, admits children through the
resource launcher, and shares the maintenance/heavy projection lanes. The
portable source, however, rendered only the capture and broad resource-gated
sweep units. A live retry service/timer could therefore exist as a disabled
legacy file without being source-authorized, while a broad sweep remained a
different lane and did not provide automatic successor dispatch.

The repair must preserve the capture-only boundary and make the existing
dispatcher reachable through one source-owned scheduler topology. Current
freshness obligations also need a bounded scheduling hint so they cannot sit
behind historical retry debt, while the exact capture identity remains the
admission authority.

## Options Considered

- Enable the existing live retry timer directly. Rejected because a legacy
  file is not source authority and an ad hoc enable would bypass export,
  install, and unit-contract review.
- Add another poller or put retry work into capture-watch or the broad sweep.
  Rejected because it creates competing queue ownership, risks heavy work in
  capture, and collapses separate resource and projection boundaries.
- Render a new dispatcher implementation beside the existing one. Rejected
  because it duplicates retry ownership and would make attempts, leases, and
  successor reconciliation ambiguous.
- Render one service/timer for the existing bounded dispatcher and add a
  persisted current-epoch scheduler hint that is revalidated before claim.
  Accepted.

## Decision

The source renderer emits exactly one persistent retry-dispatch service and
timer in addition to the capture-only and resource-gated sweep pairs. The
retry service invokes only `auto-maintenance-retry --apply --limit 4
--write-report`; the dispatcher remains the sole queue worker and launches
each child through the existing resource-gated owner route. The timer is a
bounded `Type=oneshot` cadence with `OnActiveSec=2min` for the initial arm,
`OnUnitInactiveSec=1min` for the post-attempt rearm, jitter, and
`Persistent=true`. Using `OnActiveSec` is necessary when an already-running
user manager enables the timer after the boot-relative point has elapsed;
`OnUnitInactiveSec` alone cannot arm a service that has never run. Rendering
and portable installation still write named unit files only; they do not
enable, start, reload, or trust systemd.

Capture-watch may mark a freshness obligation with
`current_epoch_priority=true` as a persisted scheduling hint. The selector
places such due obligations in the first practical selection slots. A
fail-closed non-actionable hint does not consume a practical slot. For any
bounded batch larger than one, the final practical slot is reserved for one earliest
breached historical backlog or deep item, so current-epoch debt cannot consume
every opportunity. The remaining historical debt follows the existing profile
deadline order. Before `attempts_started` or `in_flight`, the dispatcher
revalidates the exact capture identity under the persistent queue lock; an
unresolved or stale identity still fails closed. The hint is not a freshness
proof and does not perform capture, discovery, or projection work.

### Review amendment — 2026-08-25

A current-epoch hint can still be non-actionable at the claim boundary when
its exact capture identity is missing, stale, or ambiguous. Treating that
fail-closed refusal as the end of the whole bounded batch created head-of-line
starvation: later actionable current work and the historical heavy reservation
never received a practical slot, while the refused obligation correctly
remained at `attempts_started=0` and `in_flight=false`.

Policy version 6 keeps the same deterministic deadline order, bounded launch
limit, and final breached-heavy reservation. The dispatcher now excludes a
refused queue key only for the current invocation and continues selection. It
recomputes the bounded reservation over the remaining eligible rows, so every
eligible batch under current-freshness pressure can offer a practical slot to
an actionable true-current obligation when one exists. A refusal is visible in
the dispatch result and does not consume a practical launch slot, change retry
timing, increment attempts, set a lease, or bypass the exact identity,
resource, maintenance-lock, or exclusive heavy-lane gates.

The existing profile-specific systemd units remain outside this source-owned
automatic topology. A runtime owner may leave already-disabled legacy files in
place, but only the rendered retry-dispatch pair is eligible for activation by
this route.

This decision supersedes the four-unit activation statement in D-0094 while
preserving its capture-only ingress and separate resource-gated sweep
boundary.

## Rationale

The failure was an activation gap, not a reason to create a second worker.
Making the existing dispatcher source-rendered preserves its queue lock,
restart recovery, identity admission, resource deny/defer/backoff, one-worker
lane, and semantic completion boundaries. A oneshot timer provides a single
outer invocation lane; the worker lock and shared maintenance/heavy leases
remain the internal exclusion boundaries.

The current-epoch hint is derived only from the bounded capture-watch route.
It improves selection without reading raw capture or global state in the
selector. The claim-time identity revalidation prevents a stale hint from
launching old projection work. Historical heavy fairness remains visible and
bounded in every multi-slot dispatch batch, even when current-epoch work is
backlogged.

## Consequences

- Positive: a clean portable export and owner installer now contain the exact
  retry activation topology needed for automatic successor availability.
- Positive: capture remains lightweight, and the retry child still passes
  resource admission, maintenance locking, and heavy-lane exclusion.
- Positive: current-epoch freshness is selected ahead of historical debt while
  every multi-slot batch still reserves one historical heavy opportunity, and
  retry attempts and stale-identity refusal remain restart-safe.
- Positive: one stale or ambiguous current-epoch hint cannot block later
  actionable current work or the reserved historical heavy opportunity in the
  same bounded dispatcher invocation.
- Tradeoff: a rendered unit is still only source/install evidence until a
  runtime owner activates and observes it; scheduled dispatch is not semantic
  freshness.
- Follow-up: live activation, bounded smoke, and final semantic acceptance
  remain separate runtime and independent-review routes.

## Boundaries

This decision does not make a timer trigger, dispatcher claim, child process,
resource admission, checkpoint, or retry receipt into semantic projection
freshness. It does not authorize live systemd mutation, artifact admission,
canonical owner acceptance, or human acceptance. It does not move heavy work
into capture-watch and does not authorize manual queue edits or targeted
projection-catchup proof runs.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `INSTALL.md`
- `docs/decisions/AOA-SM-D-0094-logical-registry-coverage-and-capture-only-ingress.md`
- `docs/decisions/AOA-SM-D-0015-deadline-aware-cooperative-retry-dispatch.md`
- `docs/decisions/`

## Follow-Up Route

Run the owner source, standalone export, artifact trust/admission, and live
unit identity checks. Route the exact source/export/live evidence to an
independent automatic successor availability and semantic acceptance review.

## Verification

Deterministic tests must cover the source-rendered six-unit topology, missing
retry activation files, current-epoch selector priority and bounded-batch
actionability, one-lane exclusion, resource refusal and later resumption,
interrupted claim recovery, and strict current-identity admission. Source
compilation, decision-index regeneration/check, focused retry/identity/systemd
tests, the full owner suite, portable public-safety audit, and live runtime
evidence remain separate claims.
