# Stage-Scoped Producer ABI and Guarded Predecessor Admission

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0048
- Original date: 2026-08-10
- Owner surfaces: `scripts/aoa_session_memory.py`, `DESIGN.md`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: generation identity, freshness, incremental maintenance, migration
- Projection layers: event classification, session segments, task episodes, session index
- Guard families: producer ABI, dependency DAG, predecessor attestation, fail-closed admission, atomic publication
- Posture: accepted

## Context

The original process-loaded producer identity correctly prevented a source
change during one process from being published as if it were unchanged. It was
too broad as a semantic invalidation key: unrelated edits to the monolithic
producer could make every projection stale. The first projection source-range
contracts reduced that blast radius, but the core dependency graph still bound
classification to the segment generation and segments to task episodes. Those
edges reversed the actual data flow and could turn a local implementation
change into a cold rebuild of classification blocks, segments, episodes, and
every downstream projection.

Changing the dependency graph itself creates new generation IDs even when the
stored projection payload is semantically unchanged. Treating all earlier IDs
as compatible would hide real schema or policy drift; refusing every earlier
ID would discard content-addressed work during the migration.

## Options Considered

- Keep one whole-file producer hash in every semantic generation. Rejected
  because it makes unrelated source edits global invalidations.
- Use hand-maintained version strings without source contracts. Rejected
  because a contributor can change producer behavior without changing the
  version and silently reuse incompatible output.
- Immediately split the entire monolithic producer into physical stage
  packages. Deferred because it is a large topology migration and is not
  required to correct the semantic dependency graph.
- Keep stage-scoped producer contracts, separate the whole-source runtime pin,
  correct the dependency graph, and admit only exact declared predecessor IDs
  through a reuse-then-restamp bridge.

## Decision

Semantic generation identity is stage scoped. The event-classification,
segment-index, task-episode-source, and session-index stages each carry their
own producer contract digest plus their schema, policy, normalization, and
declared upstream generation IDs. The dependency graph follows actual data
flow:

`raw blocks -> event classification -> segment index and task episode source -> session index -> downstream projections`.

The whole loaded source SHA remains a process-stability and atomic-publication
guard. It is not the normal semantic invalidation key for a mapped stage. A
missing, ambiguous, or invalid stage contract falls back to the whole-source
identity and therefore fails closed rather than silently reusing output.

The transition from the 0.7.0 dependency graph uses an in-source allowlist of
exact predecessor generation IDs for only the four affected stages. Admission
does not operate by schema version, prefix, or caller assertion. A matching
predecessor may be reused only when its content-addressed source block or
segment input digest and artifact receipt still validate. The writer then
restamps the artifact with the current generation identity. Unknown IDs and
payload mismatches remain incompatible.

If any predecessor crosses the boundary, the same atomic session manifest
records a deterministic migration receipt. It binds the exact allowed source
IDs and current target IDs, migrated artifact counts by stage, raw source
fingerprint, publish ID, and last-good rollback posture. The staged validator
recomputes the receipt identity and rejects an altered allowlist, target, or
artifact count before publication.

## Rationale

Stage identity keeps invalidation proportional to changed producer semantics.
An explicit DAG makes freshness explainable and prevents downstream code from
invalidating its own upstream inputs. Exact predecessor IDs make the migration
bounded and auditable, while reuse-then-restamp prevents the compatibility
exception from becoming an open-ended reader mode. Raw evidence and artifact
digests still decide whether the reusable payload is the one that was
attested.

## Consequences

- Positive: unrelated producer edits no longer invalidate mapped core stages.
- Positive: classification no longer depends on segment or episode output.
- Positive: old 0.7.0 block and segment work can cross the DAG correction
  without being recomputed when its exact input and artifact receipts match.
- Positive: every actual predecessor crossing is visible in the published
  manifest rather than existing only as an in-process counter.
- Positive: the whole-source mutation check still blocks publication if the
  executable changes during a process.
- Tradeoff: stage source contracts must be updated when producer functions move
  across declared boundaries.
- Tradeoff: every real upstream dependency must be declared; focused tests must
  prove both invalidation and non-invalidation behavior.
- Follow-up: replace range extraction with generated symbol-closure ABI
  manifests as physical producer modules are separated, then retire the 0.7.0
  predecessor allowlist after migration evidence shows no remaining readers.

## Boundaries

This decision does not make raw capture append-only, make task episodes
append-stable, remove eager Markdown rendering, or prove downstream graph,
search, dense, and Atlas freshness. It does not authorize a live `.aoa`
deployment or GitHub publication. A predecessor attestation proves only the
declared generation transition plus matching content receipts; it is not raw
evidence authority or a general compatibility promise.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.md`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Continue with append-only raw block capture and a persistent live-tail overlay,
then move session components to manifest-first incremental publication. Export
only through the owner bundle route after source tests and migration fixtures
pass; validate source, standalone, and installed surfaces separately.

## Verification

Focused tests must prove the corrected dependency edges, unrelated-stage
non-invalidation, exact predecessor admission, unknown-generation refusal,
classification-block reuse with restamping, segment reuse with restamping, and
whole-source mutation refusal. The migration receipt test proves deterministic
identity, exact source/target IDs, stage artifact counts, and no raw-authority
change; staged validation rejects receipt drift. Run decision-index regeneration/check,
`py_compile`, focused pytest, source validation, portable export validation,
and `git diff --check` before local landing.
