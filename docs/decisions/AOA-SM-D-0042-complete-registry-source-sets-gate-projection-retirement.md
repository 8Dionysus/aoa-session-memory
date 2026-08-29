# Complete Registry Source Sets Gate Projection Retirement

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0042
- Original date: 2026-08-01
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `READINESS.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: indexing, freshness, deletion, migration, automatic maintenance, evidence preservation
- Projection layers: portable search, exact literal postings, episode semantic, episode dense, search shards, agent atlas, session graph
- Guard families: complete source set, tombstone receipt, deep rebuild fallback, bounded catch-up, answer admission, raw preservation
- Posture: accepted

## Context

Per-session fingerprints prove whether a selected source changed, but they do
not prove that the selected batch is the complete owner set. After a session
was removed from the owner registry, its generated search, exact, episode,
Atlas, shard, and graph rows could remain physically present. A bounded
freshness check saw only the surviving selection and could report the global
projection as current; exact and episode readers could then return candidates
from the retired source.

Treating every session absent from one bounded batch as deleted would be worse:
hot and catch-up selection intentionally omit most valid archive sessions. The
system therefore needs an explicit distinction between batch coverage and a
complete owner source set.

## Options Considered

- Delete generated rows whenever a session is absent from the current batch.
  Rejected because bounded discovery is not an owner deletion statement and
  would silently destroy valid recall.
- Leave old rows readable until periodic cleanup. Rejected because a stale
  generated candidate could be mistaken for current evidence after the owner
  source was retired.
- Delete the session directory and raw transcript together with projections.
  Rejected because projection lifecycle never owns raw evidence destruction
  and provenance must survive retirement.
- Persist a versioned complete source-set identity in the monolith projection,
  compare it with the complete owner registry, fail closed on removals, and
  route coherent projection replacement to the deep profile.

## Decision

A valid `session-registry.json` with a `sessions` list is the complete owner
selection for projection lifecycle. A full all-session search build records a
versioned, deterministic identity of that set. Incremental and bounded builds
may add selected current sessions to the stored identity, but they never infer
deletion from omission.

When an ID present in the stored projection source set is absent from the
complete current registry, search, exact, episode semantic, and dense readers
withhold generated candidates and return an explicit deep-rebuild route.
Legacy databases without source-set metadata compare their persisted
per-session projection states with the complete registry; a missing or invalid
registry makes the lifecycle claim unproven rather than inventing deletion.

Removal requires a clean, atomic replacement of the monolith database. That
replacement also removes its exact, episode, dense, entity-posting, and queue
rows. Existing monthly shards are rebuilt from the current owner set; catalog
construction refuses to recover shard-only rows absent from the complete
registry. Atlas uses the same complete-registry retirement test and cleans its
publish set. Graph maintenance receives a global current selection so orphaned
source contributions are removed.

Bounded non-deep profiles invoke none of those clean producers. They report
the tombstoned session IDs, keep the read gate closed, and return the exact
resource-owned `auto-maintenance deep all` command. Deep work remains
cooperatively budgeted and publishes only completed stores.

A tombstone is a generated retirement receipt naming the removed projection
state and its provenance. It is not an archive deletion or a new source of
truth. Removing the last registry session may publish an authoritative empty
source set and empty search catalog. Reintroducing the preserved owner record
is an addition/correction: bounded indexing can add it back without rewriting
or losing its raw evidence.

## Rationale

The complete source-set identity makes negative lifecycle knowledge explicit
without confusing it with bounded selection. Fail-closed readers prevent
retired generated rows from becoming answer evidence during the interval
before cleanup. Atomic deep replacement keeps all monolith-owned projections
on one coherent source set, while independent Atlas, shard, and graph cleanup
retain their own publication contracts.

Preserving the session directory and raw digest allows later audit,
reinstatement, or canonicalization correction. The generated tombstone makes
the cleanup explainable while keeping owner evidence stronger than every
read-model.

## Consequences

- Positive: a removed owner session is no longer returned from exact, episode,
  dense, shard, Atlas, or graph navigation as if it were current.
- Positive: bounded discovery cannot create false deletions merely because a
  valid session was outside its window.
- Positive: retirement, authoritative empty state, deterministic rebuild, and
  reinstatement have executable failure-derived coverage.
- Tradeoff: all search and episode candidates are withheld after any confirmed
  removal until the coherent deep replacement succeeds.
- Tradeoff: a missing or malformed registry preserves legacy compatibility but
  cannot prove current source-set completeness.
- Follow-up: evaluate whether future independently published projections need
  their own persisted source-set identity rather than deriving retirement from
  their complete per-session state.

## Boundaries

This decision does not authorize raw deletion, make the registry proof of
session content, or turn a tombstone into owner truth. It does not prove that a
remaining candidate is relevant, that graph cleanup improves retrieval, or
that process completion proves freshness. MCP remains read-only and cannot
perform or attest the replacement. Host scheduling and portable publication
remain separate owner routes.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `READINESS.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Run the sealed lifecycle lab from two sources to one and from one to zero,
verify fail-closed readers before maintenance, run bounded catch-up and deep
replacement under the same preregistered evidence, compare two clean semantic
digests, then restore the retired registry record. Reopen this decision if a
bounded omission creates a tombstone, a removed ID remains answer-admissible,
deep replacement changes raw bytes, or reinstatement requires raw recovery.

## Verification

Failure-derived tests cover complete-registry detection under bounded
selection, legacy metadata, exact/episode withholding, non-deep producer
deferral, deep monolith/Atlas/shard/graph replacement, authoritative empty
publication, raw SHA preservation, deterministic double rebuild, and
reinstatement. Manual proof uses independently chosen real-shaped raw refs and
records before/after projection cardinality and rejected claims; private paths
and session-specific evidence remain in the session proof packet.
