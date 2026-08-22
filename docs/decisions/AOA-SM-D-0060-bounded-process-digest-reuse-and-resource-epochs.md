# Bounded Process Digest Reuse and Resource Epochs

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0060
- Original date: 2026-08-11
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: freshness, incremental maintenance, performance, resource admission
- Projection layers: entity registry, portable SQLite search, maintenance diagnostics
- Guard families: exact semantic digest, atomic publication, cache invalidation, resource demand epoch
- Posture: accepted

## Context

AOA-SM-D-0059 removed repeated full route-relation aggregation, but an admitted
maintenance process still recomputed the semantic digest of the same
atomically published 13-thousand-entry registry snapshot for several planning,
outbox, search-sync, and final-state consumers. The resource launcher also
retained peak observations learned from the older monolithic execution shape,
so an optimized bounded drip could be denied as though it still required the
old peak.

## Options Considered

- Recompute the snapshot digest for every consumer. Rejected because unchanged
  immutable input makes those proofs identical within one process.
- Trust the stored digest without verifying snapshot content. Rejected because
  the generated file would become its own unverified authority.
- Persist a cross-process digest cache based only on mtime. Rejected because it
  weakens replacement and rewrite detection.
- Reuse one exact digest only inside the current process while the complete file
  identity is unchanged, and advance resource-demand epochs when the execution
  envelope materially changes.

## Decision

The first entity-registry status read in a process recomputes and verifies the
exact semantic digest. Later consumers may reuse that calculation only when
resolved path, device, inode, size, nanosecond mtime, and nanosecond ctime are
unchanged before and after the snapshot read. The cache is bounded to the
current snapshot identity. Any rewrite, atomic replacement, missing stat, or
read race forces recomputation.

Search sync may use the stored digest as its snapshot signature only when the
same status packet explicitly reports that exact digest as verified. It does
not independently trust snapshot metadata.

Each automatic-maintenance profile and its index-drip fallback include the
current execution-envelope epoch in the `abyss-machine` demand key. A material
algorithmic reduction advances the epoch, preserving old observations under
their old key while allowing the new shape to learn from fresh bounded runs.
Owner memory floors remain in force.

## Rationale

File identity is used only to reuse a computation already performed on the
same immutable publication inside one process; it is not semantic identity and
does not survive process restart. This removes duplicate CPU work without
weakening the first exact proof. Epoching demand keys prevents safe admission
from being governed indefinitely by observations of code that no longer runs,
without deleting evidence or lowering owner-declared floors.

## Consequences

- Positive: repeated registry status and search-sync consumers share one exact
  digest calculation per unchanged snapshot and process.
- Positive: optimized workloads receive fresh resource learning while safety
  floors and admission reserves remain unchanged.
- Tradeoff: every new process still performs one exact registry digest, and a
  snapshot mutation deliberately pays that cost again.
- Tradeoff: a new demand epoch begins with medium-confidence owner floors until
  successful transient runs establish observed peaks.

## Boundaries

The process cache is not a persisted freshness proof, semantic identity,
cross-process authority, or replacement for the snapshot's stored digest. The
resource epoch does not bypass admission, erase old samples, lower hard
reserves, or authorize interference with concurrent workloads.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Measure consecutive live bounded cycles under the new epoch, retain the owner
floor until observed peaks converge, and optimize only independently measured
remaining phases.

## Verification

Tests prove one digest computation for repeated unchanged status reads, force a
snapshot rewrite and require recomputation, verify exact demand keys for every
profile and fallback, and retain existing semantic-digest, transactional dirty
marker, search-sync, resource-admission, and portable-export gates.
