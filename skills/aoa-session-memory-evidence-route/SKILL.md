---
name: aoa-session-memory-evidence-route
description: Use when an agent needs evidence from prior `.aoa` sessions about how a skill, MCP, hook, tool, API, goal, eval, test, validator, script, decision, error, receipt, or other recurring operational entity was used, what happened nearby, and which raw or segment refs prove it.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: evidence-router
---

# aoa-session-memory-evidence-route

Use this as the compact consumer route for session evidence. It finds evidence;
it does not decide repository truth, proof truth, decision truth, skill truth,
or durable memory promotion.

## Route

1. Start with the smallest typed route.
2. Use graph for topology and relation shape.
3. Use search for exact filters and recall.
4. Use raw, segment, and session refs for evidence authority.
5. Hand final judgment back to the owning surface.

## Consumer Profiles

Use these first routes when available:

- source identity, new entity registration, or “does this skill/MCP/hook/tool
  exist”: `entity-registry --lookup <anchor> --kind <kind>` first. A registered
  source entity with zero session hits means “known but not yet observed in
  session usage”, not “missing”. Registry maintenance uses
  `entity-registry-search-sync --observed-source auto` by default: it prefers
  the materialized operational route-rollup for observed archived entities,
  including stale-but-readable rollups as navigation evidence with explicit
  freshness flags, and keeps full route-term aggregation behind the explicit
  `--observed-source route-terms` heavy/deep lane. Treat registry packets as
  source/navigation identity; use usage routes for behavior evidence.
- skill, MCP, hook, tool, API, script, validator, test, eval, graph, memory
  surface, decision, error, receipt, or other operational entity usage and
  consequences: `usage-chain <anchor> --kind <kind>` first when the question
  asks how it was used and what happened after it. This is the compact hot
  route; it avoids GraphRAG, graph neighborhood, and raw-preview neighborhood
  expansion by default while preserving raw, segment, and session refs.
- Use `entity-dossier <anchor> --kind <kind>` when the question also needs the
  full graph/cooccurrence/timeline dossier, related entities, or a heavier
  one-packet human card. Use the dossier as a route packet, not as owner truth.
- skill, MCP, tool, API, script, validator, test, eval, graph, memory surface:
  use `entity-usage-audit`, then `entity-usage-neighborhood` only when the
  usage-chain is unavailable, truncated, stale, or too coarse for the needed
  source buckets or before/after evidence.
- hook health or recent hook errors: `hook-receipts` first, then
  `entity-dossier` or `entity-usage-audit` for surrounding session evidence.
- goal lifecycle: `goal-lifecycles` first. Read its `work_chain` before
  manually jumping to task or answer routes: it links generated task intervals,
  goal-event refs, answer/progress/verification/error/closeout samples, and
  exact next expansion commands. Treat `observed_goal` /
  `state_observations` from `get_goal` output as observed state evidence, not
  as proof that a `create_goal` raw event exists; keep `missing_create` visible
  when present.
- agent answers, closeouts, progress, or reasoning boundaries:
  `agent-responses`, `agent-closeouts`, `agent-progress-updates`,
  `agent-reasoning-windows`, or `answer-neighborhood`.
- exact text, path, command, error, session id, or human phrase:
  `literal-query-plan` first; follow its cheaper structured route or bounded
  raw fallback. Read `literal_route_strategy` first, then `classifications`,
  `cost_profile`, `fallback_plan`, and `next_expansion_command` before opening
  raw. The strategy names the literal class, first route, route sequence,
  monolith/raw fallback position, scoped full-text need, and exact-recall
  posture. Its nested `scoped_full_text_strategy` says whether a repeated
  literal load should first materialize a scoped full-text shard, which shard
  command to run, and which scoped query to repeat afterward. For commands, use
  the planner's command anchor for structured routes and preserve the full
  command text for exact recall. For exact session ids, use the planner's
  rehydrate/session search route before global literal fallback.
