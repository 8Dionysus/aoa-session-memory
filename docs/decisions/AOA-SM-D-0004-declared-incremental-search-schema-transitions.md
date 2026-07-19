# Declared Incremental Search Schema Transitions

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0004
- Original date: 2026-07-15
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`
- Surface classes: freshness contract, search indexing, automatic maintenance, resource scheduling
- Projection layers: portable SQLite search, exact literal postings, dirty session state
- Guard families: declared schema transition, structural compatibility, bounded catch-up, deep rebuild fallback
- Posture: accepted

## Context

Automatic maintenance treated every search schema version mismatch as requiring
a full rebuild. Hot and catch-up profiles therefore deferred the search layer
to the deep profile even when the live store already had the required tables,
columns, route postings, and per-session dirty-state machinery.

That policy protects unknown migrations, but it also turns an additive epoch
change into an unnecessarily heavy operation. When unattended heavy work is
resource-blocked, compatible per-session work cannot start and a healthy retry
loop can repeatedly report launcher activity without advancing search
freshness.

## Options Considered

- Treat every schema mismatch as a full rebuild. This is conservative, but it
  lets compatible changes starve behind a heavy-only route.
- Rewrite only the global schema version or mark every session current. This
  is cheap, but it hides which session projections were actually regenerated.
- Attempt every schema mismatch incrementally. This improves liveness but can
  run an incompatible or structurally incomplete store through an unsafe path.
- Declare reviewed additive version pairs explicitly, require structural
  readiness, and keep every unprocessed session dirty while bounded workers
  advance the new epoch.

## Decision

Search schema transitions are incremental only when the source explicitly
declares the observed-to-expected version pair as compatible and the live store
already has documents, route indexes, route terms, and no structural schema
diagnostic.

For a declared transition, hot, backlog, or catch-up maintenance may use the
normal bounded dirty-session indexing path. The first committed session may
advance the store-level schema epoch, but other sessions remain stale until
their own versioned projection state is regenerated. Exact, semantic, and
other dependent projection versions continue to dirty their own rows
independently.

Unknown transitions, missing structures, empty routing surfaces, corrupt
stores, and explicitly incompatible changes retain the deep/full-rebuild
boundary.

## Rationale

An explicit transition table makes compatibility an owner-reviewed source
choice rather than an inference from a version number. Structural gates prevent
the incremental route from masking missing storage contracts. Per-session
dirty state preserves freshness honesty: advancing the global epoch opens the
bounded worker path without claiming that untouched sessions were rebuilt.

This route also respects resource scheduling. Small, restartable session
transactions can make observable progress under ordinary maintenance budgets,
while genuinely incompatible rewrites remain visible as heavy operator work.

### Review amendment — 2026-07-18

A live automatic retry exposed source drift inside the owner implementation.
The outer maintenance preflight correctly classified a declared additive
transition as incremental, but the inner index planner still treated the same
`search_schema_mismatch` reason as an unconditional full rebuild. It created a
PID-local replacement store, exceeded the cooperative profile deadline, held
the shared writer lease, and left generated temp storage after cancellation.

The inner planner now derives its rebuild boundary from the same declared
transition contract as the outer preflight. A structurally ready declared pair
therefore plans `--no-rebuild` bounded session work all the way through;
unknown or structurally incomplete transitions still route to deep recovery.
Maintenance cleanup separately recognizes dead-PID search rebuild temps. That
cleanup does not make an incompatible transition incremental and never removes
the live search store.

## Consequences

- Compatible migrations no longer wait for an unnecessary global rebuild.
- Every new additive transition requires an explicit source declaration and
  focused compatibility evidence.
- Catch-up may report partial progress for many cycles; remaining session
  counts stay visible instead of being normalized away.
- A global schema epoch can be current while dependent per-session projections
  are still stale, so consumers must continue reading freshness and projection
  versions.
- Unknown or structurally damaged stores remain deferred to deep recovery.

## Boundaries

This decision does not declare every future schema change additive, authorize
direct edits to a generated database, prove that a timer completed semantic
catch-up, weaken raw evidence authority, or change host resource policy. Live
freshness, WAL/headroom, retry behavior, and retrieval quality still require
runtime and manual evidence. Session-specific measurements remain in session
provenance.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`

## Follow-Up Route

Run the bounded automatic maintenance profile, verify that dirty counts decline
without a full rebuild, confirm important exact refs before and after, then
export and validate the standalone bundle. Add another transition pair only
after the same compatibility and resource review.

## Verification

A real stale archived session was selected and indexed through the scoped
non-rebuild route before this policy was encoded. The run advanced the store
epoch, left all other sessions dirty, preserved independently selected exact
raw refs, completed with a bounded WAL, and avoided a replacement database.
Owner-neutral regressions cover the declared transition, an unknown version,
structural drift, and the automatic catch-up branch. Exact measurements and
private evidence coordinates remain in session provenance.

An additional planner-level regression builds a current structured search
store, sets its metadata and per-session state to the declared prior schema,
and verifies that index maintenance selects one bounded incremental update
with `--no-rebuild`. The live retry and its generated orphan measurements
remain session/runtime evidence rather than decision-record content.
