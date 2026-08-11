# Append-Only Raw Capture Ledger and Persistent Live-Tail Overlay

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0049
- Original date: 2026-08-10
- Owner surfaces: `scripts/aoa_session_memory.py`, `schemas/raw-capture-state.schema.json`, `schemas/live-tail.postings.schema.json`, `schemas/live-tail.postings-shard.schema.json`, `DESIGN.md`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: raw capture, live-tail retrieval, incremental maintenance, storage
- Projection layers: raw evidence, persistent live-tail overlay
- Guard families: append-only capture, source epoch, content address, hash chain, prefix attestation, last-good preservation
- Posture: accepted

## Context

Lifecycle hooks preserved a large live transcript by copying it to a temporary
file and hashing the complete copy on every capture. The operation was safe but
its cost grew with all historical bytes rather than with the new tail. Live
retrieval then hashed the complete archived prefix again before scanning the
unarchived suffix. A continuously growing session therefore paid two repeated
whole-prefix costs even when only a few lines had arrived.

The archive projection cannot assume that a writable transcript is immutable.
It must distinguish a true append from truncation, inode replacement, or a
rewrite at the committed boundary, and it must not splice bytes from two source
epochs into one evidence stream.

## Options Considered

- Continue whole-file capture and prefix hashing. Rejected because cost remains
  linear in historical session size on every hook and query.
- Append directly to one mutable raw mirror without block receipts. Rejected
  because a partial write or source replacement would be difficult to audit or
  roll back.
- Trust only path, size, and modification time. Rejected because those fields
  do not prove the committed boundary still contains the same bytes.
- Persist immutable content-addressed byte blocks in a chained source epoch,
  retain an append-only compatibility materialization, and publish a bounded
  persistent live-tail overlay with an archived-prefix attestation.

## Decision

Raw hook capture is an append-only block ledger. The first capture of a source
epoch reads the available snapshot once in bounded blocks. Later captures
verify device, inode, monotonic size, the last committed source range, its
block digest, the compatibility-materialization watermark, and the hash-chain
head, then read only bytes after the committed offset. Each block records byte
and line coordinates, boundary completeness, SHA-256, predecessor chain hash,
commit time, and an immutable content-addressed artifact path.

Truncation, inode replacement, source-path change, or committed-boundary digest
mismatch starts a new epoch. Earlier epochs and blocks remain readable; bytes
from different epochs are never silently concatenated. A crash before ledger
publication may leave an unreferenced content-addressed block, but it cannot
advance the committed watermark. An uncommitted compatibility suffix is
truncated back to that watermark before retry.

Block files and the compatibility suffix are flushed and fsynced before the
ledger watermark is written. Ledger, postings, overlay, and latest capture
state use temp-file fsync, atomic rename, and parent-directory fsync. This
durability cost is paid only on changed capture or queue state, never by an
unchanged hot probe.

The hook also atomically publishes `raw/live-tail.index.json`, a compact
redacted `raw/live-tail.postings.json` manifest, and bounded immutable posting
revisions under `raw/live-tail-postings/`. The index binds the
current epoch and chain head, source identity and captured watermark, complete
line state, compatibility materialization, and any archived-prefix digest
measured while the source was already being captured. A live-tail reader may
skip whole-prefix rehashing only when the current source identity and size,
ledger epoch, chain head, materialization size, last block receipt, and exact
archived-prefix attestation all match. Otherwise it falls back to the existing
bounded direct-source validation or fails closed.

The postings frontier advances only across newly completed captured lines. A
native shard stores typed fields, redacted previews, safe tokens, a local
inverted token-to-entry map, exact byte ranges, and raw or capture refs; it
stores neither raw line bodies nor reversible secret digests. The compact
manifest stores exact shard byte receipts and a no-false-negative Bloom filter
over the shard's already-redacted safe tokens. Ordinary append reads at most
the last open shard, writes a new immutable revision for it or a new shard, and
publishes the manifest last. The prior manifest and its shard revision remain
valid until publication; stale revisions are removed only afterward.

If a later line makes an earlier repeated literal recognizable as a sensitive
assignment value, retained derived shards are re-sanitized and re-sharded
before atomic publication. This exceptional privacy repair reads derived
postings, never historical raw. A positive lookup rejects irrelevant shards
through manifest filters, intersects local token postings in selected shards,
then verifies only the selected raw byte ranges. It can therefore prove the
returned evidence current while still reporting
`global_recall_complete=false`. A miss or a query that cannot be represented by
safe tokens is never an exhaustive negative claim and may route to the
existing bounded raw fallback.