- operational route-rollup navigation: when `maintenance-status`,
  `literal-query-plan`, or another route packet says
  `use_operational_route_rollup_projection`, use
  `search-operational-route-rollup-query <query> --layer <layer>` first. This
  route reads the materialized rollup only; it must not rebuild maintenance,
  resample shards, open the monolith, use FTS, or hydrate raw body text. Human
  anchor forms such as `aoa-session-memory-mcp` are canonicalized into route
  keys such as `aoa_session_memory_mcp`; inspect `normalized_filters` if a
  result is surprising before widening the route. Read `agent_route_summary`
  and `query_route_advice` before trusting the top unfiltered rows. If
  `query_route_advice.status` is `typed_lane_detected`, run its recommended
  exact layer command before broad fuzzy results; this is especially important
  for broad human terms such as `decisions`, where path/entity rows can be
  noisy but the typed layer is `decision_thread`. If it is
  `dedicated_lane_detected`, use the returned dedicated route command first
  (for example `goal-lifecycles` or `agent-responses`). If it is
  `lane_route_detected`, keep the lane/owner boundary visible and use the
  returned command as navigation, not as truth. The summary maps
  tools, skills, MCP, hooks, APIs, plugins, goals, answers, errors, tests,
  validators, decisions, memory surfaces, graphs, evals, scripts, mechanics,
  and agents to lane-specific rollup commands or dedicated first routes such
  as `goal-lifecycles`, `agent-responses`, and graph routes.
  The materialized rollup aggregates context-tail route refs, omitted compact
  sidecar refs, and promoted protected agent-route layers (`goal`,
  `agent_event`, `decision_thread`) while keeping raw/segment refs as the
  authority handoff.
- search projection weight, context-tail pressure, or a
  `search_projection_combined_large` warning: use
  `search-operational-shrink-gates --write-report` when the operational
  route-rollup is current. The gate packet reads `route_ref_rollup_plan` and
  `physical_shrink_plan`, checks route-rollup refs/cost, literal exact-recall
  posture, live scenario corpus, and storage baseline, and still keeps
  `apply_ready=false` until the explicit apply route and after-shrink storage
  comparison exist. After a successful `search-operational-shrink-apply`
  diagnostic exists, the gate packet should expose
  `latest_shrink_apply_proof.status=found` and pass
  `storage_before_after_comparison` from that generated before/after proof;
  its projection packet should show `projection_plan_source=latest_shrink_apply_proof`
  and `cost_profile.resamples_shards=false`. Use the explicit heavy
  `search-operational-projection-plan --write-report` route only when a fresh
  shard sample or fresh unrouted-tail count is needed. The gate remains
  read-only evidence, not permission to mutate again. If the gate reports a
  missing/stale rollup, materialize the route-rollup first.
  Post-omission route-rollup must include compact
  `omitted_context_tail_route_refs` rows; an empty rollup after route-backed
  omission is a route/read-model regression. Keep unrouted context-tail rows
  and the monolith raw-text fallback until their replacements are proven.
  Routine `search-shards --no-rebuild --dirty-only` uses
  `--context-tail-omission-policy auto` by default: fresh shards resolve to
  keep-all, but an existing shard rebuilt with route-ref-backed policy is
  inherited from SQLite metadata. Read
  `context_tail_omission_policy_resolution` in the packet before assuming a
  dirty-only refresh is in rollback or slim mode; `no_dirty_sessions` is valid
  evidence when the command writes a diagnostic report.
  When the gates are ready and only the before/after comparison is missing,
  run `search-operational-shrink-apply --apply --write-report` rather than a
  naked shard rebuild. Its packet should be read as an operator route: preflight
  gates, structured shard rebuild, route-rollup refresh, route-rollup ref
  query, live scenario corpus, and storage before/after comparison. Status
  `applied_with_storage_warning` means the generated document cardinality and
  refs improved but physical bytes did not shrink; do not report that as a
  storage weight win without naming the warning.
  If stale/source-mismatched rollup is the only projection blocker, prefer
  `auto-maintenance-resource hot all --apply --skip-graph-repair --write-report`
  before re-running shrink gates; this route should refresh the rollup from
  stable shards and expose child `skipped_lock_held`/deferred statuses rather
  than hiding them as successful completion.
- relation/topology question between entities: `graph-bridge` first when the
  question asks how two anchors connect; otherwise `graph-neighborhood`,
  `graph-timeline`, `graph-shortest-path`, or `graph-cooccurrence` with
  compact node, edge, and evidence budgets.
- live route-quality regression proof: `live-scenario-corpus check` first when
  the question is whether current entity/search/literal/graph consumer routes
  still satisfy reviewed cases. Use `live-scenario-audit` for one-off
  diagnostics; use the corpus check when the result should be treated as a
  regression gate.

## MCP Preference

When `aoa-session-memory-mcp` exposes a route, prefer the MCP tool so other
agents get the same compact packets. If the live tool registry is stale or a
tool is missing, run the equivalent archive command from `/srv/AbyssOS/.aoa`:

For Codex tool discovery, search exact MCP tool names first when the general
query is fuzzy:

