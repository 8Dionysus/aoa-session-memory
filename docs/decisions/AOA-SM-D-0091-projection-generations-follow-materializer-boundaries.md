# Projection Generations Follow Materializer Boundaries

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0091
- Original date: 2026-08-21
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: projection generation, freshness, incremental maintenance, performance
- Projection layers: task episode source, session index, episode semantic, graph
- Guard families: bounded producer contract, dependency generation, declared predecessor, reuse then restamp, fail-closed admission
- Posture: accepted

## Context

Projection generation identities are intended to invalidate derived data only
when the code that defines that projection's semantics changes. The
`task_episode_source` producer contract used one broad source range beginning
at task-episode lineage and ending at goal fields. Transcript discovery,
capture, import, and sweep orchestration happened to sit inside that range.
Consequently, an orchestration-only freshness repair changed the task-episode
generation and cascaded into session-index, episode-semantic, and graph debt
even though no task-episode materializer behavior changed.

This is not a data-volume problem. It is an incorrect dependency edge between
orchestration and projection semantics.

## Options Considered

- Keep the broad range and accept full downstream convergence after unrelated
  maintenance changes. Rejected because the rebuild does not prove a semantic
  change and makes routine freshness repair create new historical debt.
- Bind every projection to the whole producer file. Rejected because the
  monolithic CLI contains many independent owners and would make unrelated
  edits invalidate every derived surface.
- Remove producer code from generation identities. Rejected because schema and
  constants alone cannot prove that materializer semantics stayed unchanged.
- Split the task-episode producer contract into narrow materializer ranges and
  admit only exact reviewed predecessor generations through the existing
  reuse-then-restamp route.

## Decision

Projection producer contracts follow the smallest source ranges that own the
materialized value. The task-episode contract covers task-episode lineage and
the task-episode builder/materializer functions; it excludes transcript
discovery, capture, import, sweep, retry, and resource orchestration.

Changes outside those ranges must leave the task-episode producer digest
unchanged. Changes inside them must advance the digest. The generation DAG may
then propagate only that real semantic change to session-index,
episode-semantic, and graph consumers.

The exact task-episode generation accidentally published by the freshness
repair is a declared predecessor. It may be reused only through the existing
artifact, dependency, raw-input, and publication proofs and then restamped to
the corrected generation. Unknown identities remain incompatible.

## Rationale

The source contract is evidence for a projection implementation, so its
boundary should mirror the claim being proved. A narrow contract preserves
fail-closed invalidation when materializer behavior changes while preventing
capture scheduling or retry policy from manufacturing semantic debt. Exact
predecessor admission preserves already-proved artifacts without turning the
fix into a broad compatibility claim.

## Consequences

- Positive: sweep, retry, hook, and resource-control changes no longer
  invalidate task episodes, episode semantic search, or graph through an
  accidental source-range edge.
- Positive: real task-episode materializer edits still advance the dependency
  DAG and invalidate affected consumers.
- Positive: the transition can reuse exact current artifacts instead of
  forcing a cold core rebuild.
- Tradeoff: source-range anchors are an explicit ABI map and require regression
  tests when code is moved across their boundaries.
- Follow-up: apply the same bounded-range audit whenever a projection changes
  after an edit outside its semantic owner, but do not declare compatibility
  without exact predecessor and artifact proof.

## Boundaries

This decision does not declare existing search or graph debt current, prove
that every historical generation is compatible, remove schema-version
invalidation, or make generated projections authoritative. It does not weaken
the process-loaded whole-source stability check used to prevent publication
from code that changed during a writer process.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Run focused generation tests, the full owner suite, source validation, clean
portable export, and standalone validation. Install only through the owner
installer, then compare live generation identities and freshness obligations.

## Verification

Regression tests mutate sweep-only source bytes and require the task-episode
producer digest to remain identical. Existing contract tests still require a
materializer-range change to alter the owning digest, and predecessor tests
retain exact identity reconstruction and fail-closed unknown-generation
behavior.
