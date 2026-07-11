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
- for `usage-chain <anchor> --kind skill`, answer “what skill-linked candidate
  evidence exists”, not “the skill was invoked”. Read
  `skill_evidence.schema_version`, `state_counts`,
  `association_state_counts`, `rejection_edge_states`, `dimensions`,
  `dispatch_candidate_present`, `behavioral_candidate_present`,
  `candidate_only`, `invocation_claim_allowed`, and
  `invocation_claim_blocker`. Treat `prompt_visible`, `selected`,
  `skill_read`, `edited`, `mentioned`, `cooccurrence`, and `deflected` as
  insufficient by themselves to prove procedure execution. The currently
  declared receipt-or-review states are not automatically ingested; check
  `receipt_or_review_ingestion_available` before relying on them. Follow raw
  or segment refs plus a reviewed task episode before making invocation or
  effectiveness claims, and hand the verdict to the skill owner or
  `aoa-evals`.
- treat `state_counts` as one canonical state per archived event;
  `association_state_counts` may show weaker alternate projections. Skill
  route prefixes, `SKILL.md` paths, hyphen/underscore forms, and namespaced
  plugin names resolve to one canonical key. Do not add their counts together
  as independent evidence.
- when `quality.skill_text_fallback_deferred=true`, the bounded indexed
  outcome/entrypoint dispatch passes found no candidate and the hot route
  intentionally avoided broad FTS. Do not rewrite that as “selection did not
  happen”; use the returned literal/raw expansion only when the missing recall
  matters enough to pay for it.
- inspect `false_correlation_events`,
  `skill_evidence.correlation_rejections`, and the
  `foreign_correlated_results_rejected` noise flag for skill chains. A foreign
  result remains auditable context with its source/rejected correlation ids;
  it must never be read as a consequence. In neighborhood packets the same
  event uses `role=context` and `relation=foreign_correlation_context`.
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
- task to answer/outcome chain: `task-answer-chain` first when the task interval
  itself is the anchor. Follow `next_expansion` only for the needed task,
  answer, reasoning-boundary, or closeout lane; raw and segment refs remain
  authority.
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
  rehydrate/session search route before global literal fallback. If a noisy
  human phrase contains both broad class words and a concrete registered
  operational entity, follow the concrete entity route first; broad class
  inventory is only first when no concrete embedded entity wins.
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
- direct operational-event rollup navigation: use
  `search-operational-direct-event-rollup-query` when the question is about a
  broad event class or operational motion such as result events, command
  outputs, verification events, errors, tool outputs, or session acts. This
  route reads the materialized direct-event rollup only; it must not rebuild
  maintenance, resample shards, open the monolith, use FTS, or hydrate raw
  body text. Treat it as compact navigation over event classes, not behavior
  proof. For “how was this entity used and what happened after,” expand
  through `usage-chain <anchor> --kind <kind>` and then raw/segment refs.
- search projection weight, context-tail pressure, or a
  `search_projection_combined_large` warning: read
  `search-pressure-decision-packet` first when available, or the MCP
  `aoa_session_search_pressure_decision_packet` tool in MCP-first contexts.
  The packet exposes the current route-first decision, raw-text fallback
  boundary, operational route-rollup posture, direct-event read-model posture,
  default consumer routes, and next live scenario without rebuilding
  maintenance, resampling shards, opening the monolith, using FTS, or hydrating
  raw body text. If that route is unavailable, fall back to the compact
  `maintenance-status` packet and inspect
  `operations.search_pressure.latest_operational_projection_plan`, including
  `remaining_projection_pressure`, `context_tail_rehome_status`,
  `direct_operational_event_read_model`, `physical_shrink_plan`, and
  `next_route`. Run the
  heavier
  `search-operational-projection-plan --write-report` route only when the
  compact packet is missing, stale, or needs fresh shard/tail counts. Use
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
  compact node, edge, and evidence budgets. For dense operational anchors such
  as common tools/MCP/services, prefer `graph-cooccurrence` as the bounded
  neighboring-route packet before widening into raw search or GraphRAG.
- graph maintenance pressure: read `maintenance-status` next actions first.
  If `operations.graph_pressure` reports large cardinality or dominant edge
  classes, use `graph-high-fanout-policy` as the read-only policy packet before
  proposing graph compaction or pruning. It names dense edge classes, compact
  query routes, replacement layers, `replacement_readiness`, `prune_gate`, and
  the mutation boundary; it is not permission to delete graph rows. Treat
  `prune_gate.apply_ready=false` as the normal state until replacement
  projections prove raw/segment refs, freshness, fallback, live-scenario
  quality, and before/after cardinality.
  For `event_mentions_registered_entity`, use
  `graph-entity-usage-replacement-proof <anchor> --kind <kind>` to prove one
  dense anchor against `usage-chain` refs and graph edge samples before any
  wider replacement or pruning plan. When several dense operational anchors
  matter, run the `graph_high_fanout_replacement` live-scenario corpus case
  with reviewed `graph_replacement_probes`; it should cover tool/MCP/skill
  anchors together while keeping `prune_gate.apply_ready=false`. Use
  `live-scenario-corpus check --write-report` when high-fanout policy should
  consume the latest entity-usage replacement proof as diagnostic evidence;
  freshness is checked against the corpus definition and route code, while
  graph store `mtime` is reported as context and is not prune permission.
  For resource-blocked catchup/backlog/deep profiles, `fallback_graph_drip`
  should be interpreted as bounded generated-graph progress, not completion of
  the outer maintenance profile. Global fallbacks use the generated graph
  maintenance queue: drain existing queue items with `--use-queue`, seed from
  the graph source ledger only when the queue is empty, and keep
  `queue_had_items`, `queue_seed_from_ledger`, `queue_seed_limit`, and
  `queue_seed_include_deferred_live` visible in reports. This queue is a
  generated route/freshness aid; raw, segment, and owner layers remain the
  evidence authority. For graph deferred-live sources, read
  `live_tail.status`, `catchup_ready_to_run`, `next_ready_at`, and graph-source
  samples before running the returned catch-up command. A
  `waiting_for_quiet_window` packet means the immediate command should be the
  status retry route, while the graph catch-up command is only the post-window
  expansion.
