# Freshness Profiles Do Not Own Heavy Tail

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0061
- Original date: 2026-08-11
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: freshness, scheduling, incremental maintenance, performance
- Projection layers: session projection, search, atlas, maintenance diagnostics
- Guard families: profile ownership, heavy-lane lease, bounded exclusion, explicit handoff
- Posture: accepted

## Context

Automatic catch-up selected one oversized generation-stale session before
ordinary bounded repair. Although the heavy builder ran outside the global
maintenance lock and excluded other heavy sessions, its catch-up slice could
spend many minutes rebuilding hundreds of megabytes of raw evidence before a
new small session became searchable. A test proved scope exclusion but did not
prove temporal non-starvation.

## Options Considered

- Keep heavy-first ordering in every profile. Rejected because freshness work
  inherits unbounded latency from historical tail size.
- Allow the heavy session to fall through ordinary repair. Rejected because it
  defeats the exclusive heavy-lane resource contract.
- Run ordinary work first and then heavy work in the same hot/catch-up process.
  Rejected because the heavy tail can still hold the recurring freshness unit
  and distort its resource learning and completion semantics.
- Assign automatic heavy projection ownership only to backlog/deep profiles;
  hot/catch-up exclude and explicitly hand off heavy candidates while
  continuing bounded work.

## Decision

`hot` and `catchup` profiles do not execute the automatic heavy projection
lane. They detect all oversized deferred or generation-stale candidates,
exclude them from locked ordinary repair, publish a handoff naming `backlog`
and `deep` as owner profiles, and continue bounded maintenance immediately.

`backlog` and `deep` retain the existing one-candidate-per-slice heavy lane,
exclusive lease, cooperative budget, checkpoint, and atomic publication
contracts. Explicit target and manual heavy routes remain available.

## Rationale

Freshness and historical convergence are different scheduling obligations.
Giving them separate profile owners prevents a large old session from deciding
the latency of newly available evidence while preserving a recurring,
resource-gated path that eventually converges the heavy tail.

## Consequences

- Positive: recent bounded sessions remain eligible even while heavy debt
  exists continuously.
- Positive: heavy work keeps its exclusive lease, checkpoints, resource class,
  and dedicated timers rather than being silently dropped.
- Tradeoff: catch-up can report remaining global work after its own bounded
  freshness scope is current.
- Tradeoff: heavy convergence depends on backlog/deep scheduling or an explicit
  target route and must not be inferred from catch-up completion.

## Boundaries

The handoff is not proof that heavy work completed, that global freshness is
current, or that raw evidence may be removed. Catch-up does not mutate or
reclassify heavy candidates and does not bypass their owner resource gate.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Measure catch-up latency with a known heavy candidate present, then measure
heavy-tail convergence independently under backlog/deep receipts.

## Verification

Tests create two heavy sessions and one fresh bounded session, require catch-up
to make no heavy builder call while still evaluating the fresh scope, require
an explicit backlog call to acquire and checkpoint the heavy lane, and retain
the lease-conflict deferral proof.
