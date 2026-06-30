# AoA Session Memory

`.aoa` is the local working root for the portable session-memory bundle.

The first implementation target is Codex session capture:

```text
raw transcript jsonl
  -> raw compaction interval blocks
  -> raw block and compaction-event ledgers
  -> compaction-interval Markdown segments
  -> segment indexes
  -> universal event facets and relationships
  -> route-signal indexes for operational layers
  -> token-accounting summaries
  -> session index
  -> agent atlas route entries
  -> graph sidecar and GraphRAG packets
  -> diagnostics
  -> later reviewed distillation
```

The archive layer is intentionally non-distilling. It keeps raw material
available so later passes can extract process lessons, patterns, skill changes,
and automation candidates without losing evidence.

## Local Root

The bundle can run in two shapes:

```text
standalone repository root
workspace/.aoa
```

In another workspace, install the same kernel under that workspace's `.aoa`
root. When checked out as a standalone repository, the repository root is the
AoA root. Local AoA/Tree of Sophia meaning should remain an overlay, not a hard
dependency of the portable kernel.

## Hook Shape

Existing Codex hooks call into this layer on:

- `SessionStart`
- `UserPromptSubmit`
- `PreCompact`
- `PostCompact`
- `Stop`

The hook path is fail-open. If raw session access fails, it writes an incident
and diagnostic record instead of blocking the active Codex session.

`PreCompact` and `PostCompact` stay deliberately light in the foreground: they
record the hook receipt, mirror readable raw transcript state when cheap, and
queue `hook-worker` for the heavy archive work. `PostCompact` is the normal
automatic path for sealing the closed compaction interval into raw blocks,
segment Markdown, and segment indexes. Manual `sync`, import, or reindex are
recovery and rebuild paths. Set `AOA_SESSION_MEMORY_FULL_COMPACT_SYNC=1` or
`AOA_SESSION_MEMORY_FULL_STOP_SYNC=1` only for deliberate debugging, not for
normal long-session hooks. `AOA_SESSION_MEMORY_STOP_SYNC_MAX_BYTES` controls
the default Stop full-sync threshold.

If Codex closes without emitting a usable lifecycle hook,
`sweep-codex-sessions` is the recovery net over `~/.codex/sessions`: it
compares transcript snapshots against `.aoa` manifests and syncs only missing,
stale, deferred, hook-only, or raw-unavailable archives when run with
`--apply`.

## Session Shape

```text
sessions/
  AGENTS.md
  INDEX.md
  index.json
  2026-05-12__001__short-title/
    AGENTS.md
    SESSION.md
    session.index.json
    session.manifest.json
    hooks/
      events.jsonl
    raw/
      session.raw.jsonl
      source.json
      blocks.index.json
      compaction-events.jsonl
      blocks/
        000__initial-to-latest.raw.jsonl
    segments/
      000__initial-to-latest.md
      000__initial-to-latest.index.json
    incidents/
    distillation/
```

`sessions/<date>__<number>__<short-title>` is the canonical evidence
directory. Codex transcript identity remains inside `session.manifest.json` as
`session_id`. `codex-sessions/` is legacy-only and should be empty after
migration.

`sessions/AGENTS.md` is the archive-district route card.
`sessions/INDEX.md` and `sessions/index.json` are generated archive-local
tables of contents. They group sessions by date, list named sessions, surface
the largest archives, show naming-readiness queues, and point agents to the
right `SESSION.md` before they open heavy generated or raw material.

Naming rules live in `NAMING.md` and `config/naming-policy.json`.

Agent-facing route design lives in `DESIGN.AGENTS.md`.

The operational route lives in `PIPELINE.md`.

Current readiness and unfinished gates live in `READINESS.md`.

## Token Accounting

Generated session ledgers carry count-only token summaries. Provider usage
metadata is marked `provider_reported`; local tokenizer counts, when available,
must be marked `exact_tokenizer`; heuristic counts are `estimated`. These
ledgers stay separate, and estimated counts are never promoted to exact usage
facts.

Use:

```bash
python3 scripts/aoa_session_memory.py token-accounting all --since-days 7
python3 scripts/aoa_session_memory.py token-accounting-backfill all --since-days 7 --max-raw-mb 16
python3 scripts/aoa_session_memory.py index-maintenance all --since-days 7 --apply --token-max-raw-mb 512
```

`token-accounting` prefers generated ledgers and, when a generated ledger is
missing, may compute from preserved raw without persisting changes. Backfill is
the route that refreshes generated ledgers. `index-maintenance` includes token
backfill as its first repair action; `--token-max-raw-mb` lets large raw
sessions receive count-only ledgers without raising the raw-text extraction
limit used by search indexing. Host consumers such as
`abyss-machine ai token-accounting aoa-summary --json` must use only generated
summaries and must not read raw transcripts or mutate `.aoa`.

## Agent Answers And Task Episodes

Use the generated agent-event routes when the question is what the assistant
answered, how a task interval unfolded, or where a live session moved between
analysis, action, verification, and closeout. These routes are navigation
packets, not reviewed truth; promote or cite claims only after opening the
packet's `raw_ref`, `segment_ref`, or `segment_index_ref`.

Start with the route that matches the question:

```bash
python3 scripts/aoa_session_memory.py agent-responses --session latest --limit 20
python3 scripts/aoa_session_memory.py agent-closeouts --session latest --limit 20
python3 scripts/aoa_session_memory.py agent-progress-updates --session latest --limit 20
python3 scripts/aoa_session_memory.py agent-reasoning-windows --session latest --limit 10
python3 scripts/aoa_session_memory.py task-episodes latest --limit 20 --order recent
python3 scripts/aoa_session_memory.py answer-neighborhood --session latest --limit 10
```

For archive-wide agent-event routes on a materialized archive, add
`--use-shards`; the packet will expose `search_projection`, `cost_profile`, and
the shard refs used for the result set. Agent-event packets also expose
`quality` with freshness counts, class counts, source counts, raw/segment ref
coverage, and the latest returned event so a consumer can distinguish "latest
but stale; verify refs" from "fresh enough to use as navigation".

`agent-responses` is for assistant answers and reports. `agent-closeouts` is
for final task handoff/completion packets. `agent-progress-updates` keeps
in-flight status separate from real answers. `agent-reasoning-windows` locates
reasoning boundaries and nearby context; it must not be treated as hidden
reasoning content. When a packet says
`preview_source=encrypted_reasoning_boundary`, the encrypted content is
unavailable by design.

Assistant transitions keep handoff and resume separate. Use `--agent-event
handoff` for explicit next-agent handoff packets and `--agent-event resume` for
session/context resume packets. The legacy `assistant_handoff_or_resume` filter
expands to both new classes plus the old class for pre-v3 indexes; do not use
it when the task needs to distinguish transition meaning.

Use `task-episodes` to reconstruct a bounded task interval with the user
prompt, plans, tool/action refs, verification refs, errors/blockers, and
closeout refs. Use `answer-neighborhood` when the answer itself is not enough
and the before/after context matters.

Use `goal-lifecycles` when the question is about goal start, inspection,
completion, blocking, or intermediate goal tool observations. If a session only
preserves `get_goal` / `update_goal` after a compaction or resume boundary, the
packet may recover `objective`, `status`, and created/updated timestamps from
the linked goal tool output as `observed_goal` and `state_observations`. That is
still evidence routing: keep `missing_create` visible unless a real
`create_goal` raw event exists. Each lifecycle packet also carries a compact
`work_chain` built from generated `task_episodes`: linked task intervals,
goal-event refs, answer/progress/verification/error/closeout samples, and exact
next expansion commands for `task-episodes`, `answer-neighborhood`, and
`agent-reasoning-windows`. This is a navigation bridge only; raw and segment
refs remain the authority.

The MCP surface may expose these routes through read-only tools such as
`aoa_session_search` filters (`agent_event`, `doc_type=task_episode`) or
dedicated agent-event tools. MCP payloads are route packets with evidence refs;
raw/session files remain authoritative. If a Codex-hosted MCP tool returns
`Transport closed`, verify the service plane with the stdio smoke first:

```bash
python3 /srv/AbyssOS/8Dionysus/scripts/smoke_aoa_session_memory_mcp.py --workspace-root /srv/AbyssOS
```

A green stdio smoke proves the package/launcher path, not that the already
running Codex MCP host handle has recovered. Restart the Codex MCP host/session
before claiming live MCP tool availability.

## Session Evidence Consumer Route

