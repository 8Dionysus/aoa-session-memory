# Entry-Set-Equivalent Graph Rebind Is Metadata Only

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0077
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: graph dependency, generation transition, automatic maintenance, bounded rebind
- Projection layers: entity registry, graph
- Guard families: entry-set fingerprint, semantic epoch, generation compatibility, transaction rollback
- Posture: accepted

## Context

A registry dependency ID can change because snapshot-level metadata or producer
generation changed even when the exact registry entry set did not. The graph
rebind route nevertheless parsed every node, edge, and contribution payload
several times to prove that updating only generation and dependency bindings
did not change graph content. On a large store that metadata transition cost
more than ordinary graph maintenance.

## Options Considered

- Always run complete payload equivalence scans. Rejected because it makes
  metadata-only transitions proportional to graph payload volume.
- Accept matching semantic epoch alone. Rejected because same-epoch entry
  growth can require registry-node materialization changes.
- Admit a metadata-only transaction only when the exact entry-set fingerprint,
  entity count, semantic epoch, stored source bindings, static versions, and
  declared generation transitions all prove equivalence.

## Decision

Graph registry rebind classifies an entry-set-equivalent transition before
materialization scans. The fast route requires equal non-empty registry source
fingerprints, equal entity counts and semantic epochs, valid source bindings
to the stored dependency, no static version mismatch, and compatible graph
generation transitions for metadata and every source row. It skips content
digests and selective registry migration, updates only generation/dependency
bindings in one transaction, repeats the same identity proof after commit, and
retains rollback guards for producer or dependency changes.

## Rationale

The registry source fingerprint is the exact canonical entry-set identity used
by graph resolution. When it is unchanged, registry graph content cannot need
rematerialization. Transaction source code constrains mutations to fields that
the graph content digest already excludes.

## Consequences

- Positive: metadata-only rebind cost follows source-row metadata rather than
  multi-gigabyte payload volume.
- Positive: post-commit proof is fast and uses the same explicit invariants.
- Tradeoff: any entry-set, epoch, binding, static-version, or undeclared
  generation change falls back to complete materialization proof.

## Boundaries

This does not certify unrelated pre-existing graph quality, admit entry-set
growth without proof, skip rollback, or make generated registry/graph content
owner truth.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Use complete materialization compatibility and bounded registry refresh when
the exact entry-set fingerprint changes; use graph maintenance for source
content debt after dependency binding is current.

## Verification

Run identity-only no-scan regression, mixed-generation compatibility, content
digest exclusion, rollback tests, decision indexes, compile, source/export
validation, and a live rebind timing plus final graph freshness gate.
