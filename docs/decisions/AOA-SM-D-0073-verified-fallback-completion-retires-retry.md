# Verified Fallback Completion Retires Retry

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0073
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: automatic maintenance, resource fallback, retry queue, completion semantics
- Projection layers: search index, graph
- Guard families: child result verification, bounded fallback, zero remaining work, retry convergence
- Posture: accepted

## Context

The primary automatic-maintenance resource route may be denied while its
smaller index-drip or graph-drip fallback is admitted. The fallback can finish
all actionable work, but the wrapper and retry dispatcher historically
verified only the denied primary child. They therefore reported the bounded
fallback as control-flow progress and scheduled the already completed work
again.

## Options Considered

- Treat every successful fallback process exit as final completion. Rejected
  because exit status alone does not prove the child result or post-run state.
- Keep every resource-blocked wrapper retryable regardless of fallback result.
  Rejected because verified zero-backlog work would never converge.
- Accept a fallback as final only when its typed child result is verified and
  its post-run state proves that no bounded work remains.

## Decision

A completed index-drip or graph-drip fallback is semantic maintenance success
only when the fallback result is verified, the child artifact has the expected
owner type and reports success, and the fallback's post-run evidence reports
`remaining_work=false`.

The wrapper exposes that proof as verified overall completion. Periodic retry
reconciliation and the persistent retry dispatcher clear the matching intent.
A fallback with remaining work stays progress-and-retry; an untyped,
unverified, failed, or ambiguous fallback cannot retire the queue item.

## Rationale

Completion belongs to verified owner evidence rather than to the resource
route that happened to run it. This lets bounded fallbacks converge under host
pressure while preserving the same fail-closed standard used for a primary
maintenance child.

## Consequences

- Positive: a fallback that drains its scope does not recreate its own retry.
- Positive: partial graph or index progress remains resumable.
- Positive: the retry dispatcher accepts a verified fallback child without
  misclassifying the denied primary route as an unverified result.
- Tradeoff: older or minimal fallback packets without typed child proof remain
  retryable until a current owner run produces verifiable completion evidence.

## Boundaries

This does not treat resource admission, process exit, fallback progress, or an
empty diagnostic list alone as completion. It does not clear another profile's
intent or claim that continuously arriving live sessions have stopped.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Run the ordinary resource-blocked graph fallback against the current generated
ledger, then inspect its typed child, remaining-work proof, and persistent retry
queue reconciliation.

## Verification

Run focused fallback and retry-dispatch regressions, decision-index
regeneration/check, `py_compile`, source validation, live source parity, and a
normal fallback cycle that reaches zero actionable graph work and clears its
retry intent.
