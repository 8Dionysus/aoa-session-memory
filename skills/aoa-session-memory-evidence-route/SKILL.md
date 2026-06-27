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
  session usage”, not “missing”.
- skill, MCP, tool, API, script, validator, test, eval, graph, memory surface:
  `entity-usage-audit`, then `entity-usage-neighborhood` for before/after
  evidence.
- hook health or recent hook errors: `hook-receipts` first, then
  `entity-usage-audit` for surrounding session evidence.
- goal lifecycle: `goal-lifecycles` first, then task or answer routes by refs.
  Treat `observed_goal` / `state_observations` from `get_goal` output as
  observed state evidence, not as proof that a `create_goal` raw event exists;
  keep `missing_create` visible when present.
- agent answers, closeouts, progress, or reasoning boundaries:
  `agent-responses`, `agent-closeouts`, `agent-progress-updates`,
  `agent-reasoning-windows`, or `answer-neighborhood`.
- exact text, path, command, error, session id, or human phrase:
  `literal-query-plan` first; follow its cheaper structured route or bounded
  raw fallback. For commands, use the planner's command anchor for structured
  routes and preserve the full command text for exact recall.
- relation/topology question between entities: `graph-neighborhood`,
  `graph-timeline`, `graph-shortest-path`, or `graph-cooccurrence` with compact
  node, edge, and evidence budgets.

## MCP Preference

When `aoa-session-memory-mcp` exposes a route, prefer the MCP tool so other
agents get the same compact packets. If the live tool registry is stale or a
tool is missing, run the equivalent archive command from `/srv/AbyssOS/.aoa`:

For Codex tool discovery, search exact MCP tool names first when the general
query is fuzzy:

- literal planner: `aoa_session_literal_query_plan`
- typed entity inventory: `aoa_session_entity_inventory`
- source/entity registry lookup: `aoa_session_entity_registry`
- usage and consequence audit: `aoa_session_entity_usage_audit`
- before/after usage windows: `aoa_session_entity_usage_neighborhood`
- hook receipts and hook failures: `aoa_session_hook_receipts`
- graph topology: `aoa_session_graph_neighborhood`
- bounded live quality loop: `aoa_session_live_scenario_audit`

Then call the MCP tool with the same typed anchor/kind that the CLI route would
use. For graph/topology questions, search `aoa_session_graph_neighborhood`
directly if a broad "graph route" tool search does not surface it.

If an exact MCP tool is discovered but the call returns `Transport closed`,
treat it as a Codex/MCP transport reload gate, not as evidence failure and not
as permission to widen into broad raw search. Verify the configured stdio plane
first:

```bash
python3 /home/dionysus/src/abyss-stack/mcp/services/aoa-session-memory-mcp/scripts/validate_session_memory_mcp.py
```

If configured stdio is green but the current Codex session has no fresh
`aoa-session-memory` child, name CLI fallback explicitly and state that direct
MCP freshness proof requires a Codex/MCP restart.

```bash
python3 scripts/aoa_session_memory.py entity-usage-audit <anchor> --kind <kind>
python3 scripts/aoa_session_memory.py entity-usage-neighborhood <anchor> --kind <kind>
python3 scripts/aoa_session_memory.py entity-registry --lookup <anchor> --kind <kind>
python3 scripts/aoa_session_memory.py literal-query-plan "<query>" --kind auto
python3 scripts/aoa_session_memory.py graph-neighborhood <anchor> --kind <kind> --limit 12 --edge-limit 48
```

Name the fallback in the report. A missing MCP tool or closed MCP transport is
a runtime reload issue, not a reason to widen into unbounded raw search.

## Reading Packets

Prefer packets that expose:

- normalized entity or route candidates;
- usage, result, outcome, consequence, and neighborhood counts;
- freshness, ambiguity, truncation, and omitted counts;
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
