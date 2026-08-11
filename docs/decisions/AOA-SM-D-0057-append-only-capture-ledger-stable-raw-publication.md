# Append-Only Capture Ledger Stable Raw Publication

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0057
- Original date: 2026-08-11
- Owner surfaces: `scripts/aoa_session_memory.py`, `DESIGN.md`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: stable projection, raw capture, incremental maintenance, performance
- Projection layers: raw capture, raw block projection, session manifest
- Guard families: append-only ledger, processed watermark, chain receipt, last-good fallback, deep audit
- Posture: accepted

## Context

Incremental parsing and component reuse made a real 430 MB append bounded, but
stable publication still copied and then rehashed the entire monolithic
`raw/session.raw.jsonl`. On filesystems without reflink support this violated
the requirement that a small append must not read or rewrite the old prefix.

The capture layer already persists only new source bytes into immutable,
content-addressed blocks, maintains a chained ledger, keeps a bounded
materialization, and carries a resumable conventional SHA-256 at an exact byte
watermark. Recopying that same evidence into every stable projection added no
new authority.

## Options Considered

- Require a reflink-capable filesystem. Rejected because portable installation
  must not depend on CoW support.
- Hardlink the growing capture as a supposedly immutable snapshot. Rejected
  because later appends would mutate the staged and backup inode across an
  atomic-publish boundary.
- Publish the exact capture-ledger watermark and retain the old monolith only
  as a compatibility fallback. Accepted.

## Decision

When the current raw source is an exact, stable capture-ledger watermark, the
stable projection records
`append_only_capture_ledger_with_bounded_materialization_v1`. Its manifest binds
the raw SHA-256, byte and line watermark, epoch, chain root, block count, and
bounded materialization path. Stable publication writes no replacement
monolithic raw payload.

Admission recomputes the ledger chain from its bounded records, verifies exact
contiguous coverage, validates every content-addressed block by name and size,
and hashes the last block that contains the append frontier. It also requires
the capture state, ledger epoch, materialization size, conventional digest, and
publish identity to agree. Any mismatch falls back to the existing exact
snapshot path or fails publication closed.

Raw-block records retain `raw/session.raw.jsonl` as a stable logical authority
ref. In ledger-backed mode its concrete bounded source is resolved through the
manifest storage contract; changing physical capture layout is not a segment
semantic ABI change.

The prior `raw/session.raw.jsonl` is not deleted. It remains a readable
last-good compatibility snapshot while owner readers migrate to the manifest's
raw storage contract. Raw authority remains the captured transcript evidence;
generated segments and indexes remain projections.

## Rationale

The immutable block ledger is the natural append unit. It lets capture,
overlay, stable projection, and downstream consumers advance independently
without treating one growing file as a transaction. Binding a conventional
digest and processed watermark preserves exact-source identity while making
hot publication proportional to delta rather than total history.

## Consequences

- A ledger-backed stable append writes zero historical raw bytes and reads only
  bounded ledger metadata plus the frontier block for admission.
- Filesystems without reflink support no longer force a full raw copy in the
  hot append path.
- The bounded materialization may advance ahead of the stable projection; the
  manifest watermark, not the current file end, defines the stable view.
- Legacy and non-attested captures retain the monolithic snapshot fallback.
- Explicit deep audit remains responsible for periodically rehashing historical
  content-addressed blocks and the full conventional raw digest.

## Boundaries

This decision does not make the capture ledger reviewed semantic truth, remove
raw evidence, weaken privacy filtering, or make generated indexes
authoritative. It does not yet remove the compatibility monolith or convert
every external raw reader; those changes require a reader audit and a portable
migration gate.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.md`
- `PIPELINE.md`
- `docs/decisions/AOA-SM-D-0056-merkle-semantic-component-receipts.md`

## Follow-Up Route

Measure repeated hot appends on the retained 430 MB fixture, migrate owner raw
readers to watermark-bounded composite access, and only then consider retiring
the compatibility monolith.

## Verification

Focused tests prove bounded ledger admission, zero historical raw rewrite,
semantic parity with full replay, and fail-closed rejection after same-size
frontier-block tampering. The retained 430 MB benchmark receipt must report the
ledger storage mode, zero target bytes written, bounded source bytes read, and
no swap-peak growth.
