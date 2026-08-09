# Content-Addressed Session-Index Components With Compatibility View

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0046
- Original date: 2026-08-09
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `DESIGN.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: session indexing, incremental maintenance, storage, privacy, compatibility, orchestration
- Projection layers: session index, task episodes, session projection work
- Guard families: raw authority, content identity, cooperative deadline, privacy, deterministic parallelism, atomic publish, reader compatibility
- Posture: accepted

## Context

Block-addressed classification and segment checkpoints made the first two large
session-indexing phases restartable, but session assembly still produced one
large in-memory object before its first checkpoint. On event-dense sessions,
task episodes dominate the serialized session index and session-specific
privacy redaction repeats millions of substitutions. A bounded heavy slice can
therefore finish classification and segments, enter session assembly, and lose
the remaining budget without preserving assembly progress.

The existing CLI and MCP readers consume the embedded fields in
`session.index.json` directly. Replacing that file with a compact shard
manifest in one release would reduce writer cost but create a broad, mixed
reader migration and could make last-good archives unreadable to an older
installed access plane.

## Options Considered

- Keep the monolithic writer and only increase its deadline. Rejected because
  interruption still repeats all session-index assembly work.
- Replace `session.index.json` immediately with a compact manifest. Rejected
  for the first landing because direct CLI, test, and MCP readers have not yet
  completed a coordinated reader migration.
- Persist unredacted task-episode state or session-sensitive literals.
  Rejected because it expands the private evidence and credential surface.
- Materialize privacy-safe task episodes as immutable content-addressed
  component shards, publish a compact shard manifest, and retain the embedded
  `session.index.json` payload as a compatibility view during migration.

## Decision

Session-index assembly materializes each task episode as an immutable JSON
component shard. The shard envelope binds the exact raw source identity, the
task-episode producer generation, and the privacy/redaction policy versions.
Its filename is the SHA-256 of the complete serialized artifact, while the
manifest records both artifact and payload digests.

Task-episode redaction runs in deterministic bounded waves with one through six
process workers. Every completed shard is durable inside the exact
content-addressed projection-work directory. A cooperative deadline may stop
between waves; the next compatible run validates and reuses completed shards.
Privacy matchers use only necessary-marker prefilters: an expensive matcher is
skipped when a literal required by every possible match is absent, while the
admitting expression and opaque-credential scan remain unchanged.
Raw text, parsed payloads, and session-sensitive literal values are not added
to shard metadata. The ephemeral whole-session literal policy is still applied
before any task-episode payload becomes persistent.

The shard directory and its manifest publish through the existing atomic
session-projection journal. Validation checks publish identity, path bounds,
artifact hashes, payload hashes, component order, and exact parity with the
embedded task-episode compatibility view. Readers continue to receive the
current `session.index.json` shape during this phase. A later reader migration
may make the compact manifest canonical and hydrate only requested components;
that migration is not silently implied by this decision.

## Rationale

The smallest safe boundary is the dominant independently valid session-index
component, not the complete index and not an arbitrary byte range. Immutable
component shards create a restart boundary inside session assembly, allow
bounded parallel privacy work, and preserve one atomic reader generation.
Keeping the embedded compatibility view separates writer decomposition from a
coordinated CLI/MCP reader cutover.

## Consequences

- Positive: a bounded run preserves completed task-episode assembly work.
- Positive: privacy redaction can use the existing bounded worker envelope.
- Positive: benign transcript text avoids provably impossible credential
  matcher scans without weakening the privacy policy.
- Positive: validation proves shard-to-compatibility parity before publish.
- Positive: older direct readers retain the established session-index fields.
- Tradeoff: task episodes are temporarily stored both as shards and inside the
  compatibility view.
- Tradeoff: task-episode source generation still scans the full event stream;
  append-stable builder-state checkpoints remain follow-up work.
- Tradeoff: a compact manifest-only reader cutover requires coordinated CLI,
  MCP, export, and fallback proof.

## Boundaries

Component shards are rebuildable projections and never replace raw, manifest,
block, or segment evidence. A shard hash proves exact stored bytes under its
declared generation; it does not prove search, graph, registry, or global
freshness. This decision does not persist sensitive literal values, authorize
mixed-generation reads, remove the compatibility view, or bypass host resource
admission.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `DESIGN.md`
- `docs/decisions/`

## Follow-Up Route

Measure cold, interrupted-resume, and growing-session assembly separately.
Then add append-stable task-episode builder checkpoints and migrate CLI/MCP
readers to selective component hydration before considering removal of the
embedded compatibility view.

## Verification

Tests cover content addressing, privacy redaction, deadline checkpoint/resume,
parallel deterministic ordering, shard-manifest validation, compatibility-view
parity, atomic rollback, and raw hash preservation. Source validation, clean
portable export, and a resource-admitted live large-session proof remain
required before rollout completion is claimed.
