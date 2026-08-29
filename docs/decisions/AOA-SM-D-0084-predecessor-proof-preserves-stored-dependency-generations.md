# Predecessor Proof Preserves Stored Dependency Generations

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0084
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: registry rebind, generation transition, recovery
- Projection layers: graph, entity registry
- Guard families: exact predecessor, declared transition, complete proof
- Posture: accepted

## Context

A declared graph transition can preserve the graph producer contract while its
entity-registry dependency generation changes. Predecessor reconstruction used
the current dependency generations, so it could never equal the exact stored
predecessor identity in precisely the transition it was intended to admit.

## Options Considered

- Ignore the reconstructed identity mismatch. Rejected because that would
  weaken exact predecessor proof.
- Rewrite historical graph-source generations first. Rejected because it would
  mutate the evidence being checked.
- Reconstruct producer fields from the exact predecessor source and preserve
  dependency generations from the stored predecessor identity. Accepted.

## Decision

Projection predecessor reconstruction combines the exact declared predecessor
source contract with the dependency-generation map recorded in the stored
identity. The resulting full identity must still equal that stored identity;
the exact source SHA, declared from/to pair, current target identity, and
complete materialization proof remain mandatory.

## Rationale

Producer identity and dependency identity are independent inputs to a graph
generation. Each must be reconstructed from its own authority: exact source for
the producer contract, stored predecessor identity for historical dependency
generations.

## Consequences

- Positive: declared registry-generation transitions are actually reachable.
- Positive: no historical dependency value is inferred from current runtime.
- Tradeoff: every admitted predecessor pair remains an explicit allowlist
  entry rather than general compatibility.

## Boundaries

This does not admit undeclared generations, missing predecessor source,
source-SHA mismatch, changed producer contracts, or incomplete graph
materialization.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Run graph registry rebind with the exact predecessor source. If the stored
identity or declared pair differs, fail closed and declare a separately
reviewed transition.

## Verification

Use a regression whose predecessor has a different entity-registry generation,
then run mixed-generation rebind tests, source/portable validation, and live
complete materialization proof.