Use `skills/aoa-session-memory-evidence-route` when another agent or skill asks
how a recurring operational entity was used in prior sessions and what happened
nearby. It is the compact entry for skills, MCPs, hooks, tools, APIs, goals,
evals, tests, validators, scripts, decisions, errors, and receipts.

The first route should stay typed and cheap:

```bash
python3 scripts/aoa_session_memory.py usage-chain aoa-session-memory-mcp --kind mcp
python3 scripts/aoa_session_memory.py entity-dossier aoa-session-memory-mcp --kind mcp
python3 scripts/aoa_session_memory.py entity-usage-audit aoa-session-memory-mcp --kind mcp
python3 scripts/aoa_session_memory.py entity-usage-neighborhood aoa-session-memory-mcp --kind mcp
python3 scripts/aoa_session_memory.py literal-query-plan "Traceback ValueError" --doc-type event
python3 scripts/aoa_session_memory.py literal-query-plan "python3 scripts/aoa_session_memory.py agent-event-audit latest --probe-routes"
python3 scripts/aoa_session_memory.py literal-query-plan "019e8b6e-343d-7951-87a7-579e1184cceb"
python3 scripts/aoa_session_memory.py graph-neighborhood aoa-session-memory-mcp --kind mcp --limit 12 --edge-limit 48
```

These packets are route evidence, not owner truth. Use them to find raw,
segment, and session refs, then hand decisions, eval verdicts, skill meaning,
or durable memory promotion back to the owning surface.

## Agent Atlas

`maps/` is the source-owned skeleton for the generated agent atlas.

Start at:

```text
maps/START.md
```

The atlas is organized by route axes such as work context, memory surface,
authority surface, session act, verification state, open thread, entity, tool,
MCP service/resource, hook health, delivery state, failure mode, risk, review
state, evidence provenance, owner route, freshness, runtime environment,
mutation surface, correlation, confidence, access boundary, resource profile,
operator preference, and next action. Generated entries belong under
`maps/by-*/entries/` and must point back to session, segment, and raw evidence.

Build generated atlas entries from current session indexes:

```bash
python3 scripts/aoa_session_memory.py atlas build all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write-report
```

## Graph Store And Sidecar

`graph/` is generated from session indexes, segment indexes, route signals,
event relationships, and raw refs. The live graph surface is
`graph/graph.sqlite3`: it stores session/segment graph sources, source hashes,
node/edge contributions, aggregate nodes/edges, and evidence refs. It exists so
agents can ask for a bounded neighborhood, timeline, shortest path,
cooccurrence packet, or GraphRAG packet for stable anchors such as skills,
MCPs, hooks, tools, paths, goals, failures, and decisions.

The graph materialization policy does not require every event route signal to
become an `event -> route` edge. New/rebuilt segment sources always emit
`segment_has_route_signal` summary edges with counts, while
`mentions_route_signal` event edges are reserved for concrete operational
anchors such as skills, MCPs, hooks, tools, APIs, scripts, validators, tests,
evals, playbooks, techniques, mechanics, graph, memory, goals, agents, and
Git. Exact event-level route lookup remains in segment indexes and search
postings; the graph is the bounded topology layer, not the raw authority.
`graph_sources.graph_event_route_signal_edge_policy` is part of the hot
freshness contract, so `maintenance-status` can detect policy drift without a
full session-source scan.

Build it after route indexes/search/atlas are refreshed:

```bash
python3 scripts/aoa_session_memory.py graph-build all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write \
  --force-large-export
```

For large live archives, use store-only mode when interactive graph queries
only need `graph/graph.sqlite3` and not exported sidecar snapshots:

```bash
python3 scripts/aoa_session_memory.py graph-build all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write \
  --store-only \
  --in-place \
  --progress-every 10
```

`--in-place` is valid only with `--store-only`. This route keeps raw/search/atlas
evidence as the recovery surface, avoids writing multi-GB snapshots, and
removes stale sidecar exports so freshness reports `not_exported` instead of
trusting old snapshot data.

Normal growth, mass policy drift, and empty-store recovery should use
incremental maintenance instead of a full rebuild:

```bash
python3 scripts/aoa_session_memory.py graph-maintenance all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --apply \
  --batch-limit 3 \
  --budget-seconds 300 \
  --refresh-chunk-size 512 \
  --write-report \
  --write-hash-cache
```

Hot timers intentionally keep small graph ticks. For a large global backlog,
`maintenance-status` may recommend a manual budgeted route with a larger source
batch; run it through the machine resource lane when possible:

```bash
abyss-machine resource launch --class medium --kind indexing --timeout 900 --json -- \
  python3 scripts/aoa_session_memory.py graph-maintenance all \
    --workspace-root /path/to/workspace \
    --aoa-root /path/to/workspace/.aoa \
    --apply \
    --batch-limit 25 \
    --budget-seconds 300 \
    --refresh-chunk-size 512 \
    --write-report \
    --write-hash-cache
```

Each session or segment contributes its own graph slice. When a source changes,
`graph-maintenance` deletes that source's old contribution and inserts the new
one in one SQLite transaction. Maintenance groups dirty/missing sources by
session and refreshes touched aggregate nodes/edges in batches, so a large
session is not reparsed once per source. Aggregate node/edge refresh is streamed
from SQLite and chunked by `--refresh-chunk-size`; reports include
`maintenance_detail` stats for requested ids, chunks, rows, and missing
aggregates. Unfiltered reports keep matched graph source evidence bounded as a
count plus sample; the full matched-source list is reserved for explicit
`--source-key` probes. Foreground hooks only enqueue/background graph work; they
do not run heavy graph maintenance inline. Automated graph maintenance uses
small source batches and profile-level refresh chunks because one dirty
historical session can touch thousands of edges. Maintenance plans exact
old-plus-new aggregate node/edge refresh cost before mutating, sorts actionable
sources cheap-first, and then selects only sources that fit the current batch and
refresh budgets.
`--budget-seconds` bounds live wall-clock work; if the deadline expires before
or during a mutation pass, the command records `deferred_time_budget` sources
and rolls back the in-flight mutation instead of leaving a half-refreshed graph.
During aggregate refresh, low-cardinality node ids still get a fresh
representative contribution payload so event labels and titles stay current.
High-fanout node ids reuse the existing compact aggregate payload and update
counts from the contribution summary. Edge aggregates do not run representative
payload scans during incremental refresh; their `source`, `target`, `type`, and
count come from the contribution summary, and evidence refs are still hydrated
from `edge_contribs` when a packet is read. This keeps interactive queue drips
from sorting large `edge_contribs` windows just to refresh non-authoritative
edge labels.
Deep graph source scans can reuse `graph/source-hash-cache.json` with
`--hash-mode cached` when file size and `mtime_ns` still match. Mutating
graph-maintenance source scans refresh that generated cache by default; use
`--hash-mode exact --write-hash-cache` when the operator wants an explicit full
file-read rehash, or `--hash-mode exact` without cache writes for a read-only
audit. The cache stores only path/stat/hash metadata and is not raw evidence or
graph authority.
`index-maintenance` and `auto-maintenance` also use
`graph_max_refresh_nodes` / `graph_max_refresh_edges` guards; individually
oversized sources are reported under `oversized_sources`, while sources that
fit alone but not the current combined pass are reported under
`budget_deferred_sources` for a narrower or heavier pass.

Aggregate `nodes` and `edges` in `graph.sqlite3` use compact evidence
references on new full rebuilds and on sources touched by incremental
maintenance. Full per-source evidence remains in `node_contribs` and
`edge_contribs`. Bounded graph reads hydrate refs from contribution rows on
demand, so agents still receive raw/segment/session refs without storing the
same evidence arrays twice in the aggregate tables. Existing live stores remain
mixed until a controlled `graph-build all --write --store-only --in-place`
rebuild or enough source maintenance has refreshed the touched aggregates.
If a killed full rebuild leaves `graph.sqlite3` with empty `nodes` or `edges`,
the hot route must report `graph_store_nodes_empty` /
`graph_store_edges_empty` and point to bounded `graph-maintenance --apply`
recovery. Do not retry an in-place full rebuild by default after memory
pressure.
If partial recovery leaves `graph_sources` much smaller than the source-state
ledger, the hot route must report `graph_source_ledger_store_count_mismatch`
and keep graph search unavailable until bounded maintenance catches up. A fresh
`graph-maintenance` report with non-zero `remaining_count` is also a hot-gate
signal (`latest_graph_maintenance_remaining_sources`), so an exhausted or stale
ledger cannot make a partial graph store look current.

