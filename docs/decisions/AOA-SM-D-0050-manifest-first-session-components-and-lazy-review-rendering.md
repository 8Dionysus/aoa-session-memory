# Manifest-First Session Components and Lazy Review Rendering

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0050
- Original date: 2026-08-10
- Owner surfaces: `scripts/aoa_session_memory.py`, `schemas/segment.index.schema.json`, `DESIGN.md`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: session indexing, task episodes, segment review, incremental maintenance, storage, compatibility
- Projection layers: segment index, review rendering, task episodes, session component manifest
- Guard families: content identity, selective hydration, append stability, privacy, atomic publish, raw authority, reader compatibility
- Posture: accepted

## Context

Content-addressed task-episode shards initially remained duplicated inside
`session.index.json`. Segment construction also rendered every raw event body
into Markdown even though most agent routes use the machine index and exact raw
refs. Those compatibility choices reduced migration risk, but retained two
whole-session costs: repeated serialization of all episodes and eager review
rendering of every event.

A growing session additionally invalidated every task-episode shard because its
source identity included the whole-session raw digest. Closed episodes whose
evidence ranges did not change therefore appeared new after an unrelated tail
append.

## Options Considered

- Retain the embedded episode array indefinitely. Rejected because every write
  and reader parse remains proportional to the whole episode history.
- Remove shards and keep only the embedded array. Rejected because it discards
  component checkpointing and append-stable reuse.
- Stop producing readable Markdown. Rejected because bounded human review and
  export remain required.
- Make content-addressed episode components the default reader surface, keep a
  legacy embedded fallback, publish compact index-first Markdown, and render a
  selected full review artifact only on demand.

## Decision

New session publications are manifest first. `session.index.json` carries
aggregate task-episode counts, semantic digest, component-storage contract, and
an empty compatibility field, while ordered task episodes live in immutable
content-addressed shards. The shared loader validates manifest path bounds,
artifact filename and digest, payload digest, component key, source identity,
and count before returning any component. The bounded task-episode CLI/MCP
route stops after the requested matching components, reports the number of
hydrated shards, and marks unvisited integrity and global recall unresolved.
Full semantic-digest, audit, and projection consumers verify the complete
ordered set through the same loader. A legacy index without component storage
may still supply its embedded array; a broken or mixed-generation manifest does
not silently fall back to an embedded copy.

Task-episode component identity is scoped to the episode's semantic evidence,
event range, task-episode generation, and privacy/redaction contracts. A tail
append may reuse closed compatible shards from the published generation. An
exact declared predecessor shard may be restamped only when its payload digest
still equals the newly generated payload. Changed or open-tail episodes are
rebuilt.

The session index persists a privacy-safe episode-builder frontier. On an
append, the builder admits only the exact compatible segment prefix, reuses
sealed episodes covered by that prefix, and deliberately replays the last two
boundary-adjacent episodes plus the new tail. That bounded replay preserves
transport-turn bridging and semantic continuation without serializing the
entire historical episode set again. Its receipt exposes reused episodes,
replayed events, and the admitted lineage rather than calling the whole session
incremental merely because some shards were reused.

Segment publication is index first. It always writes the machine index, raw
and block refs, typed event metadata, counts, relationships, route maps, and a
compact Markdown synopsis with stable anchors. Full redacted event bodies are
not rendered on the normal build path. `render-segment` explicitly renders one
selected segment to a separate review artifact under `segments/rendered/`,
using the current privacy policy and a generation-bearing receipt. An oversized
raw body contributes only an omission marker, character count, and raw ref to
the machine index, preserving audit navigation without copying the body or its
literals.

Spawned segment workers receive immutable classification-block refs, exact line
ranges, a bounded reconciliation patch map, raw-block refs, and process-local
privacy context. They load only their own overlapping ranges and never receive
serialized `RawEvent` slices from the parent.