- transport/runtime preflight: `aoa_session_transport_preflight`
- literal planner: `aoa_session_literal_query_plan`
- entity usage dossier: `aoa_session_entity_dossier`
- entity usage-to-consequence chain: `aoa_session_entity_usage_chain`
- typed entity inventory: `aoa_session_entity_inventory`
- source/entity registry lookup: `aoa_session_entity_registry`
- usage and consequence audit: `aoa_session_entity_usage_audit`
- before/after usage windows: `aoa_session_entity_usage_neighborhood`
- hook receipts and hook failures: `aoa_session_hook_receipts`
- graph topology: `aoa_session_graph_neighborhood`
- graph relation bridge: `aoa_session_graph_bridge`
- operational route-rollup projection:
  `aoa_session_route_rollup_query`
- bounded live quality loop: `aoa_session_live_scenario_audit`
- reviewed live quality regression gate:
  `aoa_session_live_scenario_corpus_check`

Then call the MCP tool with the same typed anchor/kind that the CLI route would
use. For graph/topology questions, search `aoa_session_graph_neighborhood`
directly if a broad "graph route" tool search does not surface it.

If an exact MCP tool is discovered but the call returns `Transport closed`,
treat it as a Codex/MCP transport reload gate, not as evidence failure and not
as permission to widen into broad raw search. If the preflight tool itself is
callable, run `aoa_session_transport_preflight()` first. If direct MCP calls are
already closed, use the CLI preflight from the `abyss-stack` checkout:

```bash
cd /home/dionysus/src/abyss-stack
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src \
  python3 -m aoa_session_memory_mcp.cli transport-preflight
```

Then verify the configured stdio plane:

```bash
python3 /home/dionysus/src/abyss-stack/mcp/services/aoa-session-memory-mcp/scripts/validate_session_memory_mcp.py
```

If configured stdio is green but the current Codex session has no fresh
`aoa-session-memory` child, name CLI fallback explicitly and state that direct
MCP freshness proof requires a Codex/MCP restart.

```bash
python3 scripts/aoa_session_memory.py usage-chain <anchor> --kind <kind>
python3 scripts/aoa_session_memory.py entity-dossier <anchor> --kind <kind>
python3 scripts/aoa_session_memory.py entity-usage-audit <anchor> --kind <kind>
python3 scripts/aoa_session_memory.py entity-usage-neighborhood <anchor> --kind <kind>
python3 scripts/aoa_session_memory.py entity-registry --lookup <anchor> --kind <kind>
python3 scripts/aoa_session_memory.py literal-query-plan "<query>" --kind auto
python3 scripts/aoa_session_memory.py search-operational-route-rollup-query "<query>" --layer <layer> --limit 12 --ref-limit 3
python3 scripts/aoa_session_memory.py search-operational-shrink-apply --apply --write-report
python3 scripts/aoa_session_memory.py graph-neighborhood <anchor> --kind <kind> --limit 12 --edge-limit 48
python3 scripts/aoa_session_memory.py graph-bridge <source-anchor> <target-anchor> --source-kind <kind> --target-kind <kind>
python3 scripts/aoa_session_memory.py live-scenario-corpus check --case-limit 1
```

Name the fallback in the report. A missing MCP tool or closed MCP transport is
a runtime reload issue, not a reason to widen into unbounded raw search.

## Reading Packets

Prefer packets that expose:

- normalized entity or route candidates;
- usage, result, outcome, consequence, graph, and neighborhood counts;
- freshness, ambiguity, truncation, and omitted counts;
- agent-route lane coverage when a packet includes `agent_route_summary`; if
  a packet includes `query_route_advice`, follow typed-lane, dedicated-route,
  or owner-aware lane recommendations before broad fuzzy results;
- cost profile, especially whether a route used materialized projections or
  expanded into shard search, monolith reads, FTS, or raw hydration;
- literal route strategy, especially `uses_structured_first`, fallback
  position, and whether scoped full-text is needed before repeating a literal
  load; if `scoped_full_text_strategy.status` is
  `materialize_scoped_full_text_first`, run its first materialization command
  only as an explicit heavy/operator route and then repeat its scoped query;
- `raw`, `segment`, `segment_index`, and `session` refs;
- `next_command` or next expansion route.

Open raw or segment refs only to verify important claims, inspect exact error
text, or promote evidence into another owner layer.

## Authority Boundary

Session-memory packets are generated navigation and evidence routes. They are
weaker than:

- repo-local source files and validators;
- `docs/decisions/` records for decision truth;
- `aoa-evals` and repo-local `evals/` ports for proof truth;
- canonical skill bundles for skill meaning;
- reviewed memory or promotion surfaces for durable lessons.

Do not write or correct another owner layer from session evidence alone. Use
session evidence to choose the next source surface and cite refs.

## Verification

- State which route was used first and why.
- State whether MCP or CLI fallback was used.
- State freshness and truncation posture.
- Cite at least one raw, segment, or session ref before treating the packet as
  evidence for another owner route.
- State which owner layer receives the decision, proof, write, or promotion.
