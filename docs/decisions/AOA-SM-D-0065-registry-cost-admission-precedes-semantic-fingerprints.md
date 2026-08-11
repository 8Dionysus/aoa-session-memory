# Registry Cost Admission Precedes Semantic Fingerprints

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0065
- Original date: 2026-08-11
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: freshness, scheduling, incremental maintenance, performance
- Projection layers: session registry, route indexes, search, maintenance diagnostics
- Guard families: pre-admission, cost-class admission, bounded discovery, explicit handoff
- Posture: accepted

## Context

Light-only repair admission still occurred after semantic fingerprints were
computed for the complete bounded discovery window. One cursor-reserved heavy
session could therefore parse and canonicalize large projection payloads even
though the later repair selector correctly deferred it. A live bounded slice
spent minutes and several gigabytes before selecting a small light session.

## Options Considered

- Keep semantic fingerprints before admission because the semantic classifier
  is authoritative. Rejected because rejected work can still consume the full
  freshness envelope.
- Remove cursor fairness. Rejected because that hides old debt and can starve
  discovery without eliminating other oversized candidates.
- Admit from registry metadata first, then run authoritative semantic
  fingerprinting only for the admitted subset.

## Decision

Bounded freshness maintenance applies a conservative cost pre-admission gate
from session-registry raw bytes, event count, and segment count before opening
projection payloads. The persistent discovery cursor advances across the
original window. Records above the requested light or warm ceiling remain
visible as deferred work, while semantic fingerprinting and dirty-state
classification continue unchanged for admitted records. The index-drip
resource-demand epoch advances so peaks learned from the former pre-admission
shape do not govern the new route.

## Rationale

The session registry is already the bounded navigation surface used to select
the discovery window. Its declared counts can safely reject obviously
oversized work without claiming that admitted records are current. This makes
the cost boundary control both mutation and diagnostic work while preserving
semantic fingerprints as the authority for the smaller admitted subset.

## Consequences

- Positive: a cursor-reserved heavy session cannot consume freshness memory or
  latency merely to be rejected later.
- Positive: the cursor still advances, so warm and heavy debt remains visible
  and can converge through targeted, backlog, or deep owners.
- Positive: resource admission learns from receipts produced by the new
  bounded shape rather than its multi-gigabyte predecessor.
- Tradeoff: registry metadata can conservatively defer a record whose eventual
  semantic work would be cheaper; larger profiles remain its recovery route.
- Follow-up: calibrate thresholds from consecutive complete live receipts.

## Boundaries

Pre-admission is not freshness proof, does not replace semantic fingerprints,
and does not discard or rewrite source evidence. Unknown or incomplete cheap
metadata is admitted rather than treated as proof of low cost.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Use bounded maintenance receipts for latency and memory calibration; use
backlog, deep, or an explicit target for deferred warm and heavy sessions.

## Verification

Focused tests require heavy registry records to be excluded before fingerprint
functions receive the selected subset. Live proof must show the same mixed
window completing without opening the heavy cursor session.
