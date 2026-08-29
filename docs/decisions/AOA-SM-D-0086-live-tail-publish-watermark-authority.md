# Live Tail Publish Watermark Authority

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0086
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: live tail, current-session retrieval, projection publication, raw capture overlay
- Projection layers: stable session projection, captured raw overlay, live owner transcript
- Guard families: atomic publish identity, attested prefix, bounded append read
- Posture: accepted

## Context

A resumed session projection can publish beyond the source snapshot that first
seeded its work while the append-only capture overlay advances further. The
live-tail route used the older `raw.source_snapshot.size` as its archive
watermark but used the growing capture materialization as its archive path.
Their sizes necessarily differed, so current-session retrieval failed closed
even though the overlay already contained an exact prefix attestation for the
published projection.

## Options Considered

- Accept the growing capture path without a prefix proof. Rejected because
  current evidence must remain append-only and authority-bounded.
- Rewrite manifest snapshots opportunistically during a query. Rejected
  because retrieval is read-only and must not repair owner state.
- Take bytes, lines, and digest from the atomic projection publish identity,
  then require the existing persistent-overlay prefix attestation. Accepted.

## Decision

Live-tail snapshot admission uses
`index_schema.projection_publish.source` as the primary stable archive
watermark. Legacy manifests fall back to raw manifest fields. A capture overlay
is admitted only when its source identity, ledger epoch, captured size, chain,
last block, and exact published-prefix digest all verify as before. If the same
owner source inode has only grown beyond the capture watermark, the immutable
capture remains readable and the uncaptured owner suffix is reported as
unscanned truncated bytes.

## Rationale

The publish identity is the authority for what the stable projection actually
covers. The capture overlay is the authority for later preserved raw bytes.
Keeping those watermarks separate lets live retrieval bridge them without
promoting either projection beyond its proof.

## Consequences

- Positive: resumed, still-growing sessions remain queryable before full
  projection catch-up.
- Positive: no manifest mutation or full prefix rehash is required when the
  persisted attestation exists.
- Tradeoff: old manifests without publish identity retain the conservative raw
  manifest fallback and may still fail closed when their evidence disagrees.

## Boundaries

This does not treat the live overlay as stable projection truth, admit a
missing prefix record, bypass source inode/size checks, or authorize exhaustive
negative claims from a bounded live-tail query. Bytes appended after the last
capture are never claimed as searched by the capture-overlay route.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Use live-tail retrieval immediately for an open session, then let ordinary
projection, search, registry, and graph catch-up proceed independently.

## Verification

Use a regression with an old source snapshot, a newer atomic publish
watermark, and a still-newer captured overlay; require the scan to begin at the
published byte boundary and retain the attested prefix digest.