`graph/nodes.jsonl`, `graph/edges.jsonl`, and `graph/index.json` are optional
snapshot exports from the graph store, not the live mutable database. On large
live archives these files can be multi-GB and should not be retained just for
interactive work. Remove them after proof/export with:

```bash
python3 scripts/aoa_session_memory.py graph-prune-sidecar \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --apply \
  --write-report
```

`graph-freshness-check` treats a fully absent sidecar as `not_exported`, which
is acceptable when `graph.sqlite3` remains available. Partial, invalid, or
stale sidecars are still reported so stale snapshot data is not mistaken for
current truth. If the gate reports `needs_offline_graph_build`, verify host
disk/time budget before running a full `graph-build all --write
--force-large-export`.

Older live graph stores may still contain standalone `raw_ref` nodes and
`has_raw_ref` edges from the previous materialization policy. New graph builds
keep raw refs in event/contribution evidence packets instead. Prune those
generated rows without touching raw/session evidence with:

```bash
python3 scripts/aoa_session_memory.py graph-raw-ref-prune \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --apply \
  --min-free-gb 20 \
  --write-report
```

This is a `manual-bulk` single-transaction delete route. Before `--apply` it
checks disk headroom because SQLite may create a large WAL before checkpoint;
use `--allow-low-free` only when the operator has explicitly reserved capacity
another way. The command updates graph type counts and creates SQLite freelist
pages; it does not run `VACUUM`, so the physical `graph.sqlite3` file may stay
large until a controlled rebuild or VACUUM route has enough disk headroom.

Plan that physical compaction explicitly before running it:

```bash
python3 scripts/aoa_session_memory.py graph-sqlite-compact \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write-report
```

The default route is read-only and reports conservative free-space requirements
for a staged `VACUUM INTO` copy. `--apply --method vacuum-into --target-path
...` creates and integrity-checks a compact copy without replacing the live
`graph.sqlite3`. Source-mutating `--method vacuum` requires
`--confirm-source-vacuum` and the same disk-headroom guard.

For live-churn checks, keep the strict default as full truth and use
`graph-freshness-check --stable --quiet-seconds 120` only when the operator
wants a quiescent-subset gate. Stable mode reports recent writes under
`deferred_live_sessions`; those sessions are visible but not checked.

Query examples:

```bash
python3 scripts/aoa_session_memory.py graph-neighborhood aoa-session-memory-mcp --kind mcp --depth 2
python3 scripts/aoa_session_memory.py graph-bridge aoa-session-memory-mcp exec_command --source-kind mcp --target-kind tool
python3 scripts/aoa_session_memory.py graphrag-packet --query aoa-session-memory-mcp --anchor aoa-session-memory-mcp
python3 scripts/aoa_session_memory.py graph-eval
python3 scripts/aoa_session_memory.py graph-quality-audit --write-report
python3 scripts/aoa_session_memory.py graph-quality-review diagnostics/<stamp>__graph-quality-audit.json \
  --verdict mcp_access_plane=accept:accept:"good MCP evidence route" \
  --write-report
python3 scripts/aoa_session_memory.py graph-maintenance all --apply --write-report --write-hash-cache
python3 scripts/aoa_session_memory.py graph-quality-corpus check --write-report
python3 scripts/aoa_session_memory.py live-scenario-corpus check --write-report
python3 scripts/aoa_session_memory.py graph-freshness-check --write-report
python3 scripts/aoa_session_memory.py entity-dossier aoa-session-memory-mcp --kind mcp --write-report
```

The graph is a route companion, not reviewed memory. Its packets must carry
raw/segment/session refs before an agent relies on them. `graph-quality-audit`
checks representative MCP, skill, hook, tool, path, goal, failure, and decision
anchors for those refs,
freshness, and manual-verdict readiness. Its default mode uses graph
neighborhoods plus lexical refs; pass `--full-graphrag` only for slower
offline inspection. `graph-quality-review` records verdicts over that audit and
emits quality feedback plus regression-candidate anchors; it does not mutate
raw evidence, route indexes, or reviewed memory. `graph-quality-corpus` turns
reviewed candidates into a versioned machine-readable regression corpus under
`config/graph-quality-regression-corpus.json` and can check that corpus against
current graph/search evidence. `graph-freshness-check` answers whether maps,
search, the graph store, optional sidecar snapshots, and evidence refs are
fresh enough for GraphRAG-style synthesis, and whether `index-maintenance`,
`graph-maintenance`, sidecar export/prune, or offline `graph-build` is needed.
During active writes, `--stable` reports `truth_status`, `checked_count`, and
`deferred_live_sessions` so agents do not confuse a stable subset with a strict
archive-wide gate. A fresh Codex transcript under
`~/.codex/sessions/.../rollout-*.jsonl` is enough to defer a session even when
the archive projection is older; that state means live-not-yet-archived, not
stable corruption.
`live-scenario-corpus` checks reviewed consumer-loop route controls from
`config/live-scenario-regression-corpus.json` against the current archive. It
keeps warnings as `actionable_gaps`, so allowed warning states still leave a
precise next route instead of becoming silent green. The corpus includes the
`route_rollup_query` profile so the fast materialized route-rollup consumer path
is checked for refs, freshness, and no shard/monolith/FTS/raw-hydration
expansion.
`usage-chain` builds the hot consumer packet for one stable anchor: direct
usage events, result/consequence events, refs, freshness, noise flags, and
next expansion commands without opening GraphRAG, graph neighborhood, or raw
preview neighborhoods by default.
`entity-dossier` builds the heavier human card for one stable anchor with
strong refs, weak refs, related skills/MCPs/tools/hooks/paths/goals/failures/
decisions, open questions, and a read-first route.
`graph-bridge` is the compact first graph route when the question is how two
operational anchors are connected. It combines side neighborhoods at the
requested bounded depth, compact side-neighborhood event/ref samples, evidence
refs, freshness, noise flags, timings, and expansion commands without turning
graph output into reviewed truth. The default packet keeps dense anchors cheap
through node/edge budgets and deferred timeline hydration; lower `--max-depth`
for a stricter shallow probe, or open the returned `graph-timeline` or
`shortest_path` expansion when the task needs deeper ordering or a deeper graph
path.
`performance-baseline` is route-family aware: `--kind agent_event` measures the
structured `agent-responses`/agent-event shard route and skips entity
usage/neighborhood/GraphRAG steps by default. Use explicit graph or GraphRAG
commands when the task needs deep synthesis; do not treat agent answers as
operational entity usage just to produce a timing report. For operational
entities, answer-rule diagnostics from the optional GraphRAG step are reported
as warnings so they do not hide a healthy compact evidence route; open the
GraphRAG route explicitly when that warning is the task.

Audit whether the 22 operational route layers are currently covered by
session route indexes, source atlas axes, generated atlas entries, and the
portable SQLite search route:

```bash
python3 scripts/aoa_session_memory.py route-readiness all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write-report
```

Build an unreviewed calibration packet for manual sampling of those route
layers:

```bash
python3 scripts/aoa_session_memory.py route-sample-audit all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --sample-limit 1 \
  --write-report
```

Plan or apply the automatic maintenance pass for generated route indexes,
portable search, atlas entries, and readiness reports:

```bash
python3 scripts/aoa_session_memory.py index-maintenance all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --apply \
  --write-report
```

`index-maintenance` detects missing or stale route indexes, source-newer-than
search/atlas drift, and deferred raw mirrors. `name-session --apply` queues
this maintenance route so semantic name changes do not leave search or atlas
surfaces behind the `session_id` bridge.

After classifier, schema, route-signal, or generated-projection changes, use
the named projection catch-up route so agents can see the purpose, boundary, and
next step in one packet:

```bash
python3 scripts/aoa_session_memory.py projection-catchup all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --apply \
  --write-report
```

The default `catchup` profile runs bounded batches over generated route/search,
atlas, entity, and freshness surfaces while preserving raw/session evidence as
the authority. If a full search rebuild or graph-heavy repair is required, the
payload returns a `projection-catchup --profile deep` next command and a heavy
resource launcher instead of hiding that escalation inside a generic report.
For agent/MCP routing, read `projection_completeness` first: it gives a
machine-readable status row for every generated projection surface, including
which surfaces are actionable, deferred, covered by search/index routes, or
waiting on live-tail quiet windows.

For recurring unattended upkeep, use `auto-maintenance`. It wraps the same
maintenance controller with a clean preflight gate, a lock, and bounded graph
batches:

```bash
python3 scripts/aoa_session_memory.py auto-maintenance hot \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --apply \
  --write-report
```

