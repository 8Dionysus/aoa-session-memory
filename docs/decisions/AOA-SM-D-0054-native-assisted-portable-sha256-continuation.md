# Native-Assisted Portable SHA-256 Continuation

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0054
- Original date: 2026-08-11
- Owner surfaces: `scripts/aoa_session_memory.py`, `DESIGN.md`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/benchmarks/`, `docs/decisions/`
- Surface classes: raw capture, stable projection, incremental maintenance, portability, performance
- Projection layers: raw evidence, stable session projection
- Guard families: conventional SHA-256, append proportionality, source epoch, stage-scoped generation, fail-closed fallback
- Posture: accepted

## Context

AOA-SM-D-0049 made large live capture proportional to appended bytes, but its
first implementation deliberately omitted pure-Python SHA-256 continuation
state above 64 MiB. An actual 430 MB append proved capture and postings bounded,
yet stable projection had to reread all historical raw because the capture
could not provide a current conventional whole-stream digest. The block-chain
head could not substitute for SHA-256 without changing evidence identity.

## Options Considered

- Admit the ordered block-chain head as if it were the conventional raw digest.
  Rejected because the identities are not equivalent.
- Rehash the historical prefix on every stable append. Rejected because a tiny
  append would continue to read the old 99%.
- Persist an OpenSSL context or pending raw bytes. Rejected because native ABI
  state is not a portable artifact and pending bytes may contain private raw
  evidence.
- Use native SHA-256 only while bytes are already being read, export its public
  block-aligned state into the existing portable schema, and fail closed when
  the native layout cannot prove exact parity.

## Decision

Large capture may use the host's public OpenSSL `SHA256_CTX` as an optional
in-process accelerator. Before admission, the implementation self-tests both a
multi-block digest and continuation restored from an exported aligned state.
It then exports only the eight SHA-256 state words and the block-aligned byte
watermark into the existing portable `PersistableSha256` payload. No pointer,
native object, library version, buffered context bytes, or pending raw bytes are
persisted.

Resume reconstructs either a native or portable hasher from that schema, reads
only the difference between the aligned watermark and the captured watermark
(zero to 63 bytes), verifies the prior conventional digest, and hashes the new
tail. The result remains the ordinary SHA-256 of the complete byte stream.

When OpenSSL is absent, its symbols or public layout differ, or the self-test
fails, correctness does not depend on the accelerator. A bounded epoch uses the
portable implementation; a large epoch retains exact immutable block receipts,
the predecessor chain, and an explicitly deferred conventional continuation.
An already-required stable full scan can export aligned portable state while it
reads and atomically attest that state only when its reconstructed digest equals
the scan's exact SHA-256 at the same capture watermark.

Classification producer identity no longer includes scan-planning and capture
handoff code. The previous broad classification identity and its exact dependent
segment, episode, and session-index generations are explicit predecessor
attestations: their payloads may be reused and restamped, never silently treated
as current or semantically recomputed.

## Rationale

SHA-256 compression state is sufficient for exact continuation at block
boundaries and is independent of the accelerator that produced it. Deriving it
during an unavoidable read removes repeated historical I/O without creating a
second authority, changing digest meaning, persisting raw tail bytes, or making
OpenSSL a correctness dependency. Exact predecessor admission prevents a
capture-only source-contract correction from discarding sound derived work.

## Consequences

- Positive: a large append can keep the conventional whole-stream SHA-256
  current while reading at most 63 historical boundary bytes plus the delta.
- Positive: older deferred epochs gain a one-time migration path during a full
  scan already required for their current stable projection.
- Positive: the persisted continuation is portable and contains no raw bytes.
- Tradeoff: accelerated state export relies on a self-tested public OpenSSL
  context layout on the current Linux host; unsupported hosts use the explicit
  fallback.
- Tradeoff: the source-contract split causes one exact generation transition,
  handled only through declared predecessor restamping.

## Boundaries

The native context is an optimization, not evidence authority and not a new
digest algorithm. This decision does not turn the block-chain head into raw
SHA-256, admit an unverified state payload, weaken source-epoch checks, prove a
430 MB p95 from one run, or authorize live deployment. Raw capture remains the
authority and the prior last-good projection survives every failed migration.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.md`
- `PIPELINE.md`
- `docs/benchmarks/`
- `docs/decisions/AOA-SM-D-0049-append-only-raw-capture-ledger-and-persistent-live-tail-overlay.md`

## Follow-Up Route

Run the no-swap 430 MB cold-and-growth benchmark. Admit the strict append gate
only if capture plus stable projection read old raw solely at the alignment
boundary, reuse sealed components, retain semantic parity, and complete without
swap growth.

## Verification

Focused tests cover native multi-block parity, aligned export and restore,
forced-large append continuation, exact migration of a deferred epoch, bounded
tail classification, source-contract currentness, exact predecessor admission,
and fail-closed unknown identities. Full-suite, portable-export, and actual
430 MB no-swap cold-and-growth receipts remain separate terminal evidence.
