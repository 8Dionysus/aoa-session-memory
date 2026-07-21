# Search query modes

## General and filtered query

Use `search --explain` with the narrowest known filters. Literal FTS keeps its
default timeout for live work; `--query-timeout-ms 0` is an explicit offline
scan. A timeout should return `bounded_timeout.next_expansion_command`.

Exact identifiers, commands, and short literal phrases use compatible exact
postings before lexical FTS. Read `route_selection` plus
`cost_profile.literal_postings_exact_first`, `lexical_search_executed`, and
`lexical_fallback_after_exact_miss`; a successful exact lane must not silently
pay for broad text expansion. If the projection is missing and automatic raw
fallback was disabled for an A/B probe, follow the returned explicit
session-scoped raw command or keep the answer unresolved.

For assistant answers, closeouts, progress updates, or reasoning boundaries,
prefer `agent-responses` with the matching `--agent-event`. For goals,
episodes, route signals, session acts, and entity inventory, prefer their typed
routes or structured shards.

Monthly shards are structured route projections. Literal raw-text search may
fall back to the monolith rather than fan out across all shards. This is
expected. Build full-text shards only with explicit operator intent.

## Host overlays

Semantic embedding and reranking overlays may improve orientation. Check
`search-provider-status --include-host` first and keep their output weaker than
portable `.aoa` refs. `ready_with_warnings` means use `portable_sqlite` as the
reliable archive route and report the overlay warning.

## Retrieval packets

Use `retrieve <recipe>` when a result list is too thin for bounded
continuation, hook investigation, naming review, repeated-error comparison, or
manual-review preparation.

A complete packet names:

- `evidence_hits`;
- `continuation_signals`;
- `phase_discovery`;
- `next_routes`;
- source refs and freshness.

An empty required lane is an orientation gap, not permission to guess.
