# Split Registry Semantic Epoch from Content Revision

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0043
- Original date: 2026-07-30
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `DESIGN.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: graph indexing, entity canonicalization, freshness, incremental maintenance, orchestration
- Projection layers: entity registry, graph source contributions, graph store, maintenance queue
- Guard families: semantic epoch, dependency pinning, proof-gated rebind, circuit breaker, full-rebuild boundary
- Posture: accepted

## Context

The graph dependency introduced by AOA-SM-D-0022 intentionally identifies one
complete persisted registry snapshot. That preserves immutable resolution
during a transaction, but the same identifier also contains the registry
content fingerprint, semantic digest, and entity count. Ordinary discovery of
one new skill, MCP tool, or CLI entity therefore changes the dependency on
every existing graph-source row.

AOA-SM-D-0031 provides a safe registry-only rebind, yet freshness routing
classified newer owner sources as a structural full-rebuild reason before the
rebind could run. Repeated bounded graph passes then selected globally stale
rows without changing semantic graph content. More sessions and entities made
that debt grow rather than converge.

## Options Considered

- Keep one global dependency identity and increase rebuild budgets. Rejected
  because recurring content growth would continue to create global work.
- Ignore registry drift until a scheduled full rebuild. Rejected because graph
  query admission would either be stale or unavailable for an unbounded time.
- Admit graph reads after changing only dependency metadata. Rejected because
  registry nodes and route relations may require rematerialization.
- Separate rare semantic-contract change from frequent content revision, route
  same-epoch growth through the existing complete proof-gated rebind, and stop
  automatic retries after explicit semantic non-progress.

## Decision

The registry graph dependency has two nested identities:

- `semantic_epoch_id` contains only declared registry schema and
  canonicalization versions. It changes for identity-policy migrations, not
  when entities are added.
- `content_revision_id` contains the source fingerprint, registry semantic
  digest, and entity count. It changes whenever the persisted registry content
  changes.

The complete `dependency_id` remains the immutable per-operation snapshot pin.
AOA-SM-D-0022 therefore remains in force for transaction reproducibility, but
its former implication that every content revision is a structural rebuild is
superseded by this decision.

When graph and registry dependency IDs differ but their semantic epochs match,
or when stronger owner sources are newer while the stored epoch is still
known, freshness reports `rebind_required`. Query admission still fails closed.
Maintenance first refreshes the persisted registry, then uses the
AOA-SM-D-0031 route to enumerate and prove the complete registry-derived
materialization, preserve the non-registry digest, and atomically advance
global and per-source pins.

Only missing or unknown dependency metadata, schema/canonicalization epoch
change, corrupt or empty graph structure, or a rejected materialization proof
crosses the full-rebuild boundary.

An automatic graph recommendation opens a circuit when the latest globally
usable maintenance report selected sources but explicitly recorded
`semantic_progress=false`. It emits no graph-maintenance command until
freshness or dependency state changes. The same guard applies when a queued
hook-worker graph job reaches execution: the job moves to the deferred queue
and is promoted automatically only after the circuit closes. A bounded check
of the selected source paths closes a no-progress circuit after an upstream
session or segment projection actually changes; unrelated background activity
does not. Capture, indexing, and non-graph sweep lanes remain independent.

## Rationale

Snapshot pinning and incremental growth solve different problems. The complete
dependency ID prevents a mixed registry transaction; the semantic epoch
determines whether old source contributions are structurally interpretable.
Separating them preserves fail-closed reads without turning every new entity
into a graph-wide source rebuild.

Reusing the complete proof-gated rebind avoids a second graph implementation.
The circuit breaker makes explicit lack of semantic progress an orchestration
fact rather than a reason to spend a larger retry budget.

## Consequences

- Positive: ordinary entity discovery no longer requires rereading every raw
  session contribution.
- Positive: dependency freshness remains exact and query admission remains
  fail closed until the atomic rebind succeeds.
- Positive: automatic maintenance stops repeating a demonstrated no-progress
  graph pass while capture and other projections continue.
- Tradeoff: the current rebind still scans all registry-derived graph
  materialization; a later reverse dependency index may reduce this to affected
  sources without weakening the proof.
- Tradeoff: the first migration from legacy dependency packets may require one
  proof-gated rebind or, when the epoch cannot be derived, one full rebuild.
- Follow-up: add an entity-to-source reverse dependency projection and classify
  add, alias, merge, split, and policy changes for affected-subgraph rebind.

## Boundaries

The semantic epoch does not prove that a registry entity or alias is correct.
The registry remains generated navigation, weaker than owner sources. This
decision does not make merge, split, or canonical remap safe without a complete
materialization proof, and it does not hide unresolved source-generation or
graph-schema migrations.

The circuit breaker is not a freshness claim and does not discard queued work.
Resource retry intent is cleared, while an already queued hook-worker graph job
is retained as deferred work. It prevents automatic repetition until a
relevant state transition supplies a new reason to run.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `DESIGN.md`
- `docs/decisions/`

## Follow-Up Route

Observe the first owner-store registry refresh and dry-run rebind. Retain the
before/after dependency IDs, semantic epoch, non-registry digest, materialized
row counts, and post-commit query state. Design the reverse dependency index
only from those measured fanout and timing results.

## Verification

Focused tests prove that entity addition changes content revision and complete
dependency IDs without changing semantic epoch, owner-source growth requests a
rebind without a full rebuild, legacy dependency packets derive the same
declared epoch, stale reads still abstain, and explicit semantic non-progress
returns an empty circuit-broken maintenance command. Existing rebind,
transaction rollback, materialization, generation-transition, and full-suite
tests remain required.
