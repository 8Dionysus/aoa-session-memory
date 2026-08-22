# Transactional Dirty Marker for Observed Route Dependency

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0059
- Original date: 2026-08-11
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: entity canonicalization, freshness, incremental maintenance, performance
- Projection layers: portable SQLite search, archived route terms, entity registry, maintenance diagnostics
- Guard families: transactional invalidation, semantic dependency, fail-closed legacy fallback, atomic publication
- Posture: accepted

## Context

AOA-SM-D-0028 requires entity-registry freshness to recompute the semantic
fingerprint of the selected observed route projection. The hot maintenance
path consequently grouped the complete `route_terms`, `document_routes`, and
`documents` relation every time registry status was requested. One bounded
session update could invoke that proof several times before, during, and after
search publication. On a large monolith the repeated proof dominated useful
session indexing even when the first recomputation had already established the
same dependency for the current transaction.

The stored semantic digest cannot be trusted without invalidation, but physical
database mtime, file size, SQLite `data_version`, and process-local caches do
not prove that every relevant writer participated or that the dependency is
unchanged.

## Options Considered

- Recompute the complete observed dependency for every status read. Rejected
  because repeated reads in one maintenance cycle perform identical global
  aggregation without strengthening the proof.
- Treat database mtime, size, or `data_version` as the dependency identity.
  Rejected because these are physical observations, not semantic identity, and
  can change for unrelated storage activity or fail to identify the mutation
  across new connections.
- Reuse the stored dependency until a scheduled deep audit. Rejected because a
  changed route projection could remain falsely current between audits.
- Install transactional SQLite triggers that set one persistent dirty marker
  for every mutation capable of changing the archived-route aggregation; use
  the stored semantic dependency only while that marker is clean, and clear it
  only after a successful exact recomputation and registry/search-sync proof.

## Decision

The monolith search store owns a versioned transactional dirty marker for the
entity registry's archived-route dependency. Triggers cover non-registry
document insertion, relevant document metadata changes and removal,
non-registry document-route changes, and route-term update or removal. The
marker is idempotent: the first relevant mutation opens the dependency proof
and later mutations in the same dirty interval add no new bookkeeping rows.

When the tracking version and all required triggers are present and the marker
is absent, entity-registry maintenance status reuses the persisted observed
semantic dependency without enumerating route terms. The packet explicitly
identifies this as a clean transactional-marker verification, not a new
semantic digest.

When tracking is missing, incompatible, incomplete, or dirty, freshness falls
back to the complete AOA-SM-D-0028 recomputation. A matching recomputation may
clear the marker only after the current registry snapshot, requested observed
source and history policy, search documents, producer generation, document
count, and snapshot signature all pass the existing sync gate. A changed
dependency rebuilds the registry and clears the marker in the same successful
search-sync transaction. A crash before that commit leaves the marker dirty
and therefore fails closed on the next read.

## Rationale

The semantic digest remains the dependency identity; the marker answers only
whether its proof has been invalidated since the last successful sync. SQLite
triggers bind invalidation to the same transactions that mutate the generated
route projection, so multiple status readers can share one exact proof without
turning process memory or physical file metadata into authority.

This preserves authoritative full rebuild behavior and incremental history
policy while changing repeated proof cost from global aggregation to a bounded
metadata read whenever no relevant mutation occurred.

## Consequences

- Positive: repeated freshness and post-publication status checks no longer
  rescan the complete route relation after one successful sync.
- Positive: legacy stores and missing triggers automatically request one exact
  recomputation before the fast path can be used.
- Positive: interrupted syncs retain a dirty marker and cannot publish a false
  clean state.
- Tradeoff: the first relevant mutation in a batch still requires one complete
  observed-dependency recomputation under the AOA-SM-D-0028 contract.
- Tradeoff: trigger installation advances the entity-registry search-sync
  contract and causes one migration catch-up on an existing store.
- Follow-up: use the materialized operational rollup or an equivalent complete
  incremental aggregate to reduce the remaining single recomputation without
  weakening exact route-term coverage.

## Boundaries

The marker is not an evidence source, semantic digest, freshness claim, entity
identity, or proof that a registry entry is correct. It does not authorize raw
deletion, bypass observed-source or history-policy checks, weaken complete
source-set retirement, or make generated route terms stronger than their raw,
segment, session, and owner refs.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Run focused trigger and registry-sync regressions, regenerate decision
indexes, validate source and standalone exports, then measure two consecutive
live bounded maintenance cycles: the migration cycle may recompute once, while
the next clean status path must not enumerate archived route terms.

## Verification

Tests create an indexed route dependency, prove that clean status raises no
route-term aggregation call, mutate the covered SQLite tables and require a
dirty full recomputation, then complete registry/search sync and prove the
clean fast path is restored. Existing observed-rollup mutation, requested
source/history-policy, incremental search replacement, generation, outbox, and
atomic publication regressions remain required.