Profiles are `hot` (`probe`, recent route/search/atlas repair plus a small
bounded graph tick with deferred remainder allowed), `backlog` (`medium`,
recent index and graph repair, medium refresh chunks), `catchup` (`medium`,
full-scope dirty search/atlas repair in bounded batches without graph repair),
and `deep` (`heavy`, full archive repair, larger refresh chunks). Use `catchup`
when classifier or projection changes leave many historical sessions dirty and
the archive needs to converge through repeated safe batches instead of one
large rebuild. A successful bounded catch-up pass may report
`applied_with_remaining_backlog` with `expected_catchup_remaining=true`; this
means the selected repair batch landed and the remaining dirty sessions are the
next automatic queue, not a failed service. A clean `hot` or `catchup` run must
return `status=nothing_to_do`, `mutates=false`, and a `skipped_clean` action;
it must not touch graph/search read-model stores just to prove they are already
current. For a live route-cache repair
without graph cost, run
`index-maintenance --skip-graph-repair`; the report keeps graph follow-up
visible through `defer_graph_repair`. The hot profile uses
`route-cache-freshness-gates` before and after maintenance, so it does not scan
`graph.sqlite3` on the live read path, but its maintenance pass still advances
graph state in small batches. If route/search/atlas repair consumes the hot
budget before the graph tick can start, `auto-maintenance` queues a bounded
`graph_maintenance` job with the same graph guards and a separate profile graph
budget instead of requiring a manual follow-up. Search fingerprints ignore
rendered Markdown companions and can refresh stale `session_index_state`
without rebuilding session documents when the SQLite documents are already
current. Scoped route-cache freshness uses the lightweight
`session_index_state` projection state and table-existence probes instead of
counting the full `documents` and route-posting tables; full document counts
belong to explicit deep/global provider status, not the hot scoped gate. The
hot live-quiescence prefilter is mtime-only; it defers recently written live
sessions without hashing full projection sources, leaving fingerprint proof to
the bounded search/atlas freshness gates that follow.
Schema-level, missing, empty, or corrupt search stores require a full SQLite
rewrite. Non-`deep` auto profiles must report
`status=deferred_full_search_rebuild_to_deep` with a deep resource-launch
command instead of starting that rewrite from a `hot`, `backlog`, or `catchup`
timer. Manual full rebuilds may still run `search-index all --rebuild` through
the heavy resource lane.
Maintenance writers also publish a coordinator packet to
`diagnostics/maintenance-coordinator.json` while holding
`diagnostics/auto-maintenance.lock`. `maintenance-status --full` reports the
active owner job, mode (`hot`, `catchup`, `backlog`, `deep`, or
`manual-bulk`), touched projection surfaces, lock wait, deadline, last job, and
search/graph DB plus WAL sizes. Its read-only operations summary also reports
size/lock/writer warnings, recent problem jobs, the latest search-index phase
timings, slow SQLite indexes, bounded slow-session samples, last successful
auto-maintenance profiles, and `why_maintenance_long` evidence from
diagnostics. `search-index` and `search-shards` reports carry top
`slow_sessions` with session label, elapsed time, document count, docs/sec,
raw-text storage status, and shard when applicable, so agents can diagnose a
long maintenance pass without opening raw transcripts or running deep dbstat.
If `hot` finds a
bulk/catchup/deep/manual writer already holding the lease, it defers instead of
starting a competing rewrite.
Use `maintenance-cleanup` when the status packet reports stale coordinator
state or orphaned generated-store rebuild files. The cleanup route treats a lone
SQLite rollback journal such as `.graph.sqlite3.<pid>.rebuild.tmp-journal` as
part of the same generated graph rebuild tmp family, so an interrupted rebuild
cannot hide behind a missing base `.tmp` file. It removes only stale generated
maintenance artifacts and never raw transcript evidence.
Manual maintenance writers use the same shared lock but must not wait
silently behind a timer or another manual job. If the lock is held beyond the
bounded wait, the command returns a
`session_memory_maintenance_lock_conflict` packet with `mutates=false`, the
blocking owner, and lock-wait diagnostics so the agent can retry, wait, or
choose a narrower route.
When the only dirty-looking state is a live transcript quiet-window defer,
`maintenance-status` reports a `live_tail` packet. Agents should read
`live_tail.status`, `ready_count`, `waiting_count`,
`max_quiet_remaining_seconds`, and `next_ready_at` before starting catch-up.
`waiting_for_quiet_window` means stable graph/search remains usable for older
evidence while recent live claims should wait or use raw refs. `ready_for_catchup`
means the catch-up command in the packet is the next route. For deferred search
sessions this command is a targeted `index-maintenance <session>
--skip-graph-repair --apply --write-report` pass so search/atlas catch up
without turning live graph repair into a broad maintenance run. For graph
state, compare actionable and deferred counters: a
`deferred_ledger_store_missing_count` caused by a still-written transcript is a
quiet-window wait, not immediate graph repair.
without paying graph repair cost on the interactive path; the same packet keeps
the explicit graph follow-up route visible.
Host timers should run maintenance through `auto-maintenance-resource <profile>
--apply --write-report`, not by calling `abyss-machine resource launch`
directly. The wrapper still uses `abyss-machine resource launch --kind indexing
--unattended --success-on-block`, but it also writes
`diagnostics/*__auto-maintenance-resource-<profile>.json` when the host resource
gate blocks or denies the child before `auto-maintenance` starts. This keeps
heavier work outside hooks and MCP reads without hiding resource-pressure
deferrals from agents. For `catchup all`, the wrapper reuses the live-tail
packet when the quiet window is ready instead of starting broad
`auto-maintenance catchup all` for a single deferred live tail. Search-deferred
sessions launch targeted `index-maintenance <session> --skip-graph-repair
--skip-token-accounting`; graph-only deferred live sources launch the
ledger-seeded `graph-maintenance --use-queue --queue-seed-include-deferred-live`
route surfaced by `maintenance-status`. Resource-blocked catchup, backlog, and
deep runs fall back to a tightly capped probe-class graph queue drip instead
of leaving graph maintenance idle. These profiles enable this by default
because unattended medium/heavy indexing can be capped by the host resource
policy. For global fallbacks, the wrapper drains an existing generated graph
maintenance queue with `--use-queue`, or seeds an empty queue from the graph
source ledger before draining it. The fallback writes queue and ledger
freshness state so later agents see bounded progress without treating the
generated queue as evidence authority. The report keeps the outer
maintenance profile `ok=false`, records `fallback_graph_drip`, and does not
claim the full catchup/backlog/deep profile succeeded. The default fallback is
a small progress drip, currently `25` graph sources with a `300s` budget and a `25`
candidate-pool window; profile graph-drip settings control the batch, budget,
candidate-pool window, and node/edge refresh caps unless explicit CLI overrides
are passed. `fallback_graph_drip` records whether the queue already had items,
whether a ledger seed was used, the seed limit, and whether deferred-live
sources were included. Installed user timers are part of
that contract: `maintenance-status` reads their `ExecStart` lines and reports
`available_with_unit_drift` when an explicit graph-drip override no longer
matches the profile default. When a read-only MCP environment cannot query the
user systemd bus, `maintenance-status` falls back to installed unit files and
still reports the same unit-contract drift without turning the timer probe into
a false maintenance error. The fallback mutates only when the
outer resource route was called with `--apply`; use
`--no-graph-drip-on-block` only for an explicit diagnostic run that must
preserve the raw resource-blocked state.
`aoa_session_memory` MCP remains read-only and plan-only.

`maintenance-status` also reports `operations.graph_pressure` when graph
storage is large. This is a hot-path, read-only packet built from cached graph
type counts and SQLite headroom metadata. Use it to distinguish cardinality
pressure from physical SQLite reclaim before running deep audits: if top edge
types dominate, plan sharding, high-fanout edge policy, or query projections
before physical compaction. `graph-sqlite-compact` remains the explicit
preflight for staged physical shrink and must not replace live
`graph.sqlite3` by default.

## Storage Audit

Use `storage-audit` before large rebuilds, cleanup, or host storage work:

```bash
python3 scripts/aoa_session_memory.py storage-audit \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write-report
```

Add `--deep-dbstat --row-counts` only when the machine has time for heavier
SQLite inspection. The command is read-only. It reports top-level `.aoa`
weight, session raw/block/segment buckets, SQLite page and freelist state,
SQLite store metadata such as graph/search payload modes, and optional
per-table sizes. Deep graph audits also sample aggregate node/edge payloads
before estimating reclaim: table bytes are cardinality evidence, not
reclaimable bytes by themselves. If the sample shows no payload delta, the next
route is graph cardinality, sharding, or query projections, not a rebuild solely
for aggregate payload compaction.

