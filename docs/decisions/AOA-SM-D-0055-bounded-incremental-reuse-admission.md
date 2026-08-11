# Bounded Incremental Reuse Admission

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0055
- Original date: 2026-08-11
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: stable projection, incremental maintenance, checkpoints, performance
- Projection layers: classification cache, segment projection, session component shards
- Guard families: aggregate root, metadata receipt, deep audit, crash recovery
- Posture: accepted

## Context

The actual 430 MB growth benchmark proved bounded raw scanning but exposed
derived-work amplification. The classification records root was recomputed for
every block lookup, every reused segment serialized the complete growing work
checkpoint, and every task-episode shard was rehashed and decoded despite an
already validated manifest-first receipt.

## Decision

One projection build validates each candidate classification index and its
records root once, then performs block lookup against that admitted immutable
view. Published last-good is inspected first. Only four newest work roots may
follow for crash recovery or bounded predecessor migration, so abandoned work
history cannot amplify every append. Search stops only at a complete,
exact-current, root-valid view whose artifact metadata receipts are also
current; a valid index must not hide a stronger published candidate when its
hardlinked artifacts have drifted metadata. Privacy structural markers are
admitted before the sensitive-literal pass, but only for blocks under the
attested published prefix. Reused published segments are recorded in memory as
a batch and the work checkpoint is persisted once per reuse batch; newly built
worker waves retain their existing crash checkpoints.

The generation-bound classification cache index is the sole resumable owner of
completed block identities, artifact receipts, and privacy markers. Mergeable
summaries remain inside their immutable block artifacts; the compact index must
not duplicate them. Its aggregate root binds each artifact identity and privacy
structural marker, so a marker cannot be altered independently of admission.
The umbrella work
checkpoint stores only its ref, generation, and completed count; it must not
duplicate the complete classification map at every phase. Newly classified
blocks publish that index once per bounded worker wave rather than once per
individual completion. On an exact append, the session aggregate is the
previously published aggregate plus summaries loaded only from the new
classification tail. An incompatible or non-contiguous prefix fails over to
explicit full summary hydration.

Task-episode shard reuse first admits the published component manifest. A shard
may skip content I/O only when its content-addressed filename, component key,
source identity, payload digest, byte count, exact size/mtime receipt, and,
where stable, ctime receipt are structurally current. After an attested hardlink publication, ctime may
drift because link-count changes are non-semantic; the receipt then uses
explicit `size_mtime_v1`, while the content-addressed filename and stored SHA
remain mandatory. Any missing or inconsistent manifest field falls
back to full shard hashing and decoding. Deep audit continues to rehash every
artifact independently.

The umbrella checkpoint also excludes the stable published segment prefix and
the complete raw-block payload/receipt map. Stable segment files are already
owned by their immutable published components and can be relinked again after a
crash; only newly built tail segments remain in the work checkpoint. Raw-block
resume is owned by the staged block index plus small index/compaction receipts;
the loader validates its exact publish identity and every referenced block's
size/mtime/content-digest receipt before reuse. Drift falls back to deterministic
raw-block reconstruction.

## Options Considered

- Rehash and decode every historical artifact on every append. Rejected because
  it preserves correctness by making append cost proportional to total history.
- Trust filenames or mtimes alone. Rejected because neither binds the component
  generation, aggregate membership, payload identity, and content digest.
- Remove checkpoints for reuse. Rejected because explicit recoverable progress
  remains useful; the accepted design changes repetition granularity only.

## Rationale

The aggregate roots and receipts were already produced and validated at atomic
publication. Rechecking them once per candidate generation preserves the same
admission boundary while removing quadratic work. Batch checkpointing changes
recovery granularity for reused immutable components, not correctness: a crash
may repeat the batch, while last-good publication and content-addressed inputs
remain unchanged.

## Consequences

- Stable classification reuse is linear in candidate indexes plus block count,
  rather than block count multiplied by complete index size.
- An exact-current resumable work view prevents historical raw blocks from
  being rescanned when the published cache needs a bounded predecessor
  migration; tail blocks remain selected for scanning.
- Reused segment checkpoint writes are bounded by reuse batches, not segment
  count; newly generated work remains checkpointed by worker wave.
- Umbrella checkpoint size is independent of historical classification-summary
  volume; resume rehydrates the exact generation-bound cache index.
- Classification-index publication size is independent of historical summary
  payload volume; hot aggregate reads are proportional to the appended tail.
- Current task-episode shards avoid historical content reads on the fast path.
- Umbrella checkpoint writes carry only delta segment completions and compact
  raw-block index receipts rather than stable-prefix payload maps.
- Receipt drift fails closed to the existing deep-read path, and scheduled deep
  audit remains the independent corruption detector.

## Boundaries

This does not make derived caches authoritative, replace deep audit, admit
unknown generation identities, or remove crash recovery. Raw publication and
semantic component validation remain governed by their separate owner
decisions and proof.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `docs/decisions/AOA-SM-D-0053-single-pass-task-episode-reduction-and-shard-redaction.md`
- `docs/decisions/AOA-SM-D-0054-native-assisted-portable-sha256-continuation.md`

## Follow-Up Route

Rerun the actual 430 MB no-swap growth benchmark and compare classification
index bytes, historical input reads, and aggregate semantic digest with the
pre-compaction receipt.

## Verification

Focused tests prove one records-root computation across many lookups, bounded
`segments_in_progress` checkpoints across captured growth, crash/resume parity,
privacy-marker reuse from a root-valid current work view, classification resume
without bulk records or literal values in the umbrella checkpoint, and
task-shard reuse without reading or hashing published shard content. Compact
index tests additionally prove that summaries are absent from index records,
exact-prefix aggregation reads only tail artifacts, semantic output matches a
full replay, and deep audit still hashes block contents independently.
