# Catch-Up Prefers Bounded Index Drip

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0062
- Original date: 2026-08-11
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: freshness, scheduling, incremental maintenance, performance, resource admission
- Projection layers: live tail, search, route indexes, maintenance diagnostics
- Guard families: bounded resource launch, dirty-first fairness, semantic progress, automatic retry
- Posture: accepted

## Context

After heavy-tail ownership moved out of catch-up, the admitted global catch-up
child could still spend more than five minutes and read over twelve gigabytes
while planning and updating an ordinary multi-projection batch. The existing
probe-class index drip completed one dirty-session slice much faster, but the
wrapper reached it only when the larger child happened to be denied by resource
admission. More available memory therefore made recurring freshness slower.

## Options Considered

- Keep resource denial as the only path to index drip. Rejected because
  freshness latency would depend inversely on available headroom and stale
  learned peaks.
- Lower the global catch-up repair limit. Rejected because global planning and
  multi-projection status costs remain in the critical timer path.
- Remove the global catch-up route. Rejected because manual and owner-profile
  convergence still need it.
- Preserve ready live-tail targeting, but when it is not ready and the timer
  explicitly enables drip, launch bounded index maintenance directly and hand
  global convergence to backlog/deep.

## Decision

For `profile=catchup`, `target=all`, applying runs with explicit
`index_drip_on_block=true` use a freshness-first route. A ready live-tail target
still launches its exact bounded child. Otherwise the wrapper skips the global
catch-up resource launch and directly admits the probe-class index drip.

The direct drip retains the existing demand epoch and owner floor, maintenance
lease, dirty-first bounded discovery, calibrated bounded repair batch,
search-shard limit, token/graph exclusion, exact child-result parsing, semantic
progress classification, and retry scheduling. Reports distinguish
`bounded_index_drip_*` from resource-blocked fallback statuses and state why
the route was preferred.

## Rationale

Recurring freshness should choose work by latency and evidence availability,
not by whether a larger job fails admission. The bounded route makes one recent
or fairly selected dirty session searchable with predictable cost, while
separate backlog/deep profiles retain eventual multi-projection convergence.

## Consequences

- Positive: additional host headroom no longer diverts the catch-up timer into
  a slower global scan.
- Positive: each timer slice has bounded work, explicit progress evidence, and
  a retry when backlog remains.
- Tradeoff: one catch-up slice may leave atlas, episode, shard, graph, or heavy
  work pending even after its selected search/route repair completes.
- Tradeoff: global convergence is intentionally distributed across repeated
  drip, backlog, deep, and explicit owner routes.

## Boundaries

`bounded_index_drip_completed` is not global freshness, graph completion, or a
claim that every session is indexed. The preference does not bypass resource
admission, lower memory floors, weaken the maintenance lock, or consume live
transcripts that have not reached their quiet-window contract.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Measure repeated live timer slices with both heavy debt and active sessions
present, then tune only the bounded drip repair count from observed per-session
cost and resource receipts.

## Verification

Tests require an explicit all-target catch-up to issue exactly one probe-class
index-maintenance launch, never the medium global child, and retain separate
tests for true resource-blocked fallback, progress-with-remaining retry,
learned-demand floors, lock conflicts, and live-tail targeting.

## Review 2026-08-13

Live convergence showed that an installed one-session batch used about
1.0-2.7 GiB peak memory but allowed a growing archive to add stale sessions as
fast as the ten-minute route retired them. The accepted route now uses the
portable default batch of 12 sessions inside the same 600-second cooperative
budget and 32 MiB per-session light-lane ceiling. The host floor and larger
learned peak still win admission, and budget exhaustion remains a normal
checkpoint. The catch-up demand epoch advances from `v7` to `v8`, so the wider
batch does not inherit an obsolete peak from the one-session execution shape.
This tunes the bounded batch; it does not widen the projection scope or convert
catch-up into a monolithic rebuild.