Use `storage-maintenance` for the current lossless shrink action:

```bash
python3 scripts/aoa_session_memory.py storage-maintenance \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write-report
```

This only checkpoints/truncates graph/search SQLite WAL files. It does not
delete raw evidence, run `VACUUM`, rebuild graph/search stores, or remove raw
blocks.

The current safe storage route is:

- SQLite WAL: checkpoint/truncate with `storage-maintenance`; if readers or
  writers are active, let it defer and retry later.
- Graph store: aggregate node/edge payloads keep compact refs; packet reads
  hydrate evidence from contribution rows. Use the storage-audit aggregate
  payload sample before planning any rebuild; a large `nodes`/`edges` table with
  zero sample delta means topology/cardinality is the pressure center. Use
  `graph-cardinality` for fast materialized node/edge type counts; run
  `graph-cardinality --refresh` through the heavy resource lane only when the
  projection is missing or intentionally being rebuilt. If
  `storage-audit` reports old `raw_ref` graph materialization rows, run
  `graph-raw-ref-prune --apply --write-report` first. This route is
  `manual-bulk`, requires disk headroom for WAL growth, and physical file shrink
  still needs reserved disk for VACUUM or a controlled rebuild. Event route
  signal edge pressure should be handled by the graph event-edge policy:
  refresh or rebuild generated graph sources so wide route facets collapse to
  `segment_has_route_signal` summaries instead of per-event high-fanout edges.
  After generated cardinality is reduced, use
  `graph-sqlite-compact --write-report` as the explicit preflight before any
  physical graph SQLite compaction; its default `vacuum-into` route creates a
  checked copy and does not replace the live store.
- Search store: new search rebuilds keep full text in FTS and compressed
  `document_bodies`, while `documents.body` keeps only a bounded hot preview.
- Raw blocks: do not blindly delete duplicated raw blocks. First run
  `raw-block-ref-audit all --limit 20 --sample-limit 80 --write-report` to
  prove sampled `raw:line:N` refs resolve through the raw-block reader and
  still match the full raw transcript. Then use
  `raw-block-storage-compact all --skip-no-plain --limit 20 --estimate-compression --write-report`
  as the dry-run storage route. `raw-block-storage-compact --apply` writes
  gzip-backed raw-block sidecars and updates manifest/index storage metadata;
  plaintext block removal requires the explicit `--confirm-remove-plain` flag
  and keeps `raw/session.raw.jsonl` as authority. Apply runs through the
  maintenance coordinator as a `manual-bulk` writer so timer-driven hot
  maintenance can defer. `storage-audit` reports plaintext raw-block duplicate
  bytes separately from compressed sidecar bytes; only the plaintext duplicate
  bucket is the remaining reclaim candidate.

## Portable Route

Generate hook config for the current install:

```bash
python3 scripts/aoa_session_memory.py hooks-config \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

Run the local e2e gate:

```bash
python3 scripts/aoa_session_memory.py validate \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

Inspect native Codex hook trust:

```bash
python3 scripts/aoa_session_memory.py codex-hooks-status \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

Run the live compaction hook probe:

```bash
python3 scripts/aoa_session_memory.py codex-compact-probe \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --trust-hooks
```

Run the completion audit:

```bash
python3 scripts/aoa_session_memory.py audit \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

For a clean standalone bundle checkout, audit the package surface without
requiring local runtime sessions or a generated search DB:

```bash
python3 scripts/aoa_session_memory.py audit \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/aoa-session-memory \
  --portable-bundle
```

`audit` is intentionally stricter than `doctor`: it can return non-zero when
the local kernel is healthy but the end-to-end objective still has remaining
gates.

Stress-test a large archive without opening bulk raw material:

```bash
python3 scripts/aoa_session_memory.py stress-pass latest \
  --aoa-root /path/to/workspace/.aoa \
  --compactions 100 \
  --write
```

Discover and import historical Codex JSONL sessions:

```bash
python3 scripts/aoa_session_memory.py import-codex-sessions \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --since-days 21 \
  --dry-run \
  --write-report
```

Sweep recent Codex JSONL sessions for missed close/no-hook or stale archives:

```bash
python3 scripts/aoa_session_memory.py sweep-codex-sessions \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --since-days 7 \
  --min-age-sec 60 \
  --dry-run \
  --write-report
```

The sweep is dry-run by default. Use `--apply` to sync planned candidates.

Build a first-wave conveyor before applying batch distillation:

```bash
python3 scripts/aoa_session_memory.py batch-distill \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --since-days 21 \
  --write-report
```

The conveyor separates mechanical first-pass work from responsibility layers.
`manual_review` means agent-assisted, project-grounded review with evidence
refs, not that the operator must reread every raw transcript. Its priority
lanes are `manual_review_deep`, `manual_review_standard`, and
`manual_review_sample`. `mechanics_candidate` is reserved for significant
failure, lesson, risk, optimization, destructive-command, or failed-outcome
signals rather than every generic command/output pair or every successful
verification command.

Repair weak generated session names after imports or classifier/title changes:

```bash
python3 scripts/aoa_session_memory.py repair-session-titles all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --since-days 21 \
  --write-report
```

Add `--apply` after reviewing the planned changes. This moves archive
directories and rewrites generated identity surfaces, but does not alter raw
session evidence.

Before broad semantic naming or physical relabeling, refresh the readiness
queue:

```bash
python3 scripts/aoa_session_memory.py naming-readiness all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --refresh-indexes \
  --write-report
```

Use the resulting `blocked`, `diagnostic_only`, `needs_reindex`,
`needs_phase_discovery`, `phase_discovery_ready`, `ready_for_semantic_name`,
`readable_label`, `low_signal`, and `named` routes
to decide the next pass. Readiness is navigation, not reviewed truth.

For long sessions routed to phase discovery:

```bash
python3 scripts/aoa_session_memory.py phase-discovery <session-label-or-id> \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write \
  --write-report
```

This writes unreviewed `naming/phase-discovery.json` and `.md` candidates inside
the session archive. Use `review_queue` for candidates that need semantic
synthesis before they can be applied.

For large sessions, generate a batch assist packet before naming by hand:

```bash
python3 scripts/aoa_session_memory.py phase-review-assist <session-label-or-id> \
  --from-segment <segment-id> \
  --limit 8 \
  --write \
  --write-report
```

`phase-review-assist` writes `naming/phase-review-assist.md` and a
`phase-review-plan.template.json` with source raw refs, progress markers,
decisions, checks, errors, mutations, commands, and top paths for several
segments at once. It accelerates review, but does not apply names.

After reviewed names are filled into a plan JSON, preview or apply the batch
without hand-running one command per segment:

```bash
python3 scripts/aoa_session_memory.py apply-phase-review-plan <session-label-or-id> \
  --plan sessions/<session>/naming/phase-review-plan.json \
  --apply \
  --write-report
```

The plan route skips empty `reviewed_name` entries and applies each non-empty
item through the same guarded phase-name writer.

For mass session naming, build a wave plan:

```bash
python3 scripts/aoa_session_memory.py naming-wave build \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write \
  --write-report
```

The wave plan is the fast path for large archives: it separates sync/reindex
preflight, session-name candidates, open phase queues, diagnostic-only
archives, and low-signal probes. It writes a reviewable
`diagnostics/naming-waves/<wave-id>/naming-wave-plan.json`.

Apply only reviewed entries:

```bash
python3 scripts/aoa_session_memory.py naming-wave apply \
  --plan diagnostics/naming-waves/<wave-id>/naming-wave-plan.json \
  --apply \
  --write-report
```

Then audit naming quality:

```bash
python3 scripts/aoa_session_memory.py naming-wave audit \
  --plan diagnostics/naming-waves/<wave-id>/naming-wave-plan.json \
  --write-report
```

`naming-wave` applies semantic session names only. It does not rename archive
directories. This keeps the raw source bridge stable while making the archive
much faster to navigate.

Review and apply one phase candidate through the guarded route:

```bash
python3 scripts/aoa_session_memory.py review-phase-name <session-label-or-id> \
  --segment <segment-id> \
  --reviewed-name "<reviewed phase name>" \
  --apply \
  --write-report
```

`review-phase-name` refreshes the name indexes after a successful apply. It
rejects `--use-candidate` when a candidate still needs semantic synthesis.

Create first-wave manual review packets for deep review lanes:

```bash
python3 scripts/aoa_session_memory.py manual-review \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --since-days 21 \
  --priority deep \
  --apply \
  --write-report
```

