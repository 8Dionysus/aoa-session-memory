# Authoritative Registry Rebuild Excludes Generated History

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0028
- Original date: 2026-07-20
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: entity canonicalization, indexing, freshness, reproducibility, migration
- Projection layers: entity registry, search entity documents, route terms, graph dependency
- Guard families: generation identity, source authority, deterministic rebuild, freshness invalidation, bounded history
- Posture: accepted

## Context

A sealed double rebuild exposed a fixed-point failure. The first full rebuild
materialized a new entity registry and graph, while the second rebuild from the
same preserved sessions produced different registry and graph semantics. The
full search route had read the previously generated entity-registry snapshot
and an older operational rollup before publishing fresh route terms. A later
registry sync then considered the snapshot current because freshness covered
runtime sources but not the observed route projection.

The previous registry was useful navigation history during incremental
maintenance, but it had become an undeclared semantic input to a supposedly
authoritative rebuild. That made a generated read model act as a hidden source
of truth and delayed convergence by one generation.

## Options Considered

- Ignore registry and graph differences when raw inputs match. Rejected because
  the changed canonical identities and graph contributions are answer-bearing
  semantics, not volatile publication metadata.
- Treat the previous entity registry as authoritative for every rebuild.
  Rejected because the registry is a derived projection and can retain removed,
  stale, or incorrectly canonicalized candidates.
- Drop all previous-snapshot history from both full and incremental routes.
  Rejected because bounded retired-name and alias history remains useful for
  navigation while current evidence catches up.
- Give full and incremental work explicit history policies, derive a full
  rebuild only from current declared owner sources and route terms built in the
  same candidate store, and include the selected observed projection in the
  registry freshness identity.

## Decision

Entity-registry construction has two explicit policies.

An authoritative full rebuild derives registry semantics only from current
declared owner sources and the route terms built from the sealed evidence
inputs in that same candidate search store. It does not merge the previously
published registry, retain generated-only retired entries, pad current results
from an older snapshot, or prefer an older operational rollup.

Incremental refresh may preserve bounded previous-snapshot navigation history.
That input is declared through `history_policy` and
`generated_history_surfaces`; it is never listed as an owner-truth surface.
Operational rollups and archived route terms are likewise declared generated
navigation dependencies, while their resolvable raw, segment, session, skill,
MCP, CLI, or external owner refs remain stronger evidence.

Every registry snapshot persists a versioned semantic fingerprint of the
observed route entries it consumed. Freshness recomputes that dependency from
the selected current projection. A missing, unknown, unreadable, or changed
dependency makes the registry need maintenance even when runtime source
mtimes, schema, producer generation, and entity count are unchanged.

The registry generation and search-sync contracts advance when this policy
changes. Older or unknown generations remain readable only as bounded
navigation and cannot become answer candidates until the declared catch-up or
full-rebuild route succeeds.

## Rationale

The split preserves the useful behavior of incremental memory without making
history a hidden input to reproducibility proof. Building the registry from
the candidate search store makes one full rebuild a function of the sealed
owner inputs and declared generation identity. Fingerprinting the observed
dependency closes the freshness gap that a runtime-only source fingerprint
cannot see.

Explicitly classifying previous registries, rollups, and route terms as
generated surfaces keeps raw and owner evidence authoritative. It also lets
graph dependency pinning detect a genuine registry change rather than
silently inheriting a one-generation-delayed canonicalization state.

## Consequences

- Positive: repeated full rebuilds from the same sealed inputs and generation
  have one registry basis instead of a generated-to-generated feedback loop.
- Positive: observed route changes invalidate registry freshness even when
  schemas, runtime source mtimes, and cardinality remain stable.
- Positive: incremental maintenance retains bounded navigation history under
  an explicit, inspectable policy.
- Tradeoff: an authoritative rebuild can remove a generated-only retired alias
  that no current owner source or preserved evidence still supports.
- Tradeoff: changing the observed-dependency or history-policy contract
  requires registry, search-document, and dependent graph catch-up.
- Follow-up: keep the sealed real-owner double rebuild as the release gate and
  include the policy and dependency identity in source, portable, skill, CLI,
  and MCP parity proof.

## Boundaries

This decision does not make route terms or an operational rollup evidence
authority. It does not prove that an extracted alias or canonical identity is
semantically correct, merge ambiguous candidates, or admit usage,
consequence, ownership, or causal claims.

It does not require every projection to discard history. A projection may use
bounded generated history when its incremental contract declares the input,
generation, freshness effect, and fallback. Raw sessions and resolvable owner
refs remain stronger than every registry, search, or graph row.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Run the complete owner suite, regenerate and validate the repo-local KAG
family, then perform two full rebuilds from one sealed real owner corpus under
the exact committed producer generation. If the semantic digests differ,
return to the first differing projection rather than normalizing or waiving
the mismatch.

## Verification

Focused regressions mutate an observed rollup without changing runtime source
identity and require registry freshness to fail. The deterministic rebuild
regression injects a candidate that exists only in the previous generated
snapshot and requires the next authoritative rebuild to exclude it while
preserving the registry and search semantic digests.

A no-write real-owner probe verifies that two authoritative registry builds
from the same route terms produce the same dependency and semantic digests.
The final evidence class remains a sealed, resource-observed, full H1/H2
rebuild with raw-authority equality and dependent graph comparison; that
runtime proof is not replaced by this record or its generated indexes.