Classification artifacts also publish raw-free mergeable block summaries:
typed counts, route counts, compaction markers, and a bounded correlation
frontier. On an admitted append, the parent loads `RawEvent` objects only for a
bounded replay tail covering the previous open segment and the episode
transition frontier. It merges historical session aggregates from block
summaries, hardlinks attested sealed raw blocks, restamps attested sealed
segments, and recomputes only the open/new topology. A newly captured compaction
boundary seals the prior open component and creates the next open component
without hydrating the historical prefix. Stage checkpoints carry independent
stage work identities beneath the umbrella atomic publication transaction.

Each sealed segment has an immutable component identity bound to its own line
range, input digest, raw-block digest, role, and segment-stage ABI. The ordinary
append transaction can hardlink an exactly attested component and skip both
JSON hydration and Markdown rewrite. Classification-cache records use the same
records-root plus artifact-receipt admission. A separate deep doctor route
always performs uncached SHA-256 reads, validates payload/component identity,
and therefore catches same-size content mutation even if mtime was restored.

Cold builds, migrations without compatible summaries, and small histories
without a safe replay frontier retain the strict full-reduction fallback. That
fallback is explicit in execution receipts; it is not reported as incremental.
Goal lifecycles persist source line ranges. An appended goal signal expands the
replay boundary to the start of the crossing open lifecycle and merges only the
rebuilt tail with stable prior lifecycle ranges; semantic parity is checked
against a forced full replay.

## Rationale

The component manifest is the smallest current atom that can be validated and
selectively hydrated without weakening evidence. Episode-local identities turn
ordinary append reuse into a semantic property rather than a whole-session SHA
accident. Index-first segments preserve exact navigation and raw authority while
moving expensive prose rendering to the rare route that needs it.

## Consequences

- Positive: the root session index no longer duplicates all task episodes.
- Positive: closed episode shards survive unrelated session growth.
- Positive: ordinary segment builds avoid eager raw-body Markdown expansion.
- Positive: selected human review remains available through an explicit,
  redacted, receipt-bearing render.
- Positive: an admitted ordinary append does not allocate one parent event
  object per historical line and does not read historical raw bodies.
- Positive: sealed segment and classification payloads are relinked without
  historical content reads on the hot path, while explicit deep audit retains
  full content proof.
- Tradeoff: legacy embedded indexes remain a supported read fallback until a
  separate cleanup decision removes them.
- Tradeoff: full review rendering reads only the selected raw block for event
  bodies, but retains a process-local whole-session sensitive-literal scan
  until privacy-safe structural block markers can prove a smaller scan set.
- Follow-up: move the remaining cross-boundary correlation fallback onto the
  persisted frontier and physically split the monolithic producer contracts.

## Boundaries

Component shards and rendered Markdown are rebuildable projections. Raw JSONL
and immutable raw blocks remain evidence authority. Component freshness does
not imply search, entity, graph, or global recall freshness. The loader returns
no components when a manifest or shard fails validation. This decision does
not authorize live `.aoa` deployment or removal of legacy archives.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `schemas/segment.index.schema.json`
- `tests/test_session_memory.py`
- `DESIGN.md`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Physically split stage producers behind the existing ABIs, move the remaining
cross-boundary correlation fallback onto block summaries, and shard any tail
or component metadata whose write cost can otherwise grow without bound.

## Verification

Focused tests prove manifest-first publication and hydration, shard corruption
rejection, bounded two-episode tail replay after growth, ref-based spawned
segment-worker input, compact segment Markdown, explicit full review rendering,
semantic projection parity, and migrated CLI/search/graph/evidence readers.
Focused append/full replay parity now covers bounded parent materialization,
classification-summary aggregation, repeated append watermark advancement, and
a new compaction boundary. Goal-lifecycle append/full-replay parity and uncached
deep-audit mutation detection are covered. Large-corpus RSS bounds, MCP/export parity,
portable installation, live-equivalent performance, and local landing remain
required before rollout completion is claimed.
