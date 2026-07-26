# Projection-Scoped Producer Generation Identity

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0030
- Original date: 2026-07-26
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: indexing, freshness, reproducibility, migration, atomic publication
- Projection layers: segment index, session index, task episodes, episode semantic, exact search, lexical search, dense vectors, graph, atlas, entity registry
- Guard families: generation identity, stale abstention, dependency pinning, deterministic rebuild, legacy transition
- Posture: accepted

## Context

The original producer identity used one digest of the complete
`aoa_session_memory.py` process source. That correctly invalidated rows after a
producer change, but it also invalidated every projection after an unrelated
change elsewhere in the same large source file. The result was avoidable full
rebuild pressure and a false coupling between projections whose schemas,
dependencies, normalization, and producing logic had not changed.

Using only schema or hand-maintained version fields would avoid that pressure
but would reintroduce the older failure: semantic producer behavior can change
without a storage-shape change.

## Options Considered

- Keep the whole-file producer digest for every projection. Rejected because an
  unrelated CLI or projection edit needlessly invalidates all generated rows.
- Use only schema, classifier, or manually bumped versions. Rejected because a
  missed version bump could admit rows produced by different behavior.
- Hash a runtime call graph discovered dynamically. Rejected because dynamic
  coverage depends on the exercised input and is not a stable portable
  contract.
- Declare source ranges for each projection, hash those ranges from the
  process-loaded source snapshot, and combine them with the projection's
  schemas, policies, and dependency generations.

## Decision

Every answer-bearing projection declares the authored source ranges that
produce its semantics. Its generation identity records the ordered range
anchors, byte counts, range digests, contract version, schemas, normalization,
policies, and dependency generations.

The ranges are read from one process-loaded source snapshot. A long-running
writer therefore cannot silently mix code read before and after an on-disk
source update.

A missing anchor, duplicated anchor, reversed range, or otherwise unresolved
producer contract is incompatible rather than current. Rows of an older or
unknown generation remain navigation-only and cannot enter answer admission.

Transition from a legacy whole-file identity is bounded. A caller may provide
the exact prior producer source only when its whole-file digest matches the
stored legacy identity. The system reconstructs the prior projection-specific
identity from that source and applies only a declared compatible catch-up.
Unknown source text or an unmatched digest requires rebuild.

## Rationale

Projection-scoped identity makes invalidation follow semantic ownership rather
than file layout alone. It keeps automatic freshness honest while avoiding
unrelated graph, dense, search, or archive rebuilds. Recording the actual range
proof makes the contract inspectable and reproducible instead of relying on a
manual version bump.

The process-loaded snapshot closes a race between generation calculation and
publication. The strict legacy route preserves migration without inventing a
producer identity for unavailable code.

## Consequences

- Positive: unrelated source edits no longer invalidate every projection.
- Positive: a semantic edit inside a declared producer range invalidates the
  affected projection without a manual epoch bump.
- Positive: generation packets explain exactly which source chunks governed a
  projection.
- Tradeoff: moving or splitting producer functions requires updating the
  declared anchors and exercising the generation-contract tests.
- Tradeoff: shared helper behavior must be included in every projection whose
  semantics it changes.
- Follow-up: preserve deterministic double-rebuild proof for the same sealed
  owner inputs, configuration, generation identity, and dependency state.

## Boundaries

Source-range identity does not prove semantic quality, evidence correctness, or
current owner truth. It does not admit a stale row merely because its code
range can be reconstructed, and it does not replace schema migration,
dependency freshness, raw-ref verification, or manual retrieval evaluation.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Run focused generation and transition regressions, rebuild each invalidated
projection through its owner route, compare two identical-input rebuilds, and
verify generation visibility in CLI, skill, portable, and read-only MCP
packets.

## Verification

Focused tests cover independent projection invalidation, unresolved range
failure, process-loaded source stability, exact legacy-source matching,
dependency generation changes, and incompatible-row exclusion. Live
verification additionally requires current projection status and resolvable
evidence packets after the affected rebuilds.
