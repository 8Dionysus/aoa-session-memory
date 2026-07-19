# Maintenance and graph evidence routes

This card contains operator routes that are intentionally absent from the
compact evidence router.

## Search pressure

Use `search-pressure-decision-packet` or its MCP equivalent before a heavier
maintenance plan. If unavailable, inspect the compact `maintenance-status`
search-pressure section. Run a fresh projection plan only when counts or tail
state are missing or stale.

Treat shrink gates as read-only evidence. `apply_ready=false` is normal until
route-rollup refs, exact-recall fallback, live scenarios, privacy, and
before/after storage comparison are present. Run the explicit shrink-apply
route only after operator authorization. `applied_with_storage_warning` is not
a storage win.

Route-backed context-tail omission must leave compact rollup refs. Keep
unrouted tails and monolith fallback until their replacement is proven.
Dirty-only maintenance may inherit the recorded omission policy; inspect its
resolution instead of guessing rollback or slim mode.

## Resource-gated completion

Read `completion_semantics` before reporting an
`auto-maintenance-resource` run. Process completion, bounded semantic
progress, global completion, and global freshness are independent claims.
`completed_with_deferred_handoff` means that the selected bounded profile
finished its control flow and handed remaining work to a stronger profile; it
does not make the projections globally current.

For timer or retry origins, require `automatic_retry.target_queue_key` or
`handoff_queue_key` to name the stronger queued profile, and require retry
history disposition `scope_completed_with_deferred_handoff`. For a manual
origin, return the exact handoff command without claiming that background work
was scheduled. Neither exit code nor a successful systemd result proves
semantic freshness.

## Generation and partial publication

For generation or partial-publish suspicion, read `projection-status` before
widening retrieval. A shard fan-out packet with
`search_catalog_generation_incompatible_fallback_monolith` is an explicit
fallback, not an empty semantic result; preserve its catalog generation and
refresh command.

Atlas routes are usable only when the root, every referenced axis, and
`maps/index-state.json` share the expected generation and publish epoch.
`atlas_axis_publish_epoch_mismatch` or `atlas_publish_epoch_incomplete`
requires the clean Atlas rebuild route, never a scoped incremental repair. A
clean rebuild reporting `deferred_budget_exhausted_no_publish` preserved the
last-good Atlas and published no new route epoch. Dense `store_failed`
likewise preserves prior committed session vectors; use sparse or raw fallback
and repair that session instead of admitting the attempted dense generation.

## Graph pressure

Use `graph-high-fanout-policy` before proposing compaction or pruning. It is a
policy packet, not delete permission. For one dense anchor, use
`graph-entity-usage-replacement-proof`; for several, use the reviewed
high-fanout replacement corpus case.

Keep `prune_gate.apply_ready=false` until replacement routes preserve source
refs, freshness, fallback, route quality, privacy, and before/after
cardinality. A generated maintenance queue is scheduling state only. Raw,
segment, and owner sources remain authority.

`waiting_for_quiet_window` means retry status now and run catch-up only after
the returned time gate. A bounded fallback graph drip is progress, not
completion of the outer maintenance profile.

## Live scenarios

`live-scenario-corpus list` is source inventory, not live proof. Use
`live-scenario-corpus check` for the reviewed regression gate and
`live-scenario-audit` for one-off diagnostics. Preserve the packet's
`truth_status`, evidence origin, profile, and exact check command.

No maintenance result may authorize another mutation merely because the
previous gate or validator is green.
