# Durable Publication Progress Receipts Survive Timeout

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0092
- Original date: 2026-08-21
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: resumability, projection publication, freshness, orchestration
- Projection layers: session projection, component-delta outbox, maintenance retry
- Guard families: durable atomic write, execution correlation, bounded progress, fail-closed freshness
- Posture: accepted

## Context

Bounded session maintenance can publish one or more atomic projection units
before a cooperative or host hard timeout. The existing child report and
stdout-tail route cannot prove that mutation when the launcher terminates the
child or the final stdout is absent. Treating the whole attempt as having no
progress makes continuation repeat completed work and obscures the retry
obligation. Treating the timeout as success would overclaim child completion
and global freshness.

## Options Considered

- Keep stdout and child reports as the only mutation evidence. Rejected because
  a timeout can remove the only transport carrying an already-committed
  publication.
- Infer progress from a checkpoint or process exit. Rejected because a
  checkpoint is resumability state and process exit is transport state; neither
  binds a completed atomic publication to this execution.
- Persist an execution-correlated receipt immediately after atomic publication
  and recover it after timeout while retaining retry and freshness claims.

## Decision

After a session projection atomically publishes its new generation and writes
the component-delta outbox record, it durably writes a compact progress
receipt. The receipt binds the maintenance execution ID, session ID and label,
work ID, publish identity, source watermark, outbox identity, and required
consumer set. The outer resource launcher searches only the exact execution
receipt directory and target scope when child stdout or the child result is
missing.

Recovered receipts are reported as bounded publication progress. The result
keeps `child_result_verified` and process completion false, schedules or
retains the retry obligation, and leaves global freshness unresolved until a
later run proves the required watermark. Checkpoint, cache-index, and retry
queue state use durable atomic writes so continuation can reuse completed
segments and avoid restarting the bounded session work.

## Rationale

The publication boundary is the strongest local evidence available after a
child transport disappears. Correlation prevents a receipt from an unrelated
run or session from being promoted into evidence for the current timeout.
Keeping the recovered-progress, child-completion, and freshness claims
separate preserves the fail-closed contract while making already-published
work resumable. A durable receipt is intentionally compact and bounded; it is
not a second projection or a replacement for the authoritative manifest,
outbox, consumer acknowledgements, or watermark proof.

## Consequences

- Positive: a timeout with absent stdout can recover exact publication evidence
  and continue from the durable checkpoint.
- Positive: retry and freshness obligations remain visible instead of being
  retired by a transport-level success or erased by a transport-level failure.
- Tradeoff: receipts add a small durable diagnostic store and require execution
  ID propagation through the normal maintenance route.
- Follow-up: extend correlation to any separately owned custom launcher route
  only when that route can carry and preserve the same execution identity.

## Boundaries

This decision does not prove that the child reached normal completion, that
all requested sessions were processed, that required consumers acknowledged
the outbox, or that global freshness is current. It does not authorize live
deployment, repair of the installed `.aoa` organ, or remote/GitHub mutation.
Explicit custom child commands that do not carry the execution identity remain
outside receipt recovery and retain their existing unverified timeout posture.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Run the focused resumability and resource-timeout regressions, decision-index
generation/check, and the ordinary owner validation route. The Goal master
owns integration, deployment, live runtime proof, and acceptance.

## Verification

The focused suite covers durable checkpoint continuation after an injected hard
timeout, recovery from absent child stdout, repeated continuous-session
freshness, and a bounded retry queue. Source compilation and decision-index
validation are required before local handoff. Live installed-runtime state and
remote/GitHub state remain read-only and are not presented as verified here.