Manual-review applies are append-only waves. Re-running the command writes the
next `manual-review-waveN` unless `--wave-id` is supplied. The session manifest
and `distillation/review.index.*` keep every wave open for later passes, so a
candidate is indexed without being treated as closed or reviewed truth.

Aggregate unreviewed promotion candidates without promoting them:

```bash
python3 scripts/aoa_session_memory.py promotion-review \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --since-days 21 \
  --write-report
```

Regenerate generated indexes from preserved raw JSONL after classifier changes:

```bash
python3 scripts/aoa_session_memory.py reindex-sessions all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --max-raw-mb 16 \
  --budget-seconds 300 \
  --dry-run \
  --write-report
```

The `latest` target resolves by transcript/raw-source activity before generated
maintenance timestamps, so a historical archive refreshed by reindexing does
not become the active-session route. For broad foreground reindexing,
`--budget-seconds` defers remaining sessions between rewrites; it does not
interrupt a selected session halfway through regeneration.

Build the portable SQLite search index from the generated archive layers:

```bash
python3 scripts/aoa_session_memory.py search-index all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write-report
```

`search-index` uses the bounded raw lexical policy by default: raw semantic
text is indexed only for sessions at or below the default `16 MiB` raw JSONL
budget, while route documents, previews, freshness, and raw/segment refs remain
available for larger sessions. Use `--max-raw-mb` for an explicit tighter or
looser budget, and reserve `--unbounded-raw-text` for a deliberate full lexical
rebuild/benchmark where the heavier FTS size is acceptable.

Search schema 10 also bounds aggregate route postings. Event documents keep
their full route postings, while aggregate `session`, `segment`,
`task_episode`, and `incident` documents store only the most frequent route
signals per high-fanout layer. The full route preview still stays in the search
row, and raw/segment refs remain authoritative; the cap prevents aggregate
documents from multiplying path/entity/mechanic postings into tens of millions
of SQLite rows.

Successful `search-index` runs also refresh `search/catalog.json`. The catalog
maps each indexed session to its current freshness, schema versions, active
projection, and future monthly shard key. Until monthly shard DBs are
materialized, the active projection is `monolith_fallback`; the catalog is the
route map for sharding, not a replacement for raw/session indexes or the search
DB. Scoped or incremental `search-index` runs refresh the catalog from selected
records plus existing catalog state for unaffected sessions, and fall back to a
full live session-index scan only when that state does not cover the indexed
rows.
If an existing shard DB carries a `session_index_state` row that is absent from
the monolith, the catalog recovers that row as
`catalog_source=shard_session_index_state_recovery`. This is generated
navigation recovery, not raw archive truth: the row stays marked with
`monolith_status=missing`, uses shard document counts, and routes any stale
state through ordinary shard maintenance rather than pretending the monolith is
authoritative for that session.

```bash
python3 scripts/aoa_session_memory.py search-catalog \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

Materialize monthly shard DBs from the same session indexes when the archive is
large enough for bounded fan-out to be useful. Shards are generated projections:
they are rebuilt with `search-shards`, checked against live session-index
fingerprints by the catalog, and queried explicitly with `search --use-shards`
or agent-event routes such as `agent-responses --use-shards`. By default,
`search-shards` builds structured route projections: route tables, bounded hot
previews, freshness state, and refs are local to the shard, while raw-text FTS
and compressed body hydration stay in the monolith fallback. Use
`search-shards --full-text` only for an explicit shard-level lexical benchmark
or diagnostic rebuild where the extra weight is intentional.

When the only non-current shard rows are recently updated live transcripts, the
operations route reports `current_with_deferred_live_updates` instead of
`search_shards_not_current`. The stale-looking row remains visible through
`live_tail` and `deferred_live_session_count`; agents should wait for the quiet
window or run the targeted catch-up route rather than rebuilding a whole shard.
When a shard has actionable stale rows, `maintenance-status` surfaces a
secondary `refresh_search_shard_structured` action in `next_actions` and
`agent_route.search_shard_next_action`. Existing shard DBs are repaired through
`search-shards --no-rebuild --dirty-only`; missing shard DBs route to a scoped
structured rebuild only when the shard lane is already in use. The generated
action deliberately omits `--full-text`, so
raw-text recall stays on the monolith fallback unless an operator explicitly
chooses a heavier shard-level lexical route.

The default context-tail omission policy for `search-shards` is `auto`.
Fresh structured shards use `keep-all`, but incremental or dirty-only refreshes
inherit an existing shard `search_context_tail_omission_policy` from SQLite
metadata. After a guarded route-ref-backed shrink, ordinary maintenance
therefore preserves the slim generated projection without needing another
explicit flag. Use `--context-tail-omission-policy keep-all` as the rollback or
debug route, and `route-ref-backed` as the explicit apply/rebuild route.

When shard freshness is current, or only has deferred live-tail updates, but
`maintenance-status` still reports `search_projection_combined_large`, treat it
as structured event/document cardinality pressure, not a SQLite vacuum or
full-text shard problem. Use
`search-projection-plan` to read the cached catalog, shard, storage, and latest
materialization summaries without broad monolith `GROUP BY` scans. The plan
keeps the stop-lines explicit: preserve agent-event, usage, consequence,
route-signal, raw/segment/session refs before reducing generic event rows; keep
the monolith raw-text fallback until a verified replacement exists.

```bash
python3 scripts/aoa_session_memory.py search-shards all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write-report

python3 scripts/aoa_session_memory.py search "hook timed out" \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --use-shards \
  --explain

python3 scripts/aoa_session_memory.py search-projection-plan \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write-report

python3 scripts/aoa_session_memory.py search-hotset-audit \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --max-shards 3 \
  --write-report

python3 scripts/aoa_session_memory.py search-hotset-audit \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --shard month/2026-06 \
  --max-shards 1 \
  --per-shard-timeout 30 \
  --write-report

python3 scripts/aoa_session_memory.py search-operational-projection-plan \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --max-shards 3 \
  --write-report

python3 scripts/aoa_session_memory.py search-operational-projection-plan \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --shard month/2026-06 \
  --max-shards 1 \
  --route-rollup-limit 0 \
  --write-report

python3 scripts/aoa_session_memory.py search-operational-route-rollup \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --max-shards 3 \
  --apply \
  --write-report

python3 scripts/aoa_session_memory.py search-operational-route-rollup-query \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --layer tool \
  --key exec_command \
  --limit 12
