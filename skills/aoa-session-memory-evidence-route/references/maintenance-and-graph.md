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

