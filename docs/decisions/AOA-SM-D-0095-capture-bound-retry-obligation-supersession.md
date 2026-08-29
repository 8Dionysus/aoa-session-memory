# Capture-Bound Retry Obligation Supersession

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0095
- Original date: 2026-08-24
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_capture_retry_queue_identity.py`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: raw capture, freshness orchestration, retry queue, recovery
- Projection layers: preserved raw capture, persistent deep retry, stable session projection
- Guard families: capture identity, monotonic supersession, queue lock, crash recovery, fail-closed admission
- Posture: accepted

## Context

Capture publication and deep projection retry are deliberately separate durable
boundaries. A successful append-only capture can therefore publish a newer raw
watermark while the persistent freshness obligation still names the previous
bytes, digest, epoch chain, and raw reference. Launching the old deep work is
not semantic progress for the newly admitted capture, while manually editing
the generated queue would bypass its owner and lose the defect on the next
capture.

The repair must also cover the interval between the two publications. A
dispatcher may claim an older item while capture-watch advances the same
session, and a stale queue writer may race the owner reconciliation.

## Options Considered

- Rewrite the queue from capture-watch or a one-off operator command. Rejected
  because it creates a second writer and cannot preserve queue lock, retry, or
  in-flight semantics.
- Let the next deep child discover the mismatch. Rejected because admission
  would launch work against a stale identity and would make crash recovery
  timing-dependent.
- Let any writer overwrite the required identity. Rejected because a stale
  writer could downgrade a newer admitted capture.
- Reconcile the exact current capture under the persistent queue lock, before
  claim and after capture publication, and reassert an in-flight successor.
  Accepted.

## Decision

The owner binds a strict freshness obligation to the current admitted
append-only capture identity: epoch, epoch order, byte watermark, raw digest
when available, ledger chain root, and canonical `raw-ledger` reference.
Capture-watch invokes owner reconciliation only after releasing the session
capture lock. Reconciliation runs under `auto-maintenance-retry-queue.lock`,
promotes only an equal or newer identity, preserves retry metadata/history/
backoff/exhaustion, and treats repeated equal identity as a no-op.

The dispatcher reconciles strict obligations under the same queue lock before
incrementing attempts or setting `in_flight`. An unresolved or ambiguous
identity returns the exact diagnostic
`capture_retry_queue_identity_reconciliation_unresolved` and refuses deep
admission with
`deep_admission_refused_capture_retry_queue_identity_reconciliation_unresolved`.
It does not consume an attempt or rewrite retry timing. If capture advances
while a child is in flight, the finish boundary cannot retire the item; it
clears the claim, records typed supersession, and leaves the newer obligation
pending.

The durable capture publication remains atomic and unchanged. A crash after
capture state publication but before queue publication is recovered by the
next owner reconciliation, which is idempotent and does not require a manual
queue edit.

## Rationale

The raw capture state and append-only ledger already provide the strongest
admitted capture identity. Making the queue owner re-read that identity at its
existing lock boundary closes the publication gap without adding a second
source of truth or reversing the established capture/queue lock order.

Separating reconciliation, claim, child execution, and finish preserves the
existing retry lifecycle. The strict diagnostic makes missing, corrupt,
ambiguous, or non-current capture evidence visible instead of converting it
into a silent retry or false freshness claim.

## Consequences

- Positive: same-epoch appends, source epochs, crash recovery, and repeated
  owner paths converge to the exact current capture identity.
- Positive: stale writers cannot downgrade an obligation, and in-flight old
  work cannot retire a newer obligation.
- Positive: retry attempts, deadlines, history, and exhaustion remain intact
  except for typed identity supersession transitions.
- Tradeoff: an unresolved capture/ledger mismatch can keep deep work pending
  until an owner path repairs the evidence; this is intentional fail-closed
  behavior.
- Follow-up: independent semantic and lineage review must reproduce the
  strict contract against the exact local commit before any landing route.

## Boundaries

This decision does not make raw capture semantic projection, search freshness,
deep child success, queue presence, or process liveness into owner acceptance.
It does not mutate live `.aoa`, install, activate, export, or authorize a
canonical landing. The queue remains generated coordination state; raw capture
and its ledger remain evidence authority.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_capture_retry_queue_identity.py`
- `tests/test_session_memory.py`
- `DESIGN.md`
- `PIPELINE.md`
- `docs/decisions/AOA-SM-D-0049-append-only-raw-capture-ledger-and-persistent-live-tail-overlay.md`
- `docs/decisions/AOA-SM-D-0057-append-only-capture-ledger-stable-raw-publication.md`
- `docs/decisions/AOA-SM-D-0090-session-freshness-obligations-close-on-watermark-proof.md`
- `docs/decisions/`

## Follow-Up Route

Run the focused identity/retry suite and the existing freshness/capture suites,
then route the exact base/head/tree to a fresh independent semantic and
lineage reviewer. Only after that review may the owner route local landing and
separate runtime deployment/acceptance work.

## Verification

The deterministic regressions cover same-epoch append, new epoch, identical
replay, stale downgrade, concurrent queue mutation, in-flight supersession,
crash-between-publications recovery, and unresolved deep-admission refusal.
Existing retry/freshness/capture-watch/sweep regressions, `py_compile`,
decision-index check, source validation, and `git diff --check` remain the
required local evidence. No canonical or live effect is part of this record.