```

`search-hotset-audit` is the fast read-only breakdown between the cached plan
and the heavier operational projection route. It samples the largest existing
structured shard DBs with a per-shard timeout, opens no monolith, uses no FTS,
and reports doc types, usage roles, agent-event classes, event types, route
term cardinality, scoped agent-event coverage, and session hotspots. Use it
when an agent needs to answer "what is heavy and where?" before choosing a
deeper route. If a broad sample is partial, read `measurement_gap` before
guessing: it returns the partial/failed shard list and targeted
`search-hotset-audit --shard <key>` follow-up commands with a larger timeout.
That targeted route improves measurement confidence only; it does not mutate
search, raw, graph, or route-rollup truth. `agent_event` coverage is
intentionally scoped to
assistant/reasoning/agent-state events; command, tool, output, and operational
rows without `agent_event` route through `usage_role`, `event_type`,
`session_act`, and route signals instead of becoming blanket classification
gaps. The packet is pressure evidence only; raw transcripts and segment
indexes remain authority.

`search-operational-projection-plan` is the bounded follow-up for the compact
operational event projection lane. It samples existing structured shard DBs,
separates direct usage/result/outcome/entrypoint rows from protected context
rows, and reports the generic context tail that could only be reduced after
route refs and raw/segment refs have a replacement projection. Use
`--shard <key>` after a targeted hotset packet so the deeper measurement stays
on the same pressure shard instead of falling back to the largest shard. The
packet also
includes a route-ref rollup plan with top candidate route layers/terms, so the
next design step can preserve navigation fanout before any physical row
reduction. The full rollup is bounded by `--per-shard-timeout` (default 180s);
use `--route-rollup-limit 0` only for a core-count probe without route-term
detail. It does not mutate search, raw, graph, or session archives.
When the materialized operational route-rollup is already current, the same
packet reports `route_ref_rollup_plan.status=materialized_rollup_ready` and
`replacement_read_model_status=ready`. Treat sampled route-ref counts as
pressure evidence and the materialized rollup counts as the current compact
navigation surface; neither replaces raw or segment refs.
The packet also carries `physical_shrink_plan`, a read-only guarded plan for
the later generated-search shrink route. `status=guarded_plan_ready` only means
the route-ref-backed context tail has a current replacement navigation surface;
`safe_to_apply_physical_compaction` remains `false` until live-scenario,
literal-recall, route-rollup ref, storage, and bundle-parity gates prove an
explicit apply route. Unrouted context-tail rows stay in search until their own
literal/raw fallback replacement is proven.

Once a shard is rebuilt with the route-ref-backed policy, later dirty-only
maintenance should report `requested_context_tail_omission_policy=auto`,
`context_tail_omission_policy=route_ref_backed_context_tail_v1`, and
`context_tail_omission_policy_resolution.source=existing_shard_meta`. A
`no_dirty_sessions` result is still a valid proof state when the command writes
its diagnostic report.

`search-operational-shrink-gates` is the read-only gate packet for that later
physical route:

```bash
python3 scripts/aoa_session_memory.py search-operational-shrink-gates \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write-report
```

It runs the operational projection plan, materialized route-rollup ref query,
literal exact-recall probes, a bounded live-scenario corpus check, and a
lightweight search-storage baseline. The baseline checks the generated search
store and search root only; use the packet's `storage-audit` expansion command
when full storage recommendations or session/graph breakdowns are needed. A
passing gate packet still reports `apply_ready=false` until the explicit
context-tail omission/apply route and after-shrink storage comparison exist.
After `search-operational-shrink-apply --apply --write-report` has
captured a successful before/after comparison, the gate packet consumes that
latest apply diagnostic as generated proof for
`storage_before_after_comparison` and uses the current materialized
route-rollup status instead of resampling heavy shard projections or running
the full storage audit. The packet remains read-only and still does not
authorize mutation; run
`search-operational-projection-plan --write-report` when a fresh heavy shard
sample or fresh unrouted-tail count is needed. This is the route exposed by
`maintenance-status` for the current `search_projection_combined_large` warning
when the rollup is current.

`search-operational-route-rollup` is the generated replacement projection for
that next step. It materializes `search/operational-route-rollup.sqlite3` with
route term counts plus bounded raw, segment, and session ref samples for the
candidate context-tail rows, compact omitted-route sidecars, and promoted
agent-route layers that are protected from context-tail omission but still need
fast navigation (`goal`, `agent_event`, and `decision_thread`). It is still
navigation, not authority, and it does not delete or compact event rows;
physical search shrinkage must wait until this replacement route proves fresh
and useful.
When an existing materialized rollup is stale because exactly one source shard
changed, use `search-operational-route-rollup --shard <month/YYYY-MM> --apply
--write-report` to replace only that shard contribution. The scoped route keeps
the other shard rows and route refs, writes through the same generated DB, and
stays a navigation repair; full materialization remains the route for missing,
invalid, or multi-shard rollup drift.

`search-operational-route-rollup-query` is the consumer route for the current
materialized rollup. It opens only `search/operational-route-rollup.sqlite3`,
aggregates route rows by `layer/key/route_signal`, returns bounded raw,
segment, and session refs, and reports a cost profile showing that it does not
resample shards, open the monolith, use FTS, or hydrate raw body text. Use the
materialize command only for missing or stale rollups; use the query command
when the rollup is current and an agent needs compact navigation proof. The
query route canonicalizes human anchor forms such as
`aoa-session-memory-mcp` into the route-signal key form
`aoa_session_memory_mcp`; the packet exposes `normalized_filters` so agents can
see the canonical terms without guessing them or widening into broad search.
The query packet also includes `agent_route_summary`, a compact lane map for
tools, skills, MCP, hooks, APIs, plugins, goals, answers, errors, tests,
validators, decisions, memory surfaces, graphs, evals, scripts, mechanics, and
agents. Use that summary to choose a lane-specific rollup query or a dedicated
first route such as `goal-lifecycles`, `agent-responses`, or graph routes
without widening into broad search. Typed lanes are counted by their route
layer, not by incidental text matches; if a broad query such as `decisions`
returns path/entity noise, follow `query_route_advice.recommended_layer` before
trusting the broad result order.

`maintenance-status --full` surfaces this rollup under
`operations.search_pressure.operational_route_rollup`. If the rollup is missing
or stale, the search projection next-action routes to
`search-operational-route-rollup --apply --write-report`, or to the scoped
`--shard` form when a single source shard changed; once it is current, the
next-action becomes `use_operational_route_rollup_projection` and points to
`search-operational-route-rollup-query` instead of repeating sampling or the
cardinality plan.

`index-maintenance` also treats a missing or stale operational route-rollup as
a generated read-model repair when search shards are current. This lets
`auto-maintenance` refresh the rollup through the normal maintenance pipeline
without giving the rollup authority over raw transcripts or segment evidence.
When the only stale read-model is this rollup, `maintenance-status` surfaces
the dedicated rollup repair instead of a broad `index-maintenance all`; graph
live-tail catch-up remains a separate follow-up. When the rollup is already
current, the shrink-gate command is an advisory read-only pressure check, not a
blocking repair.

For MCP and agent fast paths, prefer structured filters such as `--agent-event`,
`--session-act`, `--route-signal`, `--doc-type`, and date bounds. If a text query
targets structured-only shards, `--use-shards` falls back to the monolith with an
explicit `search_shard_fanout_raw_text_uses_monolith_fallback` diagnostic so
raw-text discovery remains available without broad FTS fan-out across every
shard. Agent-event shard routes filter stream-copy duplicates before limiting,
so canonical response items are not crowded out by progress stream noise.

Full rebuilds do not run inline SQLite `PRAGMA optimize` inside the session
loop; rebuild quality comes from the normalized route tables and explicit index
build phase. Reports include phase timings for bulk session indexing, SQLite
index build, entity-registry refresh, and search-catalog refresh so long paths
are diagnosable.

Build or inspect the generated entity registry for skills, MCPs, hooks, tools,
APIs, plugins, agents, scripts, validators, tests, evals, Git, playbooks,
techniques, mechanics, graph and memory surfaces, goals, agent event classes,
decision/open-thread signals, failure/error signals, hook-health receipts, and
route signals:

```bash
python3 scripts/aoa_session_memory.py entity-registry \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --lookup aoa-session-memory-mcp \
  --kind mcp
```

Use `--lookup` for the agent hot path: it reads the generated snapshot and is
the right first route for “does this entity exist / where is its source?”. Use
`usage-chain` when the question is “how was it used and what happened after?”.
Use `entity-dossier` when graph/cooccurrence/timeline context or a heavier
human card is needed. Use `entity-usage-audit` when the chain or dossier is
unavailable or the task needs the underlying usage/consequence event list.

`maps/entity-registry.json` is generated navigation. It records active,
observed, stale, removed, and unknown entity states so agents can route quickly
without treating the registry as source truth. Active source discovery includes
skills, MCP service configuration/directories, and MCP server `@*.tool()`
functions, so a newly added MCP tool can be registered before it appears in
archived session usage. `index-maintenance` refreshes the registry when source
skill/MCP surfaces are newer, and MCP exposes it read-only.
When the registry must stay synchronized with SQLite search, use the direct
sync route:

```bash
python3 scripts/aoa_session_memory.py entity-registry-search-sync \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --observed-source auto \
  --write-report
```

`index-maintenance` may call the same narrow path, but ordinary
`search-index --no-rebuild` should not be used merely to refresh registry
docs because it also indexes selected session documents. A bare
`entity-registry --write` is only a generated snapshot refresh.
The route treats `--budget-seconds` as a soft observed budget because the
generated snapshot and SQLite registry docs must stay synchronized; it does not
interrupt the SQLite transaction mid-sync.
The default `--observed-source auto` uses the current operational route-rollup
for observed archived entities when it is available, while retaining previous
observed anchors up to the prior per-kind registry cardinality. Use
`--observed-source route-terms` only as an explicit heavy/deep refresh when the
full route-posting aggregation is needed.
The SQLite sync is delta-based: unchanged registry docs are left in place, new
docs are inserted, changed docs are replaced by rowid, and missing docs are
removed. Reports expose `inserted_entity_registry_document_count`,
`updated_entity_registry_document_count`,
`unchanged_entity_registry_document_count`, and
`removed_entity_registry_document_count` so refresh latency does not hide a
full registry rewrite. After a successful sync, SQLite `meta` records a stable
registry snapshot fingerprint; if the registry sources are current and the
fingerprint still matches, registry-only refresh returns a fast no-op with
`skipped=true`. Reports also expose `observed_route_source`,
`document_count_source`, and `phase_timings` so slow refreshes point to the
actual expensive phase.

Ask how an entity was actually used, with consequences and evidence refs:

```bash
python3 scripts/aoa_session_memory.py usage-chain aoa-session-memory-mcp \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --kind mcp \
  --limit 5 \
  --per-route-limit 5 \
  --consequence-window 4