The schema-2 monolithic postings packet is admitted only when its exact
predecessor generation is allowlisted. It is hard-linked as a sealed legacy
shard without reading historical raw, and the manifest records the migration.
An unknown predecessor fails closed. Native readers retain the legacy path
until the guarded bridge is no longer needed.

Every hook-observed source is also registered in a compact capture-watch
frontier. The ordinary hot timer stats only a bounded set of known paths,
performs no raw read for unchanged sources, and recovers a changed source
through the same append ledger if a hook was missed. Capture recovery makes the
live overlay current; it does not implicitly schedule a whole stable-session
rebuild. Hot maintenance consumes this watch frontier and the component outbox
without archive rediscovery. Catchup, deep audit, and recovery remain the
explicit global reconciliation routes.

The compatibility materialization is a rebuildable append-only view needed by
existing projection builders. Immutable ledger blocks and raw source evidence
are stronger than that view. The ledger persists a portable SHA-256 continuation
state. Each append hashes only new bytes while still emitting the exact
conventional SHA-256 of the complete captured stream. Older ledgers pay one
explicit compatibility bootstrap read; later appends do not rehash historical
bytes. When a published archive watermark exactly equals a previously captured
watermark, its prefix attestation is derived from that persisted exact state
with zero source bytes read.

## Rationale

Hook cost becomes proportional to newly appended bytes while every committed
range remains independently verifiable. Source epochs make replacement and
rewrite behavior explicit. The persistent overlay gives agents access to new
complete lines without waiting for full projection freshness and without
turning a query into another whole-session scan. Prefix attestation is acquired
as part of capture, so it adds no second read of historical bytes.

## Consequences

- Positive: an unchanged repeated hook performs no transcript copy or full
  transcript hash.
- Positive: a growing transcript writes only new immutable blocks and appends
  only the new suffix to the compatibility view.
- Positive: live-tail retrieval can use a persistent, receipt-checked overlay
  without hashing the full archived prefix on every query.
- Positive: exact positive lookup can select candidate tail lines without
  parsing the complete unarchived JSONL suffix.
- Positive: incomplete final-line state and source-epoch transitions are
  explicit.
- Tradeoff: the mutable ledger and compact postings manifest still grow with
  block and shard metadata; they do not embed historical entries or global
  token postings, but a later hierarchical catalog may be warranted for much
  larger shard counts.
- Tradeoff: recognition of a new sensitive literal deliberately re-sanitizes
  retained derived shards. This is a privacy repair exception to the ordinary
  one-open-shard append bound and still reads zero historical raw bytes.
- Tradeoff: an unreferenced block may remain after a crash and requires a
  bounded garbage-collection route after receipt reconciliation; the same is
  true for an immutable shard revision written before a failed manifest
  publication.
- Follow-up: let projection assembly consume ledger blocks directly, publish
  archive-prefix attestations when a new projection catches up, and remove the
  monolithic compatibility materialization after all readers are manifest
  first.

## Boundaries

The live-tail overlay is captured raw evidence, not a reviewed semantic
projection. It does not claim that search, task episodes, graph, vectors, or
Atlas are current. Boundary verification detects replacement, truncation, and
changes overlapping the last committed block; it is not a filesystem-wide
proof that an adversarial writer never modified an older already preserved
source range. Preserved block artifacts remain the authority for those earlier
bytes. This decision does not authorize live `.aoa` deployment.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `schemas/raw-capture-state.schema.json`
- `schemas/live-tail.postings.schema.json`
- `schemas/live-tail.postings-shard.schema.json`
- `tests/test_session_memory.py`
- `DESIGN.md`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Move classification, segmentation, and task-episode assembly to ledger-block
consumers with append-stable component manifests. Add bounded orphan-block
reconciliation only after the ledger and every referencing overlay have been
validated.

## Verification

Focused tests cover append-only byte cost, exact persisted SHA continuation,
immutable prior blocks and posting revisions, idempotent
capture, crash-before-commit preservation, source rewrite epoch separation,
zero-read watermark attestation, missed-hook timer recovery without archive
rediscovery, bounded-shard candidate selection, exact predecessor migration,
unknown-predecessor refusal, retry after manifest publication failure,
persistent-posting positive verification, later sensitive-literal recognition,
and existing
deferred-capture behavior. Source validation, schema validation, growth
benchmarks, portable export, and installed-surface proof remain required before
rollout.

## Review Amendment — 2026-08-11

The first accepted implementation proved delta raw capture but kept all live
postings in one JSON object. Event-dense evidence showed that this object grew
past 500 MB and was fully re-sanitized and rewritten on every append. The
bounded immutable shard plus compact manifest protocol above closes that
specific scaling defect while preserving the original raw-authority,
privacy-repair, last-good, and non-exhaustive-recall boundaries.
