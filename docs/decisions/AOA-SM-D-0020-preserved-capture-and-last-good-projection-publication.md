# Preserved Capture and Last-Good Projection Publication

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0020
- Original date: 2026-07-18
- Owner surfaces: `scripts/aoa_session_memory.py`, `schemas/`, `PIPELINE.md`, `tests/test_session_memory.py`
- Surface classes: raw preservation, session indexing, physical storage transition, recovery
- Projection layers: raw capture state, session projection, segment projection, raw-block storage
- Guard families: last-good preservation, content-addressed capture, atomic publish, partial-failure rollback, generation compatibility
- Posture: accepted

## Context

Foreground hooks can observe a transcript after its last completely indexed
generation. The capture must preserve those newer bytes promptly, but session
manifest, segment, raw-block, and session-index files form one evidence route.
Replacing only `raw/session.raw.jsonl` or patching those files one at a time
creates a mixed generation: raw refs can point at different content than the
published indexes, while readers may still treat the archive as indexed.

The same risk exists when changing only the physical representation of raw
blocks. Writing gzip sidecars, changing block ledgers, and removing plaintext
files in separate published steps can leave stable refs without a readable
payload after interruption.

## Options Considered

- Replace the indexed raw file immediately and repair its projections later.
  Rejected because the newest bytes would silently invalidate last-good refs
  before a complete replacement generation exists.
- Patch manifest, block, segment, and session indexes in place while keeping a
  repair journal. Rejected because readers can observe intermediate mixtures
  and recovery must reconstruct which files belong together.
- Refuse capture whenever indexing cannot finish synchronously. Rejected
  because evidence preservation must not depend on semantic or resource-heavy
  work.
- Preserve the new raw snapshot content-addressably, mark it ahead of the
  projection, block stale answer candidates, and publish every generated
  session file from one validated stage with rollback to the last-good set.

## Decision

A captured transcript and its indexed session projection have separate
identities and may advance independently.

When a foreground or bounded route cannot finish indexing, it writes a
content-addressed raw capture plus one atomic capture-state pointer. If that
capture is newer than the indexed raw digest, the existing raw file, manifest,
segments, raw-block ledger, and session index remain byte-for-byte last-good.
Semantic, graph, and other answer-bearing readers reject that session
generation as capture-ahead and expose the exact catch-up route. Operational
hook observations are recorded outside the semantic projection.

A completed sync, reindex, or raw-block storage transition builds the full
affected file set in a sibling stage. It validates digests, resolvable refs,
generation and publish identities, capture state, and readable block payloads
before publication. One publish journal makes readers abstain during the
replacement and permits recovery to restore the prior complete file set after
any interrupted rename. Plain raw-block removal is part of that same staged
publication, never a later in-place phase.

## Rationale

This route separates the urgent evidence-preservation obligation from the
stronger claim that all derived views are current. Content addressing makes a
repeated capture idempotent and retains a stable provenance handle. Keeping
last-good bytes unchanged gives rollback a concrete target instead of asking
recovery to synthesize one from partial state.

Validating and publishing the complete affected set makes publish identity an
observable consistency boundary. Readers can safely abstain while the journal
exists and resume from either the fully old or fully new generation. Raw
evidence remains authority in both states; the journal and capture pointer are
coordination metadata, not proof of semantic freshness.

## Consequences

- A preserved capture may be newer than every semantic projection; freshness
  reports this as deferred rather than overwriting or pretending currentness.
- Content-addressed captures use temporary extra storage until indexed catch-up
  and later evidence-preserving retention policy can account for them.
- Legacy sessions without the capture/publish contract require an explicit
  bounded reindex before physical raw-block compaction.
- Session-level publication temporarily blocks affected readers instead of
  serving a mixed file set.
- Registry refresh remains a separate rebuildable projection and cannot undo a
  successfully published session generation.

## Boundaries

This decision does not claim that a captured transcript is complete, that a
successful publish makes semantic ranking correct, or that a timer made global
search and graph projections fresh. It does not authorize deletion of raw
captures, session evidence, or external owner evidence. SQLite search, dense,
graph, Atlas, and registry projections retain their own transaction,
generation, and freshness contracts.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `schemas/raw-capture-state.schema.json`
- `schemas/session.manifest.schema.json`
- `schemas/segment.index.schema.json`
- `PIPELINE.md`
- `tests/test_session_memory.py`

## Follow-Up Route

Run bounded live capture-ahead and recovery cycles after landing, then verify
source, standalone bundle, and read-only MCP packets preserve the same stale
and next-route semantics. Reopen this decision if concurrent-reader evidence
shows a mixed generation, if capture retention creates unbounded pressure, or
if another projection needs to join the session publish boundary.

## Verification

Owner-neutral regressions inject capture-copy and mid-publication failures,
compare every affected last-good byte, verify reader abstention while a publish
journal exists, check stage/backup cleanup, and repeat the operation
successfully. Deterministic double rebuild, metadata-generation mismatch,
deferred-worker retry, raw-unavailable incident, and compressed-block reader
cases cover adjacent contracts. Live catch-up, portable parity, and access-plane
proof remain distinct completion gates.
