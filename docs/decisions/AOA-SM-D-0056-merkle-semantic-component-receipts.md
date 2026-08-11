# Merkle Semantic Component Receipts

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0056
- Original date: 2026-08-11
- Owner surfaces: `scripts/aoa_session_memory.py`, `DESIGN.md`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: stable projection, validation, incremental maintenance, performance
- Projection layers: segment projection, session component manifest
- Guard families: semantic digest, metadata receipt, deep audit, fail-closed fallback
- Posture: accepted

## Context

The v1 session semantic digest reopened every segment index and rehashed every
segment Markdown file during every atomic publish. On the actual 430 MB append,
644 unchanged components made semantic validation proportional to total session
history even after parsing and segment construction became incremental.

## Options Considered

- Remove semantic validation. Rejected because publication still needs an
  evidence-bearing semantic projection receipt.
- Use artifact SHA alone for JSON. Rejected because projection clocks are
  intentionally non-semantic and would create false semantic changes.
- Persist a semantic digest for each immutable component and combine those
  roots in a versioned Merkle-style session root. Accepted.

## Decision

Each generated segment-index receipt carries both its exact artifact SHA-256
and a canonical JSON semantic SHA-256 excluding the established volatile keys.
Markdown already has the required exact content SHA-256. The v2 session digest
combines the canonical roots for the manifest, raw metadata, and session index
with ordered, named segment-index semantic roots and Markdown content roots.

The segment producer identity covers segment semantics and rendering inputs,
but excludes the generic immutable-receipt and deep-audit implementation that
only validates publication. Changing receipt plumbing therefore invalidates
semantic receipts without needlessly restamping every segment payload; changing
segment construction still changes the segment generation.

An unchanged component root is admitted only when the existing exact artifact
receipt remains current by size, mtime, and ctime. A legacy receipt without a
semantic root, or any metadata drift, causes that component to be opened and
recomputed. The next publication persists the new root. Explicit deep audit
continues to rehash artifact content independently.

## Rationale

Semantic roots are composable evidence; repeated parsing of immutable payloads
is not. Versioning the aggregate root makes the digest contract explicit while
preserving the distinction between semantic equality and filesystem equality.
The fallback gives existing repositories a safe one-time migration instead of
silently trusting incomplete receipts.

## Consequences

- Current append validation performs zero segment-index reads and zero segment
  Markdown hashes for unchanged components.
- The first append over legacy receipts may read each historical index once to
  migrate its semantic root; subsequent appends are metadata-only.
- The aggregate digest changes from v1 streamed canonical JSON to v2 named
  Merkle component roots; consumers must compare version and mode with SHA.
- Receipt drift and same-size corruption remain detectable through fallback
  validation and the independent deep-audit lane.

## Boundaries

This decision does not make generated indexes authoritative, replace artifact
SHA-256, weaken privacy filtering, or solve monolithic raw snapshot copying.
It does not admit a growing capture materialization as stable raw: immutable
chunk publication and bounded composite readers require a separate migration.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.md`
- `PIPELINE.md`
- `docs/decisions/AOA-SM-D-0055-bounded-incremental-reuse-admission.md`

## Follow-Up Route

Measure v2 validation on the actual 430 MB append, then design immutable raw
chunk publication with watermark-bounded readers before removing the monolithic
raw snapshot fallback.

## Verification

Focused tests prove the v2 aggregate root against a materialized reference,
prove current segment receipts avoid both JSON reads and Markdown hashes, and
retain captured-growth semantic parity plus crash/atomic-publish behavior.
