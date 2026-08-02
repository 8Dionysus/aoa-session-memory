# Served-Request Health Is Distinct from Provider Availability

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0040
- Original date: 2026-07-31
- Owner surfaces: `scripts/aoa_session_memory.py`, `READINESS.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: semantic retrieval, optional host acceleration, provider status, orchestration, evidence provenance
- Projection layers: provider status packet, episode dense generation preflight, compact retrieval route packet
- Guard families: real-request admission, provider fallback, model contract, freshness honesty, privacy-safe health
- Posture: accepted

## Context

An optional semantic provider can pass process, capability, model-registration,
quality, and HTTP health gates while its first real embedding request still
fails. A status packet that reports only those availability gates cannot tell
an orchestrator whether the provider has actually served the selected
workload.

Episode-dense generation already runs a real, dimension-checked embedding
preflight before attributing failures to individual sessions. The generic
provider-status surface did not expose the same distinction, so `ready` could
be misread as served-request health.

## Options Considered

- Treat capability, model, and health endpoints as sufficient readiness.
  Rejected because none exercises the complete request route.
- Run and persist a real probe automatically on every status read. Rejected
  because an optional host accelerator must not create hidden cost, and an old
  success must not become reusable current truth.
- Collapse a failed real request into the model or process status. Rejected
  because availability and request serving are different observations with
  different recovery routes.
- Add an explicit, one-request probe whose non-reusable result is reported
  separately and fail the explicitly probed provider on request failure or
  model-contract drift.

## Decision

Search-provider status has a versioned `served_request_health` contract
separate from capability, quality, model, and health-endpoint availability.

Without an explicit served-request probe, the field reports `unobserved` and
must not be interpreted as request health. `search-provider-status
--include-host --probe-served-request` makes exactly one bounded embedding
request through the same model-and-dimension preflight used at dense
generation boundaries.

A successful request reports `served`. A transport or provider failure
reports `failed`; an unexpected model or dimension reports `contract_drift`.
The latter two states make the explicitly probed provider unavailable even
when its process and model gates remain green.

The observation is current only within that status invocation and declares
that it cannot be reused. It records the provider, observation time, expected
and observed model and dimension, elapsed time, and a bounded diagnostic
class. It does not record the probe text, embedding vector, response body, or
new host path.

## Rationale

This preserves two facts instead of forcing one to overwrite the other: a
provider can be registered and reachable yet unable to serve a real request.
An explicit probe avoids hidden accelerator work while giving generation and
fallback orchestration a common, inspectable contract when stronger runtime
evidence is required.

Non-reuse prevents a successful probe from becoming a stale green receipt.
Privacy-bounded diagnostics keep the agent-facing packet useful without
copying provider payloads or host internals into portable session memory.

## Consequences

- Positive: availability can no longer be mistaken for observed request
  serving in provider packets.
- Positive: an explicitly observed failure or model-contract drift blocks a
  green provider result.
- Positive: dense generation retains its existing real-request preflight and
  no vector or raw evidence migration is required.
- Tradeoff: callers that need served-request evidence pay for one explicit
  embedding request.
- Tradeoff: the observation is deliberately non-reusable; later routing may
  require a new probe at a new admission boundary.

## Boundaries

A served probe is routing evidence, not proof of semantic quality, ranking
quality, index freshness, or answer correctness. It does not make an optional
host backend authoritative and does not replace raw/session refs, gold-first
evaluation, or claim admission.

The decision does not require a particular vector backend, does not persist
provider health as owner truth, and does not change portable SQLite behavior.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `READINESS.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Reopen this decision if measured probe cost requires a bounded cache with an
explicit generation and expiry contract, or if another provider workload
needs its own real-request admission shape. Do not generalize an embedding
success to reranker, graph, or answer-admission health.

## Verification

Sealed scenarios cover unobserved, served, failed, and model-contract-drift
states plus compact-packet privacy. Focused tests require all states to remain
distinct, and a real local provider invocation must return the expected model
and 1024-dimensional vector before the route can report `served`.
