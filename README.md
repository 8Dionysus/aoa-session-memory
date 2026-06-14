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

Normal growth should use incremental maintenance instead of a full rebuild:

```bash
python3 scripts/aoa_session_memory.py graph-maintenance all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --apply \
  --batch-limit 3 \
  --budget-seconds 300 \
  --refresh-chunk-size 64 \
  --write-report
```

Each session or segment contributes its own graph slice. When a source changes,
`graph-maintenance` deletes that source's old contribution and inserts the new
one in one SQLite transaction. Maintenance groups dirty/missing sources by
session and refreshes touched aggregate nodes/edges in batches, so a large
session is not reparsed once per source. Aggregate node/edge refresh is streamed
from SQLite and chunked by `--refresh-chunk-size`; reports include
`maintenance_detail` stats for requested ids, chunks, rows, and missing
aggregates. Foreground hooks only enqueue/background graph work; they do not run
heavy graph maintenance inline. Automated graph maintenance uses small source
batches and profile-level refresh chunks because one dirty historical session
can touch thousands of edges. Maintenance plans exact old-plus-new aggregate
node/edge refresh cost before mutating, sorts actionable sources cheap-first,
and then selects only sources that fit the current batch and refresh budgets.
`--budget-seconds` bounds live wall-clock work; if the deadline expires before
or during a mutation pass, the command records `deferred_time_budget` sources
and rolls back the in-flight mutation instead of leaving a half-refreshed graph.
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

For live-churn checks, keep the strict default as full truth and use
`graph-freshness-check --stable --quiet-seconds 120` only when the operator
wants a quiescent-subset gate. Stable mode reports recent writes under
`deferred_live_sessions`; those sessions are visible but not checked.

Query examples:

```bash
python3 scripts/aoa_session_memory.py graph-neighborhood aoa-session-memory-mcp --kind mcp --depth 2
python3 scripts/aoa_session_memory.py graphrag-packet --query aoa-session-memory-mcp --anchor aoa-session-memory-mcp
python3 scripts/aoa_session_memory.py graph-eval
python3 scripts/aoa_session_memory.py graph-quality-audit --write-report
python3 scripts/aoa_session_memory.py graph-quality-review diagnostics/<stamp>__graph-quality-audit.json \
  --verdict mcp_access_plane=accept:accept:"good MCP evidence route" \
  --write-report
python3 scripts/aoa_session_memory.py graph-maintenance all --apply --write-report
python3 scripts/aoa_session_memory.py graph-quality-corpus check --write-report
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
archive-wide gate.
`entity-dossier` builds a human card for one stable anchor with strong refs,
weak refs, related skills/MCPs/tools/hooks/paths/goals/failures/decisions, open
questions, and a read-first route.

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

For recurring unattended upkeep, use `auto-maintenance`. It wraps the same
maintenance controller with freshness gates, a lock, and bounded graph batches:

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
next automatic queue, not a failed service. For a live route-cache repair
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
current.
Host timers should run maintenance through `abyss-machine resource launch
--kind indexing --unattended --success-on-block` so heavier work uses the
machine resource layer instead of hooks or MCP reads.
`aoa_session_memory` MCP remains read-only and plan-only.

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
weight, session raw/block/segment buckets, SQLite page and freelist state, and
optional per-table sizes.

The current safe storage route is:

- Graph store: aggregate node/edge payloads keep compact refs; packet reads
  hydrate evidence from contribution rows.
- Search store: new search rebuilds keep full text in FTS and compressed
  `document_bodies`, while `documents.body` keeps only a bounded hot preview.
- Raw blocks: do not delete duplicated raw blocks yet. They need an
  offset/compressed-block reader route first so segment and raw refs remain
  stable before any cleanup.

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
  --max-raw-mb 16 \
  --write-report
```

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
`.aoa` session-memory guidance in every Codex session. The remaining skills stay
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
