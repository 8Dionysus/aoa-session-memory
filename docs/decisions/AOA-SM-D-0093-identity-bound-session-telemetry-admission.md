# Identity-Bound Session Telemetry Uses Owner Receipt Admission

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0093
- Original date: 2026-08-22
- Owner surfaces: `scripts/identity_bound_session_telemetry.py`, `scripts/profile_session_stages.py`, `schemas/identity-bound-session-telemetry.schema.json`, `PIPELINE.md`, `tests/test_identity_bound_session_telemetry.py`, `docs/decisions/`
- Surface classes: instrumentation, evidence intake, projection, freshness, resource control, privacy
- Projection layers: capture-time envelope adapter, post-hoc stage projection, identity-bound evidence packet
- Guard families: exact source identity, session binding, projection currentness, correlation completeness, cache posture, resource posture, tamper rejection, privacy
- Posture: accepted

## Context

Session stage projection can provide bounded structured spans while a capture
ledger is ahead of the readable projection. A validation owner can separately
observe workload, candidate, source, environment, treatment, evidence,
acceptance, cache, resource, and first-failure-to-rerun identities. Without a
typed join, a readable stage projection can be mistaken for a comparable
validation run, or missing resource and correlation evidence can be silently
treated as zero or complete.

The session-memory owner must preserve this evidence boundary without taking
ownership of validation semantics, reading private operation bodies, or making
an effectiveness or evaluator claim.

## Options Considered

- Capture every identity and timing value in the generic foreground hook.
  Rejected because the hook does not own validation identity and expanding its
  payload would couple privacy and latency to an external owner.
- Infer identity and trajectory from post-hoc session events.
  Rejected because operation text and structured spans do not establish the
  external candidate, environment, cache, resource, or acceptance identity.
- Admit a public-safe external owner receipt through an exact
  session/source/projection join, while retaining optional capture facets and
  post-hoc unknowns.

## Decision

The session-memory adapter accepts a typed
`validation_owner_telemetry_receipt_v1` only when its digest, session binding,
source identity, and declared projection coordinates match the expected
context. It emits an `identity_bound_session_telemetry_v1` packet with explicit
field states for known, missing, unknown, unobservable, null, and excluded
evidence.

The capture-time route is limited to a dedicated structured facet and never
parses generic command, message, or result bodies. The post-hoc route reads
generated indexes for correlated call-to-result spans and preserves unknown
timing and resource states. Pair comparison is an admission result only: it
requires exact identity, current projection, reviewed trajectory, complete
correlation, and non-partial cache/resource posture, then returns no effect or
verdict.

## Rationale

The owner receipt carries the facts that session memory cannot safely infer.
Exact source and projection joins prevent stale or wrong-candidate evidence
from entering a comparison cohort. Keeping capture, post-hoc projection, and
owner federation as separate methods makes the provenance of each field
visible. Compact refs and typed scalar fields preserve portability and privacy,
while explicit exclusions keep missing CPU, RSS, I/O, cache, or trajectory
evidence from becoming false zeros or causal claims.

## Consequences

- Positive: identity-bound packets can be produced even when the projection is
  stale-readable, with the freshness boundary retained.
- Positive: tampered, partial, wrong-environment, and incomplete-correlation
  inputs fail closed without exposing private bodies.
- Tradeoff: no packet becomes a comparison pair without a reviewed external
  owner receipt and current projection context.
- Follow-up: the validation owner must publish matching receipts and own any
  effect, causal, proof, or acceptance evaluation.

## Boundaries

This decision does not validate a workload, measure effectiveness, establish
causality, issue an evaluator verdict, prove acceptance, or make the external
owner's receipt authoritative for session truth. It does not make the generic
hook a validation collector, read raw session bodies, refresh stale
projections, or authorize heavy maintenance. A packet or admission result is
not live runtime health or human acceptance.

## Source Surfaces

- `scripts/identity_bound_session_telemetry.py`
- `scripts/profile_session_stages.py`
- `schemas/identity-bound-session-telemetry.schema.json`
- `PIPELINE.md`
- `tests/test_identity_bound_session_telemetry.py`
- `docs/decisions/`

## Follow-Up Route

Use the owner validation receipt route for fresh resource admission, reviewed
trajectory, and any comparison or evaluator decision. Use the session-memory
bounded-prefix route for currentness and projection evidence; defer heavy
catch-up when its resource gate is not freshly admitted.

## Verification

Focused adapter and stage-profile tests cover missing versus unobservable
states, exact source/session binding, wrong candidate and environment,
stale-readable projection, partial cache, incomplete correlation, digest
tamper, private-field rejection, dedicated capture facets, and portable JSON
schema parity. Source compilation and decision-index regeneration/check are
required. Live projection freshness, external owner receipts, comparison
cohorts, evaluator verdicts, and human acceptance remain separate gates.
