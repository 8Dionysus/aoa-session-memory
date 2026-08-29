# Terminal Outbox Retirement and Staged Freshness Retry

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0099
- Original date: 2026-08-26
- Owner surfaces: `scripts/aoa_session_memory.py`, `schemas/projection-outbox-retirement.schema.json`, `DESIGN.md`, `DESIGN.AGENTS.md`, `PIPELINE.md`, `INSTALL.md`, `READINESS.md`, `tests/test_session_memory.py`
- Surface classes: projection outbox, freshness orchestration, terminal proof
- Projection layers: episode semantic, exact search, entity registry, graph
- Guard families: immutable work intent, exact completion receipt, retirement binding, staged retry
- Posture: accepted

## Context

The changed-component outbox is an immutable work-intent record, while each
downstream consumer records mutable progress. A consumer state marked complete
and a successful retry launcher do not, by themselves, prove that every
required consumer completed the same current publication. Releasing a
persistent freshness obligation at the capture/stable/search boundary can
therefore leave entity, graph, or terminal work pending and make the remaining
causal pressure invisible.

## Options Considered

- Treat all complete consumer states as terminal and remove or rewrite the
  outbox record. Rejected because it loses the immutable work-intent boundary
  and cannot bind release to exact receipt identity.
- Add a manual drain or sweep after projection. Rejected because automatic
  freshness must not depend on an operator-only state mutation, and a timer or
  launcher result is not semantic completion.
- Keep the immutable record, write a receipt-gated append-only retirement
  artifact, and carry the same retry obligation from projection to downstream
  consumers. Accepted.

## Decision

The owner keeps every changed-component outbox record immutable and pending as
historical work intent. After every declared consumer has a current exact
completion receipt bound to the record and publication, the owner may write one
append-only terminal-retirement artifact containing the required-consumer set
and completion-receipt digests. Readiness and persistent retry release require
that artifact; missing, malformed, or mismatched retirement remains pending.

When a persistent freshness obligation owns a current outbox, automatic retry
uses two stages. The projection stage advances the capture/stable/search
watermark. It then preserves and atomically retargets the same queue item to a
downstream stage, which runs the existing entity-registry and graph guards and
attempts terminal retirement. Partial progress, admission refusal, child
failure, or unverified execution never clears the item.

## Rationale

The receipt and retirement boundary makes terminality reconstructible without
editing generated work state. The staged route matches the actual dependency
order: entity and graph may remain blocked by their own current registry,
search, ledger, generation, or resource requirements after projection succeeds.
Keeping those stages visible allows fairness and capacity evidence to be
measured independently while preserving raw fallback and fail-closed identity
and freshness semantics.

## Consequences

- Positive: terminal release is bound to exact consumer evidence and one
  current publication.
- Positive: projection success cannot hide downstream backlog or graph/entity
  admission pressure.
- Tradeoff: the immutable outbox directory remains historical evidence and
  needs a separate retirement read model.
- Follow-up: runtime acceptance must compare arrivals, required-consumer
  retirements, current-work service, slope, headroom, and raw-serving latency
  across bounded natural windows.

## Boundaries

This decision does not make an outbox record, consumer state, retirement
artifact, timer, child result, or queue count proof of global semantic
freshness by itself. It does not weaken current registry/search/graph guards,
authorize manual queue or raw edits, or prove full historical drain. Runtime
identity, portable trust admission, live installation, and independent owner
acceptance remain separate evidence classes.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `schemas/projection-outbox-retirement.schema.json`
- `DESIGN.md`
- `DESIGN.AGENTS.md`
- `PIPELINE.md`
- `INSTALL.md`
- `READINESS.md`
- `tests/test_session_memory.py`

## Follow-Up Route

Run source compilation, focused and full owner tests, decision-index checks,
portable export/public-safety and artifact-trust admission, checkpointed live
install with exact unit activation, then collect bounded natural runtime proof
before independent acceptance.

## Verification

Focused tests cover receipt-gated retirement, replay idempotency, immutable
outbox preservation, and projection-to-downstream retry handoff. Source,
portable, live, throughput, raw-serving, and independent-acceptance evidence
remain separate claims in the actor report.