```

The usage audit starts from typed route signals and direct usage classes. It
keeps the MCP-sized harvest lightweight by skipping per-hit raw semantic
previews and compressed full-body hydration, and it skips broad text fallback
when route hits already contain direct usage evidence. Use the returned
raw/session refs or
`entity-usage-neighborhood` when exact before/after evidence is needed.

For literal text, path, command, error text, or session-id inputs, use
`literal-query-plan` before `search`. The packet exposes the detected
`classifications`, primary route, `literal_route_strategy`, `cost_profile`,
`fallback_plan`, and `next_expansion_command`. `literal_route_strategy` is the
compact consumer contract: it names the literal class, cheapest first route,
ordered route sequence, raw/monolith fallback position, scoped full-text need
for repeated literal loads, and whether exact recall remains preserved by
fallback. Its `scoped_full_text_strategy` block keeps repeated literal loads
operator-bounded: `materialize_scoped_full_text_first` names the shard
materialization command and the scoped query to repeat afterward, while
`choose_date_or_session_scope_before_full_text` tells the agent to narrow the
query before paying for FTS. Exact session ids route to `rehydrate` and
session-scoped search before global literal fallback; this keeps exact recall
available without making monolith FTS the first move.

Query it without losing evidence routing:

```bash
python3 scripts/aoa_session_memory.py search \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --query "hook timed out" \
  --explain
```

Resolve an operational anchor into the likely map/search routes before opening
heavy session material:

```bash
python3 scripts/aoa_session_memory.py trace-route aoa-memo-writeback \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write-report
```

`trace-route` accepts skill/entity names, MCP service names, hooks, tools,
Git/GitHub anchors, and path-like anchors. It expands aliases into
route-signal candidates, queries the portable search index, and writes a
bounded report with matched routes plus raw/segment/session refs.

Filter by generated session-act routes when the activity shape matters:

```bash
python3 scripts/aoa_session_memory.py search \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --session-act memory_read \
  --explain
```

Search results are route hints. They include session, segment, raw, raw-block,
and freshness fields so the next agent can open the stronger evidence instead
of treating a retrieval hit as reviewed truth.

Structured filters with no text query, such as `--session-act`,
`--agent-event`, `--task-episode-id`, or route-signal filters, use a lightweight
route profile. Their payload exposes `cost_profile` and avoids raw semantic
preview, compressed full-body hydration, and full-text search until a proof
window or explicit text query asks for that heavier layer.

`literal-query-plan` uses that same lightweight route when a noisy literal
phrase still resolves to a concrete route signal, such as
`hook_health:raw_unavailable`. The raw-text monolith remains an explicit recall
fallback, not the first route for an already recognized operational signal.
When a longer human phrase embeds a registered operational entity, such as
`как агент использовал aoa-decision`, the planner routes first through the
registry entity anchor (`aoa_decision`, `skill`) and keeps the original phrase
as the exact raw-text fallback.
If the same phrase also contains broad inventory words such as `найди` and a
class term such as `MCP`, the concrete embedded entity still wins; the broad
class is kept only as a suppressed diagnostic on that plan.
Broad class questions such as `какие skills есть в системе` or
`найди все MCP которые агент использовал` are classified separately from
concrete anchors. The planner starts with typed registry/inventory routes, adds
an entity-usage scenario sample when the question asks about use, errors, or
consequences, and leaves full-text recall as the last safety net.
Command literals are classified separately from plain paths: the planner uses
the command anchor for structured route candidates and keeps the full command
text as the exact raw-text fallback.

Audit the full operational route surface after classifier, atlas, or search
changes:

```bash
python3 scripts/aoa_session_memory.py route-readiness all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write-report
```

`route-readiness` checks the declared 22-layer skeleton: scope contract,
authority surface, entity/path graph, verification, decision/open-thread,
failure taxonomy, hook health, memory provenance, external snapshots,
phase/topic, delivery, findability, evidence provenance, owner route,
freshness, runtime environment, mutation surface, correlation, confidence,
access boundary, resource profile, and operator preference. It reports gaps
without turning generated route signals into reviewed truth.

For frequent status probes and MCP health checks, use a fast coverage gate with
`--sample-limit 0`. Evidence-bearing samples are intentionally reserved for
explicit audit or calibration routes so interactive status remains cheap as the
archive grows.

For classifier calibration, generate bounded review samples:

```bash
python3 scripts/aoa_session_memory.py route-sample-audit all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --sample-limit 1 \
  --write-report
```

`route-sample-audit` writes unreviewed packets with route layer/key, signal
source/confidence, raw/segment/index refs, raw previews, and reviewer verdict
placeholders. It is the bridge from coverage proof to manual sampling; it does
not promote classifier output into reviewed truth.

Record append-only verdicts against a sample packet:

```bash
python3 scripts/aoa_session_memory.py route-sample-review \
  /path/to/workspace/.aoa/diagnostics/<stamp>__route-sample-audit.json \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --verdict 'scope_contract:merge_requested:002356=accept:accept:raw supports the contract' \
  --write-report
```

Verdicts are keyed by `layer:key:event_id`. Non-accept actions such as
`reject`, `weaken`, `split`, and `add_rule` are collected as classifier
feedback for a later narrow rule change.

Check retrieval provider capability without moving archive authority out of
`.aoa`:

```bash
python3 scripts/aoa_session_memory.py search-provider-status \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --include-host
```

`portable_sqlite` is the default provider. Optional host providers such as
`abyss_machine_nervous` are status-gated overlays; their evidence is context,
not reviewed `.aoa` truth.

Use local embedding/reranker models as accelerators over the same evidence
route:

```bash
python3 scripts/aoa_session_memory.py search \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --query "hook timeout route" \
  --include-semantic-context \
  --rerank-local \
  --allow-host-warnings \
  --host-timeout 120 \
  --explain
```

`--include-semantic-context` adds a compact host semantic-search overlay.
`--rerank-local` can reorder the returned `.aoa` hits through the local
reranker, but the result provider remains `portable_sqlite` and every usable
claim must still route through raw/segment refs.

Literal raw-text FTS reads are bounded by default. The `search`,
`agent-responses`, `agent-closeouts`, `agent-progress-updates`,
`agent-reasoning-windows`, and `answer-neighborhood` commands accept
`--query-timeout-ms`; `0` disables the guard only for an explicit offline scan.
Bounded FTS reads use exact token matching with date order instead of expensive
`bm25` rank sorting. If a query still exceeds the budget, the command returns a
`sqlite_query_timeout` packet with a `next_expansion_command` instead of
blocking the agent route.

Build a compact evidence packet for a continuation or investigation recipe:

```bash
python3 scripts/aoa_session_memory.py retrieve continue-techniques-session \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --query "aoa-techniques continuation" \
  --write-report
```

Retrieval packets combine search hits, session identity, continuation signals,
phase-discovery candidates, and next route commands. They are route packets,
not summaries detached from raw refs.

Export a clean portable bundle without session archives:

```bash
python3 scripts/aoa_session_memory.py export-bundle \
  --target-dir /tmp/aoa-session-memory-bundle \
  --source-aoa-root . \
  --force
```

Install into another workspace:

```bash
python3 scripts/aoa_session_memory.py install \
  --workspace-root /path/to/workspace \
  --source-aoa-root . \
  --force
```

Detailed install rules live in `INSTALL.md`.

## Skill Shape

Portable bundle skills live under `skills/`.

The top-level router is `aoa-session-memory-global-route`. Install it into
`~/.codex/skills` with `install-user-skill` when the current user should have
`.aoa` session-memory guidance in every Codex session. The consumer evidence
route `aoa-session-memory-evidence-route` is also approved for explicit
user-level install when agents outside `.aoa` need prior-session entity usage,
consequences, graph topology, and raw/segment refs. The remaining skills stay
inside the bundle as the narrow routes for archive init, raw archiving,
historical import, diagnostics, rehydration, first-pass distillation, stress
checks, batch distillation, reindexing, portable search, audit, doctor, hook
trust, and compact probe work.

## Core Rule

```text
Raw JSONL is the evidence source.
Segment Markdown is the readable archive.
Segment index is the event map.
Session index is the atlas.
Distillation is a later reviewed act.
```
