# Bounded Fair Consumer Retirement Admission

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0100
- Original date: 2026-08-26
- Owner surfaces: `scripts/aoa_session_memory.py`, `schemas/`, `tests/`, `docs/decisions/`
- Surface classes: projection outbox, freshness orchestration, scheduling, evidence boundary
- Projection layers: exact search, episode semantic, entity registry, graph
- Guard families: fair scheduling, restart safety, immutable identity, fail-closed admission, terminal retirement
- Posture: accepted

## Context

The terminal-retirement contract in AOA-SM-D-0099 correctly keeps the
component outbox immutable and requires exact receipts from every required
consumer.  Its bounded selector nevertheless allowed newest records and a
blocked consumer lane to dominate the practical selection window.  A child
that committed an authoritative consumer artifact before its process result
was observed could also leave the receipt reconciliation deferred.  Invalid
or superseded historical records must remain visible without consuming valid
consumer service or being rewritten.

## Options Considered

- Keep newest-first global selection and rely on retry order. Rejected because
  retry fairness does not schedule the component outbox or separate consumer
  lanes.
- Mark missing or blocked consumer state complete during reconciliation.
  Rejected because missing state and transport success are not semantic proof.
- Add an owner-scoped, oldest-pending round-robin selector with a durable
  cursor, consumer-specific lanes, exact admission diagnostics, and an
  unverified-child receipt recheck. Accepted.

## Decision

The owner selects one current publication per session only after checking the
content-addressed outbox identity, authoritative path, current manifest
publication, and owner-root binding. Selection is ordered by deterministic
publication age and rotated by a durable per-consumer or global cursor. A
consumer-specific pass admits only records pending for that consumer, so a
blocked graph or registry dependency cannot consume another lane's bounded
slots. Cursor state is scheduler metadata only; malformed cursor state blocks
selection rather than being silently replaced.

Superseded, malformed, or owner-unbound records are reported as admission
blocks and left unchanged. Current records with missing consumer state remain
pending work and are not promoted. Completion receipts retain immutable
record/session/publication identity, and optional identity fields inside a
receipt must agree with the state binding. The convergence postpass rechecks
exact persisted consumer artifacts even when the child return is unverified;
it never treats that return as semantic evidence.

## Rationale

The cursor makes bounded progress independent of wall-clock restart and
prevents a repeatedly blocked head record from monopolizing a lane. Consumer
scoping preserves dependency order while allowing independent lanes to make
progress. Recomputing current identity at selection and completion preserves
the source-to-live fence, while durable cursor writes are atomic and
reconstructible. Keeping invalid records visible preserves evidence and makes
the safe quarantine posture reviewable without destructive cleanup.

## Consequences

- Positive: continuous arrivals cannot permanently displace older admitted
  work, and a blocked lane cannot starve another required consumer.
- Positive: a restart resumes from a durable cursor and exact receipt state;
  replay remains idempotent.
- Positive: malformed legacy work is skipped with explicit diagnostics rather
  than rewritten or counted as completion.
- Tradeoff: each bounded selection scans current outbox metadata and keeps a
  small generated scheduler state beside the immutable records.
- Follow-up: runtime acceptance must still measure natural arrivals,
  per-consumer terminal retirements, capacity, backlog slope, headroom, and
  concurrent bounded serving.

## Boundaries

This decision does not make scheduler state, consumer state, a child result,
an active timer, or a receipt count proof of global semantic freshness. It
does not authorize queue, outbox, raw, lease, generated-index, or runtime
state surgery, and it does not replace independent source, portable, trust,
deployment, runtime, or owner acceptance evidence.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `schemas/projection-outbox.schema.json`
- `schemas/projection-outbox-retirement.schema.json`
- `schemas/projection-outbox-fairness.schema.json`
- `tests/test_session_memory.py`
- `docs/decisions/AOA-SM-D-0099-terminal-outbox-retirement-and-staged-freshness-retry.md`

## Follow-Up Route

Run the owner source suite and decision-index checks, export through the
portable owner route, pass public-safety and artifact trust admission, install
with a checkpoint, and collect a fresh no-manual natural convergence window
for independent acceptance review.

## Verification

Focused regressions cover all four consumer identities, fair rotation under
continuous arrivals, restart persistence, invalid-record admission, receipt
identity conflicts, exact retirement, and receipt reconciliation after an
unverified child. Full owner tests, source/export validation, trust and
checkpointed activation, and natural runtime evidence remain separate gates.
