# Search projection maintenance

All commands here mutate derived search state and require explicit operator
intent. They do not modify raw or segment evidence.

## Build and focused catch-up

Use `search-index all --write-report` for an explicit full portable index
build. Prefer `search-shards all --shard <shard> --no-rebuild --dirty-only`
when the catalog identifies a small stale set. `--dirty-only` without
`--no-rebuild` is invalid. Deferred-live sessions require the live-tail route
first or a separately stated override.

Use `entity-registry-search-sync --write-report` when only generated entity
inventory is stale.

## Shrink and omission

Read `search-operational-shrink-gates` first. A gate packet is evidence, not
mutation permission. If only operational rollup freshness blocks it, use the
generated hot maintenance lane, preserve child `skipped_lock_held` or deferred
statuses, then rerun gates.

When gates pass and before/after comparison is the remaining requirement, use
the guarded `search-operational-shrink-apply --apply --write-report` wrapper.
It owns preflight, structured rebuild, route-rollup refresh, ref query, live
scenario check, and storage comparison.

Route-ref-backed omission may remove only eligible context-tail documents
from structured shards. It must preserve protected agent/task rows, unrouted
tails, compact omitted-route refs, raw/segment evidence, and monolith fallback.
An empty rollup is a regression.

`applied_with_storage_warning` means cardinality or route refs improved but
physical bytes did not. Report that distinction and never call it a storage
win.

## Recovery

Derived search projections are reproducible. Recover by rebuilding from
current preserved session indexes, then verify provider freshness, route
rollup refs, live scenarios, and raw-hash stability. Never delete or rewrite
raw archives to repair a search projection.

