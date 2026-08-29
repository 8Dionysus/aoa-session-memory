# Incompatible Atlas Generations Use the Deep Clean-Rebuild Route

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0041
- Original date: 2026-07-31
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `READINESS.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: indexing, freshness, migration, automatic maintenance, atomic publication
- Projection layers: agent atlas, atlas projection state, route readiness
- Guard families: generation identity, deep rebuild fallback, bounded catch-up, publish epoch, semantic progress
- Posture: accepted

## Context

Atlas readers already reject a root, projection state, or axis index whose
generation or publish epoch is incompatible. The producer likewise refuses an
incremental `--no-clean` update over an incompatible root. The maintenance
planner previously classified only a schema mismatch as requiring a clean
rebuild, so a producer-generation change could still be scheduled as ordinary
per-session work. That attempt was guaranteed to process nothing and fail with
an instruction to run the clean route.

Repeating a known-incompatible incremental action is not retry progress. At
the same time, letting every hot or catch-up cycle perform an all-session clean
rebuild would violate the bounded automatic profile and could block cheaper
independent work.

## Options Considered

- Let the producer reject every incompatible incremental attempt. Rejected
  because a predictable refusal is a planning error, consumes retries, and
  obscures the exact owner route that can make progress.
- Permit a bounded subset to overwrite an incompatible Atlas generation.
  Rejected because a clean Atlas publish identity covers the complete selected
  owner set; mixing old and new generation rows cannot become current.
- Run a clean all-session rebuild in any automatic profile. Rejected because
  hot and catch-up profiles do not own unbounded structural migration.
- Classify structural Atlas incompatibility before execution, defer it from
  bounded non-deep profiles, and let the resource-owned deep profile execute
  the clean build while compatible session drift remains incremental.

## Decision

Atlas maintenance distinguishes compatible per-session drift from structural
clean-rebuild conditions.

Invalid Atlas state, schema incompatibility, producer-generation mismatch,
root/projection-state generation mismatch, incomplete publish epoch, or axis
publish mismatch requires a clean rebuild. A bounded non-deep automatic
profile reports that work as deferred, returns the exact `auto-maintenance
deep` route, processes zero Atlas sessions, and does not invoke the producer
with `--no-clean`.

The deep profile may rebuild Atlas cleanly across the complete owner route. A
clean build retains the cooperative budget: budget exhaustion before publish
leaves the prior root epoch unadvanced. Missing or empty Atlas state remains
eligible for the existing bounded bootstrap because it has no incompatible
generation to preserve. Compatible source-fingerprint drift remains a bounded
incremental update.

Readers admit Atlas as current only when root index, projection state, and all
axis indexes share the expected generation and publish identity. A stale or
incomplete state may remain readable for diagnosis, but it cannot become an
answer-bearing current projection.

## Rationale

The chosen boundary makes retry behavior correspond to possible semantic
progress. Cheap profiles continue compatible work without inheriting a global
migration, while the heavier owner route receives the only operation that can
replace an incompatible generation coherently.

Generation and publish gates keep partial work fail-closed. Preserving missing
or empty bootstrap as a separate case avoids turning first installation into
an unnecessary deep migration. Keeping the rebuild budgeted preserves the
orchestration contract without weakening clean publication.

## Consequences

- Positive: known-incompatible Atlas work no longer burns an incremental retry
  and then fails predictably.
- Positive: reports expose the remaining structural work and exact deep next
  route while other projection state remains independently visible.
- Positive: compatible session changes and first bootstrap retain bounded
  incremental behavior.
- Tradeoff: Atlas can remain stale until a deep profile receives resources and
  completes the clean build.
- Tradeoff: a budget-expired clean build may need a later deep retry, but it
  does not publish a mixed epoch.

## Boundaries

This decision does not make Atlas owner truth, prove route relevance, or make
a completed process proof of freshness. It does not authorize MCP mutation,
canonical-runtime mutation, or an unbounded rebuild in hot/catch-up profiles.
It does not replace raw-ref verification, semantic evaluation, or the
projection-wide deletion, correction, tombstone, and rollback matrix.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `READINESS.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Run a preregistered clean rebuild over sealed owner sources, observe reader
admission during publication, repeat the build for semantic determinism, and
retain any unrelated stale projection as a separate residual. Reopen the
decision if a bounded profile again invokes `--no-clean` for structural drift,
deep publication admits a mixed epoch, or clean failure advances the root.

## Verification

Failure-derived tests distinguish structural drift from compatible session
drift, require catch-up to defer without invoking the Atlas producer, and
require deep planning to select a clean build. Existing failure-injection and
budget regressions keep the previous root epoch on unsuccessful clean builds.
Runtime proof uses sealed real-shaped sessions, root/state/axis publish checks,
raw hash preservation, reader polling, and two-build semantic comparison.
