# Set-Wise Append-Only Graph Batches

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0066
- Original date: 2026-08-12
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: graph indexing, incremental maintenance, performance, freshness
- Projection layers: graph source contributions, graph store, graph type counts, maintenance queue
- Guard families: bounded batch, set-wise aggregation, atomic mutation, cooperative deadline
- Posture: accepted

## Context

An ordinary live graph tail contained hundreds of new segment sources and a
small number of dirty source rows. Contribution loading completed within the
maintenance envelope, but aggregate application updated shared nodes and edges
once per new source. Repeated high-fanout JSON and type-count mutations consumed
the remaining cooperative budget, so the complete transaction rolled back and
the same bounded queue could make no progress.

## Options Considered

- Increase the cooperative or host timeout. Rejected because it preserves work
  proportional to source count and delays discovery of another failed batch.
- Reduce every append-only batch to a small fixed source count. Rejected as the
  primary route because it increases transaction and scheduling overhead while
  shared aggregates are still updated repeatedly.
- Keep per-source aggregate mutation for all inserts. Rejected because a shared
  graph entity makes batch cost grow with repeated sources rather than the
  unique affected frontier.
- Insert all new contribution and source rows, then refresh their union of
  affected aggregate IDs once inside the same transaction.

## Decision

`replace_sources` retains direct incremental aggregation for exactly one new
source. When one call admits multiple append-only sources, it first writes
their contribution and source rows, unions their node and edge IDs, and runs
one set-wise aggregate refresh over that unique frontier. Dirty, blocked, and
metadata-only sources retain their existing bounded semantics. Registry
dependency checks, cooperative deadlines, type-count deltas, and final commit
remain inside the same atomic mutation boundary.

## Rationale

The graph contribution tables already preserve the complete per-source input
needed to derive aggregates. Refreshing the union once makes cost track unique
affected graph IDs instead of repeated source occurrences, especially for
session and route nodes shared across many segments. Keeping the single-source
path avoids replacing a cheap hot-tail insert with a larger refresh protocol.
The shared transaction preserves last-good publication and truthful rollback.

## Consequences

- Positive: a multi-source append-only tail does not repeatedly mutate the same
  high-fanout aggregate or type-count row.
- Positive: inserted aggregate counts are derived against the pre-refresh store
  and remain exact across duplicated IDs in the batch.
- Positive: a budget failure still rolls back contribution rows, source rows,
  aggregates, metadata, and type counts together.
- Tradeoff: a multi-source batch retains the union of affected node and edge
  IDs in memory until the aggregate refresh reaches the atomic boundary.
- Follow-up: retain phase timings and calibrate batch limits from completed live
  receipts; split further only when a unique-ID frontier itself exceeds the
  cooperative envelope.

## Boundaries

This decision changes aggregate execution shape, not graph relation semantics,
source authority, queue admission, freshness criteria, registry generation, or
the full-rebuild boundary. A successful process still does not prove progress
without a committed mutation receipt and post-commit freshness evidence.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Run the bounded queued graph-maintenance route against a real append-only tail,
verify a committed set-wise strategy receipt, then inspect the remaining queue
through the normal freshness route without starting another full rebuild.

## Verification

A focused regression requires a multi-source batch to bypass per-source
aggregate mutation, materialize exact shared-node, event, and edge counts, and
report `batch_set_wise_refresh`. Source validation, portable parity, SQLite
integrity, and live committed-maintenance proof remain the release gates.
