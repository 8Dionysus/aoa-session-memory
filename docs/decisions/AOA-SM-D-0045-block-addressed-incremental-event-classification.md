# Block-Addressed Incremental Event Classification

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0045
- Original date: 2026-08-09
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `DESIGN.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: session indexing, freshness, incremental maintenance, privacy, orchestration, resource control
- Projection layers: raw event classification cache, session segments, session index
- Guard families: raw authority, content identity, cooperative deadline, privacy, deterministic parallelism, atomic publish
- Posture: accepted

## Context

Content-addressed segment checkpoints removed repeated segment generation, but
large event-dense sessions still classified the complete raw stream and rebuilt
the ephemeral sensitive-literal policy before the first durable checkpoint.
A 566 MB live archive spent more than twelve minutes in classification alone,
so repeated bounded heavy slices could consume their whole budget without
recording reusable progress. Growth also repeated classification of an
unchanged prefix.

## Options Considered

- Increase the heavy-lane timeout. Rejected because interruption and ordinary
  session growth would still repeat total-history work.
- Persist complete `RawEvent` objects, parsed payloads, or sensitive literals.
  Rejected because this duplicates raw evidence and expands the credential and
  privacy surface.
- Checkpoint only after whole-session classification. Rejected because it does
  not handle the observed pre-checkpoint bottleneck.
- Classify append-stable content-addressed raw blocks in a bounded process pool,
  persist only derived classification fields, and reconcile globally after
  deterministic rehydration.

## Decision

Raw snapshot scanning and work identity now precede classification. The raw
stream is divided into append-stable blocks bounded by line count and bytes;
each block is addressed by its exact byte digest and line range. Classification
runs in deterministic bounded waves with one through six process workers and
records an atomic checkpoint after each completed block.

The persistent cache contains only derived classification fields. It excludes
raw text, parsed payloads, and sensitive-literal values. Cache generation is
bound to the classifier, privacy, and redaction contract. Rehydration rereads
raw authority, verifies block bytes and cache receipts, reconstructs events,
and applies whole-session correlation reconciliation in canonical line order.

Sensitive-literal discovery may scan raw blocks in parallel, but exact values
exist only in process memory and merge into the existing ephemeral policy.
They are never serialized. This ephemeral scan precedes any classification
cache emission, and reused prefix artifacts are scrubbed again under the
current whole-session policy before admission. A source-growth rebuild can
reuse sealed prefix blocks from the published projection or another compatible
work directory and rebuild only the changed tail. Final source-drift validation
performs a cheap raw scan rather than a second full classification.

The classification cache publishes atomically with the projection but remains
a rebuildable acceleration layer. It is excluded from the semantic projection
digest and never substitutes for raw evidence or published freshness.

## Rationale

The correct restart boundary is the first expensive deterministic unit, not the
first downstream artifact. Content-addressed blocks make cost proportional to
changed raw bytes while preserving global reconciliation and atomic reader
semantics. Keeping raw and secret values out of the cache preserves the
existing authority and privacy boundary.

## Consequences

- Positive: a bounded slice records classification progress before segment
  generation begins.
- Positive: growing sessions reuse stable classified prefixes.
- Positive: classification and sensitive scanning can use bounded host CPU
  parallelism.
- Positive: pre-publish validation no longer repeats classification.
- Tradeoff: published and resumable work trees retain a small derived cache.
- Tradeoff: global correlation reconciliation and raw rehydration remain a
  deterministic whole-session pass.

## Boundaries

A valid classification cache proves only derived fields for exact raw block and
producer identities. It does not prove publication, search or graph freshness,
or semantic correctness of owner data. Cache corruption, generation drift, or
raw mismatch fails closed and preserves last-good. This decision does not allow
raw rewriting, mixed-generation publication, persistent sensitive literals, or
bypassing host resource admission.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `DESIGN.md`
- `docs/decisions/`

## Follow-Up Route

Measure cold serial, cold parallel, interrupted resume, and append-growth runs
on representative and live large sessions. Calibrate block size and worker
count from wall time, CPU, RSS, I/O, and semantic-parity receipts.

## Verification

Tests cover serial/parallel semantic parity, classification interruption and
resume, append-stable prefix reuse, generation invalidation, raw digest
preservation, and absence of a synthetic credential from persisted cache
payloads. Full source validation and target-host live freshness proof remain
required before rollout completion is claimed.
