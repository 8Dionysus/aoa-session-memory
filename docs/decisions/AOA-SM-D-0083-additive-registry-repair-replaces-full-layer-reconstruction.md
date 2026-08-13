# Additive Registry Repair Replaces Full Layer Reconstruction

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0083
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: registry rebind, graph maintenance, performance
- Projection layers: graph, entity registry
- Guard families: complete proof, additive repair, transaction boundary
- Posture: accepted

## Context

The compact rebind proof found only missing registry-to-route contribution
pairs: there were no extra pairs, semantic node mismatches, dangling endpoints,
malformed payloads, or selective-dependency drift. The legacy repair still
reconstructed every registry contribution in Python, exceeding seven GiB and
ten minutes for a 1536-pair additive mismatch.

## Options Considered

- Keep full registry-layer reconstruction with a longer timeout. Rejected
  because work and memory scale with the whole materialization instead of the
  proved mismatch.
- Rebuild affected source contributions. Rejected because event/segment
  high-fanout policy intentionally omits some registry links; source refresh
  correctly reproduces that policy and cannot repair the registry read model.
- Add only the exact missing pairs and refresh their touched aggregates.
  Accepted.

## Decision

When the complete compatibility plan proves an additive-only registry mapping
mismatch, rebind inserts only those missing registry node/edge contributions,
updates their source counts, and refreshes only affected aggregate IDs. It then
runs the unchanged complete post-proof before committing. Any extra pair,
semantic mismatch, dangling endpoint, malformed payload, selective-dependency
drift, or changed mismatch count falls back to the full guarded route.

## Rationale

The proof already establishes both the repair set and the absence of destructive
work. Preserving that scope through mutation makes runtime proportional to the
actual drift while retaining the same transaction, dependency pin, and
post-proof guarantees.

## Consequences

- Positive: additive registry drift no longer allocates a full in-memory copy
  of the registry layer.
- Positive: ordinary source materialization policy remains unchanged.
- Tradeoff: non-additive registry changes still require the full guarded
  reconstruction path.

## Boundaries

This does not weaken complete proof, repair extra mappings, bypass dependency
currentness, mutate raw/session evidence, or split the transaction.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Use compact rebind normally. The plan selects additive exact repair only when
all eligibility guards pass; otherwise it fails closed or uses the existing
full registry reconstruction.

## Verification

Delete one registry mapping in a SQLite fixture, prove exact additive recovery,
run rebind and generation regressions, source/portable validation, and apply to
the live mismatch under the maintenance coordinator.
