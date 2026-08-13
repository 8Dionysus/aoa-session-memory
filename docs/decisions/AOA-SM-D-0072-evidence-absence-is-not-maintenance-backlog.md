# Evidence Absence Is Not Maintenance Backlog

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0072
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: route readiness, automatic maintenance, retry queue, freshness orchestration
- Projection layers: route readiness, agent atlas, search index, entity registry, graph
- Guard families: structural readiness, evidence absence, bounded retry, post-maintenance proof
- Posture: accepted

## Context

Route readiness asks whether a selected session scope contains evidence for a
set of operational layers. A valid, current route index can honestly contain
no `goal`, `external_snapshot`, or `operator_preference` signal. The readiness
report correctly preserves that evidence gap, but automatic maintenance used
the report's total remaining count as retry work. Repeating the same bounded
index and graph cycle cannot create evidence that the source sessions do not
contain, so the persistent retry queue never converges.

Bounded maintenance also labels global derivatives deferred while its final
owner-level freshness probe may subsequently prove the search, atlas, entity
registry, and graph current. Retrying only because the earlier bounded planner
could not make that global claim repeats already completed work.

## Options Considered

- Make all intermittently absent route layers optional. Rejected because the
  readiness report would stop exposing meaningful evidence gaps.
- Keep retrying until a future session happens to contain every layer.
  Rejected because maintenance cannot manufacture source evidence and the
  retry lifetime would depend on unrelated future work.
- Treat every readiness failure as observational only. Rejected because
  missing axes, missing generated indexes, stale session route indexes, and an
  unavailable search provider are actionable projection failures.
- Preserve evidence gaps in readiness while separating them from structural
  repair work, and let a fresh post-maintenance proof retire a bounded global
  derivative deferral.

## Decision

Route readiness classifies its remaining requirements. Missing source axes,
missing generated axes, failed global gates, and diagnostics are actionable
and recommend retry. A required route layer with zero signals in the selected
source scope, while its source and generated axes are current, remains visible
as an evidence absence and does not recommend maintenance retry.

Automatic maintenance consumes the explicit `retry_recommended` field when
present. Compatibility with older action packets is retained through the
previous remaining-count fallback.

A bounded global-derivative deferral remains retryable until the coordinator's
fresh post-maintenance probe proves the index surface current with no
diagnostics. That later owner proof may retire the earlier planning deferral;
the bounded planner itself still does not claim global completion.

## Rationale

This keeps readiness honest without confusing corpus content with projection
health. Persistent retry is reserved for work a maintenance action can change.
The post-maintenance owner probe remains stronger than an earlier bounded
planning observation, so accepting it avoids redundant heavy cycles without
weakening freshness gates.

## Consequences

- Positive: a stable corpus converges instead of retrying forever for absent
  semantic categories.
- Positive: genuine structural readiness failures remain retryable.
- Positive: a verified current post-state retires stale bounded-planner
  deferrals in the same owner cycle.
- Tradeoff: readiness can be `ok: false` for an evidence gap while automatic
  maintenance is complete; callers must inspect `retry_recommended` rather
  than equating every coverage gap with repair work.

## Boundaries

This does not mark absent evidence present, weaken a missing-axis or stale
provider failure, infer source semantics, or let a bounded planner claim
global freshness. New source evidence still enters through ordinary capture
and projection routes.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Observe a live bounded cycle whose only route-readiness remainder is semantic
absence. Verify the successor retry is cleared while the readiness report
continues to expose the absent layers.

## Verification

Run decision-index regeneration/check, `py_compile`, focused route-readiness
and automatic-maintenance tests, source validation, live source parity, and a
normal retry-dispatch cycle ending without a false successor.
