# Bounded Dirty-First Automatic Index Discovery

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0034
- Original date: 2026-07-28
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `docs/decisions/`
- Surface classes: automatic maintenance, index discovery, freshness orchestration, bounded scheduling
- Projection layers: exact session index, search projection, episode semantic projection, dense vectors, agent atlas, graph projection
- Guard families: bounded discovery, dirty-first scheduling, round-robin fairness, generated-state honesty, manual whole-scope audit
- Posture: accepted

## Context

Automatic all-session maintenance bounded the work performed after candidate
discovery, but candidate discovery itself still opened per-session manifests,
segment indexes, and projection fingerprints across the archive. Its recurring
cost therefore grew with archive size even when an automatic profile could
repair only a small batch.

Selecting only recent or already dirty sources would reduce that cost but
could indefinitely hide older drift. Treating a bounded selection as a global
scan would also allow successful timer or worker receipts to overstate
projection freshness.

## Options Considered

- Scan the whole archive before every automatic bounded maintenance run.
  Rejected because recurring discovery cost remains unbounded and can consume
  the profile budget before useful repair begins.
- Discover only recent or known-dirty sources. Rejected because sources
  outside those sets can starve indefinitely and unknown drift remains
  invisible.
- Select a fixed dirty-first discovery window with rotating dirty and general
  cursors, while retaining an unbounded explicit manual route for audits,
  migrations, and rebuild decisions.

## Decision

Automatic all-session maintenance profiles apply a fixed discovery limit
before opening per-session projection inputs. Each selection gives known-dirty
sources first opportunity, reserves capacity for a round-robin general cursor,
and advances an independent dirty cursor so a repeatedly blocked dirty source
cannot permanently occupy the window.

Cursor positions are persisted as generated orchestration state and advance
only for applying runs. Planning and dry-run operations may report the
selection without changing future scheduling order. Selection and report
packets expose the configured limit, source count, selected records, cursor
movement, and the authority boundary.

Every bounded discovery pass reports `global_scope_complete=false`. It proves
only which sources were inspected in that pass. Projection currentness remains
owned by source fingerprints, generation identities, watermarks, and
projection-specific freshness checks.

Explicit manual index maintenance without a discovery limit retains the
whole-scope route. That route is required when the operator needs an archive
audit, migration inventory, full rebuild decision, or proof that no source was
omitted by bounded discovery.

## Rationale

The selected policy bounds recurring planning cost while preserving a
deterministic convergence route. Dirty-first ordering spends scarce automatic
capacity on known actionable work. Independent cursor rotation prevents both
the dirty backlog and the general archive from being permanently hidden by
the other.

Separating a bounded discovery receipt from freshness authority prevents
timer, process, or scheduling success from becoming false evidence of global
semantic progress. Keeping an explicit whole-scope operator route preserves
strict audit and migration behavior rather than weakening those contracts to
fit an automatic budget.

## Consequences

- Automatic discovery cost is bounded by a profile-specific source window
  before expensive per-session projection inputs are opened.
- Repeated applying opportunities can cover both known-dirty and otherwise
  uninspected sources without making every recurring run a full scan.
- A bounded run can finish successfully while the global archive remains
  incomplete or stale; reports must preserve that distinction.
- An archive with a large or repeatedly blocked backlog may require many
  cycles, a compatible heavier route, or an explicit manual whole-scope pass.
- Generated cursor loss can change scheduling order but cannot change source
  evidence or make a projection current.

## Boundaries

This decision governs candidate discovery for automatic all-session index
maintenance. It does not define retrieval ranking, semantic relevance, graph
edge truth, host resource admission, a freshness SLO, or the correctness of
work performed after discovery. It does not make the discovery cursor,
maintenance report, timer, or worker evidence authority. Session-specific
cursor positions, timings, counts, and operational receipts remain in runtime
diagnostics and session provenance.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`

## Follow-Up Route

Continue live automatic trials across hot, catch-up, backlog, and deep
profiles. Review cumulative source coverage, dirty-tail rotation, no-progress
states, and heavy-work admission. Reopen the policy if randomized trials show
starvation, cursor corruption, hidden stale results, unbounded recurring cost,
or worse retrieval quality.

## Verification

Owner-neutral regressions seal a mixed clean and dirty registry, verify the
fixed selection bound, dirty-first admission, reserved general cursor,
independent cursor rotation, dry-run immutability, and explicit
`global_scope_complete=false`. Parser and profile contract checks verify that
all automatic profiles carry a discovery limit while the manual route accepts
an explicit override.

Live-shaped automatic reports must additionally demonstrate that bounded
selection precedes maintenance work, that the generated cursor advances only
with applying runs, and that remaining global work stays visible. Full source,
portable, runtime convergence, and randomized starvation checks remain
separate gates.
