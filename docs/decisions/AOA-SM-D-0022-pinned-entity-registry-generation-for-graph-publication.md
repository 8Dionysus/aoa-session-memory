# Pinned Entity-Registry Generation for Graph Publication

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0022
- Original date: 2026-07-19
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: graph indexing, entity canonicalization, freshness, incremental maintenance, atomic publication
- Projection layers: entity registry, graph source contributions, graph store, graph sidecar, graph query packets
- Guard families: generation identity, dependency pinning, stale abstention, mutation rollback, full-rebuild boundary
- Posture: accepted

## Context

Graph construction resolves route signals and aliases through the generated
entity registry. Resolving that registry independently for every session or
segment lets one graph generation contain more than one canonicalization
state. A registry rebuild, skill change, MCP discovery change, or alias
correction during graph work could therefore change node identities and edges
without changing the graph producer process.

Graph schema and graph-producer generation alone cannot detect that mixture.
The graph must also identify the exact registry snapshot used to build every
source contribution and must stop admitting candidates when that dependency
is no longer current.

## Options Considered

- Resolve runtime aliases dynamically for every source contribution. Rejected
  because one graph rebuild can then contain multiple canonicalization states
  and cannot be reproduced from its recorded generation.
- Copy registry entries into graph nodes without recording a dependency.
  Rejected because copied values do not prove which complete registry state
  governed missing aliases, collisions, or canonical identities.
- Treat the entity registry as graph authority. Rejected because the registry
  is itself a rebuildable projection; skills, MCP definitions, CLI contracts,
  and other owner sources remain stronger.
- Pin one verified persisted registry snapshot for the complete graph
  operation, record its dependency identity globally and per source, and
  reject reads or writes when the dependency changes.

## Decision

Every answer-bearing graph build or maintenance operation acquires one current
persisted entity-registry snapshot before graph mutation. Its dependency
identity includes registry schema and canonicalization versions, producer
generation, source fingerprint, semantic digest, and entity count.

All contributions in that operation resolve identities through the immutable
index derived from that snapshot. The graph store records the dependency
identity in global metadata and in every graph-source row. It never performs a
per-record runtime registry overlay during the operation.

Graph readers compare the stored dependency with the current persisted
registry and its stronger owner-source freshness. A missing, incompatible,
unverified, owner-obsolete, or mismatched dependency makes the graph stale and
removes it from candidate admission. A locally verified evidence contribution
may still be opened through its stronger ref, but it does not make global
graph recall current.

The persisted registry records a separate versioned fingerprint of current
runtime owner identities and content-bearing source refs. A newer source
`mtime` triggers recomputation of that fingerprint; it does not independently
declare semantic drift. Matching fingerprints keep the dependency current
after a content-equivalent rewrite. A mismatch, incomplete legacy coverage, or
unavailable comparison keeps the registry stale and preserves the graph
publication refusal.

Incremental mutation checks the pinned dependency before mutation and again
before commit. A change rolls back the transaction. Full rebuild writes a
temporary store and rechecks the dependency before atomic publication; a
rejected candidate leaves the previously published store unchanged. Legacy
stores without the dependency contract require a full rebuild rather than a
silent partial schema upgrade.

Pruning and cardinality refresh use the same mutation gate. A narrow repair
route may update the graph's declared edge-policy version, but dependency,
schema, or producer-generation drift is never treated as repairable pruning.

## Rationale

The dependency identity makes graph canonicalization reproducible without
promoting the registry to source-of-truth status. Global and per-source pins
allow both fast query admission and a precise dirty-source audit. Immutable
resolution prevents mid-run alias drift, while pre-commit checks preserve the
last published usable graph during a race.

Failing closed at query admission is safer than returning a partly recanonicalized
graph with a freshness warning after candidate selection. Keeping a declared
full-rebuild boundary for legacy stores prevents a small maintenance batch
from relabelling global metadata while aggregate rows still carry unknown
identity semantics.

## Consequences

- Positive: two graph rebuilds with the same owner inputs and dependency
  identity use the same entity resolution basis.
- Positive: registry changes make graph staleness explicit globally and for
  affected source rows; query routes abstain before traversal.
- Positive: dependency races have executable rollback and last-good
  publication behavior.
- Positive: content-equivalent owner rewrites do not discard a graph build only
  because a file timestamp advanced.
- Tradeoff: graph reads perform a bounded registry integrity and owner-source
  freshness check, including runtime fingerprint recomputation after source
  timestamp advance.
- Tradeoff: an entity-registry correction can require graph-wide catch-up or a
  full rebuild before graph candidates are admitted again.
- Follow-up: include the dependency packet in portable and MCP parity checks
  and measure its hot-route latency on the real owner store.

## Boundaries

The pinned registry is a generated dependency, not identity truth. It does not
prove that an alias is semantically correct, merge ambiguous entities, or
authorize inferred ownership, usage, causality, or consequence edges.

This decision does not make graph sidecars or MCP responses mutation
authority. It does not replace raw, segment, session, skill, MCP, CLI, or
external owner evidence. Session-specific race coordinates, source names,
timings, and randomized selections remain in session provenance.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Run deterministic double rebuild and real owner-store graph queries after the
combined semantic and lifecycle changes land. Then verify that source,
portable, standalone, skill, and MCP packets expose the same dependency and
freshness contract without copying private registry or session payloads.

## Verification

Focused tests verify global and per-source dependency pins, immutable
resolution without the dynamic registry loader, stale query abstention,
source-version mismatch reporting, pre-mutation rejection, incremental
pre-commit rollback, atomic full-rebuild rejection with the prior semantic
digest unchanged, legacy-store full-rebuild admission, and dependency-aware
pruning and cardinality gates.

The broader graph suite exercises traversal, maintenance, queueing, freshness,
storage, pruning, and relation behavior under the new contract. Final release
proof still requires deterministic double rebuild and real source,
portable, standalone, skill, and MCP packets.