- live route-quality regression proof: `live-scenario-corpus list` is the
  inventory route for choosing a case/profile and explaining current reviewed
  route coverage. It is read-only source corpus inventory, not live route
  proof; respect `truth_status=source_corpus_inventory_not_live_route_proof`.
  Run `live-scenario-corpus check` when the question is whether current
  entity/search/literal/graph consumer routes still satisfy reviewed cases. Use
  `live-scenario-audit` for one-off diagnostics; use the corpus check when the
  result should be treated as a regression gate. The corpus includes
  `maintenance_status` as a read-only route-guidance profile: it proves typed
  next actions and exact next commands, not that the maintenance repair itself
  has completed.

## MCP Preference

When `aoa-session-memory-mcp` exposes a route, prefer the MCP tool so other
agents get the same compact packets. If the live tool registry is stale or a
tool is missing, run the equivalent archive command from `/srv/AbyssOS/.aoa`:

For Codex tool discovery, search exact MCP tool names first when the general
query is fuzzy:

- transport/runtime preflight: `aoa_session_transport_preflight`
- frequent MCP access-plane/read-model health packet:
  `aoa_session_access_plane_preflight`
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
- dense-anchor graph cooccurrence: `aoa_session_graph_cooccurrence`
- projection/readiness status: `aoa_session_projection_status`
- search pressure decision packet:
  `aoa_session_search_pressure_decision_packet`
- operational route-rollup projection:
  `aoa_session_route_rollup_query`
- direct operational-event rollup projection:
  `aoa_session_direct_event_rollup_query`
- bounded live quality loop: `aoa_session_live_scenario_audit`
- reviewed live quality regression gate:
  `aoa_session_live_scenario_corpus_check`

Then call the MCP tool with the same typed anchor/kind that the CLI route would
use. For graph/topology questions, search `aoa_session_graph_neighborhood`
directly if a broad "graph route" tool search does not surface it. For common
tools, MCP services, hooks, or skills with too many direct hits, search
`aoa_session_graph_cooccurrence` directly before widening into raw text.
For live corpus inventory, use an exact MCP inventory tool if the live registry
exposes one; otherwise use CLI `live-scenario-corpus list` before choosing a
case for `aoa_session_live_scenario_corpus_check`.
Treat projection status as a fast cached diagnostic route by default; run the
archive `projection-status --refresh-maintenance` only when the task needs a
fresh runtime maintenance packet in the same response.

If an exact MCP tool is discovered but the call returns `Transport closed`,
treat it as a Codex/MCP transport reload gate, not as evidence failure and not
as permission to widen into broad raw search. If the preflight tool itself is
callable, run `aoa_session_transport_preflight()` first. If direct MCP calls are
already closed, use the CLI preflight from the checkout that owns the
`aoa-session-memory-mcp` service:

```bash
ABYSS_STACK_ROOT=<path-to-abyss-stack-checkout>
cd "$ABYSS_STACK_ROOT"
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src \
  python3 -m aoa_session_memory_mcp.cli transport-preflight
```

Then verify the configured stdio plane:

```bash
python3 mcp/services/aoa-session-memory-mcp/scripts/validate_session_memory_mcp.py
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
python3 scripts/aoa_session_memory.py projection-status
python3 scripts/aoa_session_memory.py search-operational-route-rollup-query "<query>" --layer <layer> --limit 12 --ref-limit 3
python3 scripts/aoa_session_memory.py search-operational-direct-event-rollup-query --usage-role result --limit 12 --ref-limit 3
python3 scripts/aoa_session_memory.py search-operational-shrink-apply --apply --write-report
python3 scripts/aoa_session_memory.py graph-high-fanout-policy --limit 12
python3 scripts/aoa_session_memory.py graph-neighborhood <anchor> --kind <kind> --limit 12 --edge-limit 48
python3 scripts/aoa_session_memory.py graph-bridge <source-anchor> <target-anchor> --source-kind <kind> --target-kind <kind>
python3 scripts/aoa_session_memory.py live-scenario-corpus list
python3 scripts/aoa_session_memory.py live-scenario-corpus check --case-limit 1
```

Name the fallback in the report. A missing MCP tool or closed MCP transport is
a runtime reload issue, not a reason to widen into unbounded raw search.

## Reading Packets

Prefer packets that expose:

- normalized entity or route candidates;
- usage, result, outcome, consequence, graph, and neighborhood counts;
- for skill packets, candidate state dimensions, the invocation-claim blocker,
  and separate foreign-correlation rejection edge/unique-event counts;
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
- route-readiness shortcuts such as `latest_operational_projection_plan` under
  `operations.search_pressure`; prefer these compact packets before running a
  heavier plan whose only purpose would be to rediscover the same next route;
- corpus inventories with explicit `truth_status`, case/profile counts, and
  exact check commands; treat them as coverage maps, not live proof;
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
- For a regression claim about skill candidate semantics, run the reviewed
  `skill_candidate_semantics_contract` live-scenario corpus case. Report its
  synthetic `evidence_origin` and do not present it as observed adoption.
