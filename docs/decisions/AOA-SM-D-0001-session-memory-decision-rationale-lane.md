# Session-Memory Decision Rationale Lane

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0001
- Original date: 2026-07-14
- Owner surfaces: `docs/decisions/`
- Surface classes: decision record, docs route, portable source, generated read model
- Projection layers: decision lane, portable bundle
- Guard families: owner boundary, public-safe rationale, generated index parity
- Posture: accepted

## Context

`aoa-session-memory` already has strong current contracts for archive evidence,
query behavior, projection semantics, maintenance, and portable export. Durable
rationale has instead been split between those active contracts, session
provenance, runtime diagnostics, and neighboring repository decisions.

That split is insufficient for choices which will recur after the originating
session is gone. Putting the full debate into `DESIGN.md` or `PIPELINE.md`
mixes rationale with current law. Keeping all rationale only in session memory
makes the choice harder to discover from the source repository. Copying a
sibling lane literally would import metadata that does not describe session
projections.

## Options Considered

- Keep rationale only in active design and pipeline documents. This keeps the
  file count small but makes current law carry historical alternatives and
  tradeoffs.
- Keep rationale only in session provenance. This preserves experimental
  history but leaves future source readers without a bounded canonical route.
- Copy another AoA decision lane verbatim. This gives superficial symmetry but
  imports mechanic, memory-object, or tree vocabulary that this organ does not
  own.
- Create a local decision lane with shared canonical-ID/index conventions and
  session-memory-specific metadata.

## Decision

Adopt `docs/decisions/` as the durable rationale lane for
`aoa-session-memory`.

Records use the canonical `AOA-SM-D-####` ID pattern, full canonical-ID
filenames, and metadata for owner surfaces, surface classes, projection layers,
guard families, and posture. Generated indexes provide bounded lookup by those
facets. The source lane is exported through the normal portable builder; the
standalone bundle is not edited as a second authority.

## Rationale

The shared AoA decision shape makes rationale discoverable across the repo
family, while local metadata keeps session-memory boundaries honest. Separating
rationale from current contracts lets `DESIGN.md`, `DESIGN.AGENTS.md`, and
`PIPELINE.md` remain concise owner law. Generated indexes make lookup cheap but
always lead back to a source record and then to current behavior.

## Consequences

- Durable, non-trivial choices gain a canonical source path.
- Existing session evidence and diagnostics are not retroactively converted
  into decisions.
- Decision metadata and generated indexes require parity checks.
- Portable export must carry the public-safe lane without carrying private
  sessions or runtime state.
- Small implementation choices continue to use diffs, tests, or review notes
  rather than new decision records.

## Boundaries

This lane does not accept session evidence as reviewed truth, replace active
source contracts, own MCP transport, or make generated indexes authoritative.
It records only reviewed rationale that belongs to this organ.

## Source Surfaces

- `AGENTS.md`
- `DESIGN.md`
- `DESIGN.AGENTS.md`
- `PIPELINE.md`
- `scripts/aoa_session_memory.py`
- `manifests/artifact_bundles/portable_bundle.bundle.json`

## Follow-Up Route

Add new records only for durable archive, projection, routing, freshness,
orchestration, portability, evidence-boundary, or storage choices. Regenerate
indexes and export the source lane through the owner route.

## Verification

Decision-index generation and checked parity are owned by
`scripts/generate_decision_indexes.py`. Portable parity is verified by the
normal source-to-bundle export tests and bundle audit.
