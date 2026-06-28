# AoA Session Memory Pipeline

## Role

`PIPELINE.md` is the operational route for the `.aoa` session-memory kernel.

Read it after `DESIGN.md` and `DESIGN.AGENTS.md` when changing hooks, archive
generation, indexes, diagnostics, rehydration, or tests.

## Current Codex Grounding

As of the local Codex CLI `0.133.0` installation:

- Codex compacts conversation context automatically when its configured compact
  threshold is exceeded.
- OpenAI's public agent-loop writeup describes Codex using the
  `/responses/compact` endpoint and replacing the active input with a smaller
  continuation history that includes a compaction item.
- The local Codex binary exposes schema-validated hook outputs for
  `SessionStart`, `UserPromptSubmit`, `PreCompact`, `PostCompact`, and `Stop`.
- Hook stdout is strict JSON: unknown top-level fields are invalid.
- `PreCompact` and `PostCompact` output schemas currently accept only protocol
  fields such as `continue`, `stopReason`, `suppressOutput`, and
  `systemMessage`.
- The local project config currently sets `model_context_window = 400000` and
  `model_auto_compact_token_limit = 320000`, so the expected auto-compact ratio
  is `0.8`.

The consequence for `.aoa`: compaction hooks may be used, but they must be
fail-open and minimal. The archive must never depend on a hook blocking Codex.

References:

- OpenAI, "Unrolling the Codex agent loop":
  `https://openai.com/index/unrolling-the-codex-agent-loop/`
- OpenAI Codex CLI docs:
  `https://developers.openai.com/codex/cli`
- Local Codex binary schema inspection:
  `codex-cli 0.133.0`
- GitHub `openai/codex` issue #16098 documents why reliable compaction
  lifecycle hooks matter for long-running workflows:
  `https://github.com/openai/codex/issues/16098`
- GitHub `openai/codex` issue #14456 documents context-window and
  auto-compact config drift risk:
  `https://github.com/openai/codex/issues/14456`

## End-to-End Flow

```text
Codex hook event
  -> aoa_session_memory.py hook
  -> hooks/events.jsonl receipt
  -> raw transcript mirror when transcript_path is readable
  -> light hook closeout for prompt, compaction, and large stop lifecycle hooks
  -> background hook-worker for queued lifecycle sync
  -> sweep-codex-sessions for missed no-hook or stale transcript recovery
  -> JSONL event classification
  -> route-signal classification for operational layers
  -> token-accounting observation extraction
  -> raw/blocks/*.raw.jsonl sealed by compaction interval
  -> raw/blocks.index.json and raw/compaction-events.jsonl
  -> compaction-interval segment Markdown
  -> sibling segment index JSON
  -> SESSION.md and session.index.json
  -> session.manifest.json
  -> session-registry.json
  -> token-accounting report/backfill diagnostics
  -> index-maintenance token-ledger backfill before search/atlas refresh
  -> optional search-index runtime cache with bounded raw lexical policy
  -> optional provider capability status for host overlays
  -> trace-route anchor resolver for skill/MCP/hook/tool/GitHub investigations
  -> entity usage audit and neighborhood windows for real skills, MCPs,
     hooks, tools, and recurring agent-work entities
  -> retrieval packet recipes
  -> agent atlas route entries from generated route signals
  -> incremental graph store and generated sidecar snapshots
  -> graph-quality audit/review/corpus and entity dossier trust gates
  -> graph freshness gates over maps/search/graph/refs
  -> index-maintenance per-session fingerprint drift detector / repair pass
  -> rehydrate packet
  -> later reviewed distillation
  -> pattern / skill / automation candidate
```

## Hook Lifecycle

### SessionStart

Purpose: start or refresh the archive when Codex has a transcript path.

Behavior:

- records the hook event
- mirrors raw when available
- regenerates segments and indexes
- returns schema-valid Codex context for the active archive

### UserPromptSubmit

Purpose: low-cost trace of user prompts.

Behavior:

- records the hook event
- does not full-sync by default
- full-syncs only when `AOA_SESSION_MEMORY_FULL_PROMPT_SYNC=1`

Reason: prompt hooks should not become a heavy tax on every turn.

### PreCompact

Purpose: capture the latest readable raw state before compaction.

Behavior:

- records the hook event
- mirrors raw when available
- marks segment and index regeneration as deferred by default
- queues background lifecycle sync so the worker can seal the closing interval
- full-syncs only when `AOA_SESSION_MEMORY_FULL_COMPACT_SYNC=1`
- returns only `{"continue": true}` by default

Reason: pre-compact hooks run on the active lifecycle path and must preserve
raw state without risking a timeout on large transcripts. Heavy interval
sealing belongs to `hook-worker`, not the foreground hook.

## Token Accounting Route

Token accounting is generated evidence over archived events. The archive writes
count-only summaries into segment indexes, `session.index.json`,
`session.manifest.json`, raw-block ledgers, and `session-registry.json`.

Count bases stay separate:

- `provider_reported`: usage metadata emitted by the provider or local serving
  API.
- `exact_tokenizer`: local tokenizer count with a known matching tokenizer and
  model route.
- `estimated`: heuristic count for planning only.

The route must not persist prompt text, raw text, tokenizer stdout, or token
ids. Backfill may refresh generated ledgers from preserved raw inside `.aoa`;
external host consumers must consume generated summaries only. `index-maintenance`
plans token-ledger backfill before search, atlas, readiness, and graph
maintenance. It uses per-session projection fingerprints for search/atlas
freshness so changed sessions can be updated without forcing a full rebuild.
Partial atlas updates merge existing compact axis indexes instead of reparsing
every generated entry artifact. Scoped graph maintenance ignores graph sources
outside the selected session set and only prunes orphaned rows in the full
archive scope or inside explicitly selected sessions.
Use `--budget-seconds` for bounded maintenance and `--token-max-raw-mb` for
large token-ledger repairs without raising the separate raw-text extraction
limit used by search indexing. Bounded `index-maintenance` treats the budget as
both an apply budget and a planning budget: if token backfill planning or
search/atlas/entity/graph probes cannot safely start inside the remaining
window, the report sets `budget_exhausted=true`, marks the unstarted surfaces as
`deferred_budget_exhausted`, and leaves raw/search/atlas authority unchanged for
the next maintenance tick. The host bridge command is:

```bash
abyss-machine ai token-accounting aoa-summary --json
```

That command is a read-only planning projection owned by `abyss-machine`; it
does not own `.aoa` raw, manifests, indexes, or registry truth.

## Entity Usage Retrieval Route

Use `usage-chain` when the agent asks how a skill, MCP, hook, tool, API,
script, validator, test, graph, memory surface, or other recurring entity was
used and what happened immediately after it. This is the hot consumer packet:
it is built from structured usage evidence, keeps raw/segment/session refs, and
skips GraphRAG, graph neighborhood, and raw-preview neighborhoods by default.

Use `entity-dossier` when the agent needs the heavier human card for how a
recurring entity appears in archived work, what happened nearby, which
graph/ref context applies, and which next route should be opened.

Use `entity-usage-audit` when the usage-chain or dossier is unavailable, too
coarse, or the agent specifically needs the underlying usage/consequence event
list.

`entity-usage-audit` is a structured-fast route first. It queries typed route
signals and direct usage classes with lightweight search hits, skips raw
semantic previews and compressed full-body hydration on the search harvest, and
only opens the broad text fallback when the typed route hits do not contain
direct usage evidence. The payload exposes `text_search_skipped`,
`route_hit_count_before_text_fallback`, and
`route_usage_hit_count_before_text_fallback` so an agent can tell whether it got
the fast indexed path or had to widen.
For direct usage classes, the usage-role fast path uses the bounded
`route_fetch_limit` as its internal harvest budget even when the requested
presentation `--limit` is small. This keeps compact MCP packets from selecting
from an artificially tiny candidate pool while preserving a small returned
event list.

Use `entity-usage-neighborhood` when the agent needs the local before/after
event window around direct usage. Its `--limit` means "how many usage windows
to open", not "how few search hits to inspect". The command may use a wider
bounded internal harvest so direct usage is not hidden behind entrypoint,
result, or text-only matches. The payload exposes `requested_usage_limit`,
`audit_limit`, `audit_per_route_limit`, and candidate usage counts so the
agent can judge the cost and quality of the route.

Usage payloads keep route signals bounded: they include a route-signal sample,
`route_signal_count`, and `route_signals_truncated`. Follow the returned
`segment_index` and raw refs for the full route-signal set or exact evidence.
This keeps MCP-sized packets fast without making the packet the authority.

Use `entity-dossier` as the one-packet consumer route for operational entity
questions that need source identity, usage, consequence, graph neighborhood,
refs, freshness, noise flags, and next expansion commands together. Use
`usage-chain` first when the question only needs the usage-to-consequence
chain. Both routes are evidence packets, not reviewed truth.

Use `live-scenario-audit` with the default `entity_dossier` profile as the
consumer-loop smoke for that one-packet route. Use
`entity-usage-scenario-audit` as the narrower live randomized pipeline test for
operational entity usage retrieval. Its quality block separates
`candidate_selection_elapsed_ms`, `sample_total_elapsed_ms`,
`audit_total_elapsed_ms`, and `raw_preview_total_elapsed_ms` so slow runs can
be attributed to candidate-pool selection, route audit, or raw-preview opening
instead of becoming a vague "MCP is slow" complaint.
Actionable quality flags are part of the scenario verdict, not decorative
metadata. A sample that has direct usage or result evidence but no consequence
chain is a warning (`direct_usage_without_consequence`), while evidence-only
flags that do not change the agent's next action may remain informational.
Use `live-scenario-corpus check` when the loop needs regression proof rather
than a one-off diagnostic. The source-owned cases live in
`config/live-scenario-regression-corpus.json`; they check route behavior and
evidence refs, while raw/segment/receipt refs remain the stronger authority.
Compact route output keeps a bounded `provider` summary with portable SQLite
status, schema, route-index presence, and freshness status. The full provider
diagnostic remains behind `search-provider-status --provider portable_sqlite`
or the command `--full` route.

Hooks are a special case. A generic usage audit for a hook often returns
receipt/result evidence rather than direct "usage" events. For hook health,
start with hook receipt routes and use entity usage audit as surrounding
session evidence.

## Session Evidence Consumer Route

`skills/aoa-session-memory-evidence-route` is the small route card for agents
and sibling skills that need prior-session evidence without giving
session-memory another owner's authority.

Use it when the request shape is:

- "how was this skill/MCP/hook/tool/API/script/test/validator/eval used?"
- "what happened after this usage?"
- "which raw or segment refs prove it?"
- "where did this goal/answer/closeout/error/receipt appear?"
- "which graph relation or bridge connects these operational entities?"

The route order is:

1. typed usage-to-consequence packet: `usage-chain`;
2. typed entity dossier: `entity-dossier` when graph/cooccurrence/timeline
   context is needed;
3. typed usage packet: `entity-usage-audit` when the chain or dossier is unavailable,
   truncated, stale, or too coarse;
4. exact before/after windows: `entity-usage-neighborhood`;
5. hook errors or health: hook receipts before usage audit;
6. goal lifecycle: `goal-lifecycles` before raw search;
7. agent answer/task intervals: agent-event or task-episode routes;
8. literal phrase/path/command/error/session id: `literal-query-plan`;
9. topology: `graph-bridge` for "how are X and Y connected?", then compact
   graph routes with explicit node/edge/evidence budgets. The bridge packet
   keeps side neighborhoods shallow by default so dense anchors such as common
   tools do not turn the first route into a heavy graph scan.

Session-memory packets remain generated navigation and evidence routes. They
must report freshness, truncation, refs, and next expansion, then hand decision
truth, proof truth, skill meaning, or durable memory promotion back to the
owning repository, eval layer, skill bundle, or reviewed memory surface.

## Agent Event And Task Episode Route

Agent answers, progress updates, reasoning boundaries, closeouts, blockers,
handoffs, and verification reports are generated navigation classes under
`facets.agent_event`. They are not reviewed truth and they do not expose hidden
reasoning content. A reasoning item is indexed as a boundary/context event with
refs and neighbors; interpretation belongs to a later reviewed layer.

Segment indexes expose `by_agent_event`. Session indexes expose
`agent_event_counts`, `task_episode_counts`, and `task_episodes`. A task
episode links the start user ref, reasoning boundary refs, plan refs, action
and tool refs, verification refs, error/blocker refs, and final/closeout refs
inside a bounded generated interval. Ambiguous boundaries carry confidence and
`ambiguity_flags` instead of pretending the episode is reviewed truth.
If a user prompt reaches the archive tail without any agent response, action,
tool, verification, error, blocker, or closeout refs, the episode is marked
`interrupted` with `no_agent_response_seen`; this is a transition signal, not
a reviewed claim that work happened.

Use these routes when the question is about what the agent answered or how a
task interval unfolded:

```bash
python3 scripts/aoa_session_memory.py agent-responses --session latest --limit 20
python3 scripts/aoa_session_memory.py agent-closeouts --session latest --limit 20
python3 scripts/aoa_session_memory.py agent-progress-updates --session latest --limit 20
python3 scripts/aoa_session_memory.py agent-reasoning-windows --session latest --limit 10
python3 scripts/aoa_session_memory.py task-episodes latest --limit 20
python3 scripts/aoa_session_memory.py answer-neighborhood --session latest --limit 10
python3 scripts/aoa_session_memory.py agent-event-audit all \
  --order longest --min-events 1000 --limit 5 --probe-routes --write-report
```

`task-episodes` defaults to `--order recent` so an agent lands on the live tail
of a long session first. Use `--order chronological` when replaying a session
from the beginning.

Structured list routes without a text query are lightweight by default. They
avoid raw semantic preview, compressed body hydration, and full-text search,
then return bounded `search_body` previews plus raw/segment refs. Use
`answer-neighborhood`, `agent-reasoning-windows`, or the returned refs when the
task needs exact before/after evidence.
Agent-event result packets are ordered by query rank when a query is present,
then by session date and event position descending. The `quality` block reports
agent-event class counts, freshness counts, source counts, raw/segment ref
coverage, and the latest returned event. A latest answer can honestly be
`stale` when the active transcript tail has moved; do not hide it behind older
fresh events, but open the returned raw/segment refs before promoting a claim.
When monthly shards are materialized, these agent-event routes accept
`--use-shards` and return their `search_projection`; this is the preferred
archive-wide route for MCP/agent answer, closeout, progress, and reasoning
queries that do not need broad raw-text FTS.
Goal lifecycle navigation also returns the same compact provider/freshness
summary, so an MCP caller can judge projection currency before opening
generated refs or raw transcript authority.
When a lifecycle starts after a compaction/resume boundary and the archive has
`get_goal` output but no preserved `create_goal` event, the generated lifecycle
may fill `observed_goal`, `state_observations`, and `objective_source` from the
tool output. This improves route usefulness without inventing a creation ref:
`missing_create` remains the honest boundary flag.

`agent-event-audit --order longest` is the Stage-1 classification route for
real long sessions. It records selected sessions, generated shape counts,
bounded raw event-shape samples, weak spots, route probes, and refs without
dumping transcript text into the diagnostic.

The SQLite search route stores `agent_event` and `task_episode_id` as first
class filters. MCP may expose these read-only packets, but maintenance,
reindex, repair, and promotion stay outside MCP.

Full `search-index` rebuilds keep raw lexical text bounded by default and do
not run inline SQLite `PRAGMA optimize` inside the session loop. Reports carry
phase timings for bulk session indexing, SQLite index build,
entity-registry refresh, and search-catalog refresh so a slow path has an
observable stage boundary.
Search schema 10 additionally caps route postings for aggregate documents
(`session`, `segment`, `task_episode`, `incident`) while leaving event-level
route postings uncapped. Aggregate route fields are ordered by route-signal
frequency before capping, so the retained aggregate postings are the strongest
signals rather than alphabetic noise.
Every successful `search-index` run refreshes `search/catalog.json`. The
catalog records `session_id`, label, date, freshness, schema versions,
document count, active projection, and monthly shard key. Scoped or incremental
search-index runs use selected records plus existing catalog state for
unaffected sessions; if that does not cover the indexed rows, the catalog route
falls back to a full live session-index scan. While shard DBs are not
materialized, `active_projection=monolith_fallback` must remain explicit.
Future shard fan-out should start from this catalog instead of rediscovering
session buckets through broad monolith scans.
`search-shards` materializes monthly shard DBs from the same raw/session-index
inputs and then refreshes the catalog. The default shard is a structured route
projection: it keeps route tables, bounded hot previews, freshness state, and
refs, but skips local raw-text FTS rows, compressed `document_bodies`, and raw
event semantic-text extraction. `search-shards --full-text` is the explicit
operator route for a heavier shard-level lexical diagnostic. The catalog treats
a shard as materialized only when the shard `session_index_state` matches the
live session-index fingerprint and schema state for every session in that
bucket. If the only mismatch is a recently written live transcript deferred by
the quiet-window gate, the route is `current_with_deferred_live_updates`: the
live-tail packet owns the wait/catch-up action, while stable shard fan-out stays
usable. The monolith remains a fallback projection and is tracked separately.
When the catalog already identifies a small dirty set inside an existing shard,
use `search-shards all --shard <key> --no-rebuild --dirty-only --write-report`
instead of rematerializing the full month. `--dirty-only` is intentionally
incremental-only: it refuses rebuild mode and refuses missing shard DBs because
a partial rebuild from only dirty sessions would drop current sessions from the
generated shard projection. Reports expose `pre_filter_selected_count`,
`dirty_candidate_count`, `dirty_selected_count`, and `skipped_current_count`
so operators can prove the run touched only the intended stale rows.
By default dirty selection skips `freshness.status=deferred_live`; the
live-tail catch-up route must first preserve and index the newer transcript.
Use `--include-deferred-live` only for a deliberate operator override.
`search --use-shards` performs bounded fan-out across current materialized
shards and returns shard refs; when shards are missing, stale, incompatible with
host overlays, or unable to satisfy a raw-text FTS query locally, the route
falls back to the monolith with an explicit diagnostic.
Agent-event routes share the same shard fan-out through `--use-shards`, while
preserving pre-limit stream-copy filtering so progress stream duplicates do not
hide canonical `response_item` answers or reports.

### PostCompact

Purpose: capture the closed interval after compaction succeeds.

Behavior:

- records the hook event
- mirrors raw when available
- marks segment and index regeneration as deferred by default
- queues background lifecycle sync that writes the closed compaction interval,
  raw block ledger, segment Markdown, and sibling segment index
- full-syncs only when `AOA_SESSION_MEMORY_FULL_COMPACT_SYNC=1`
- returns only `{"continue": true}` by default

Reason: post-compact hooks are preservation receipts on the active lifecycle
path. The automatic `hook-worker` is the primary archive path; manual `sync`,
import, and reindex are recovery or rebuild paths.

### Stop

Purpose: final turn-close preservation receipt.

Behavior:

- records the hook event
- mirrors raw when available
- regenerates the archive from raw only when the transcript is under
  `AOA_SESSION_MEMORY_STOP_SYNC_MAX_BYTES`
- marks segment and index regeneration as deferred when the transcript is over
  that threshold
- full-syncs only when `AOA_SESSION_MEMORY_FULL_STOP_SYNC=1`
- writes diagnostics when raw is unavailable
- returns only `{"continue": true}` by default

Reason: stop hooks often fire after the longest and noisiest part of a session.
They must not block session closeout while parsing and indexing a very large
transcript. The next deliberate layer for deferred sessions is manual `sync`,
import, or reindex.

If Codex exits without a usable `Stop` receipt, the hook layer cannot invent
that missing event. The recovery route is `sweep-codex-sessions`: it scans
`~/.codex/sessions`, compares each transcript with indexed `.aoa` manifest/raw
snapshots through `indexed_archive_freshness`, and plans only missing, stale,
deferred, hook-only, or raw-unavailable archives. The command is dry-run by
default; `--apply` performs the sync.

## Segment Rule

The durable segment roles are:

- `initial-to-compaction`
- `compaction-to-compaction`
- `compaction-to-latest`
- `initial-to-latest`

When no compaction boundary exists, use `initial-to-latest`.

When compaction boundaries exist, each boundary closes the previous interval.

The preservation layer must also write raw interval blocks:

- `raw/session.raw.jsonl` keeps the full mirrored black-box transcript.
- `raw/blocks/NNN__role.raw.jsonl` keeps each interval as a bounded raw block.
- `raw/blocks.index.json` maps segment IDs to raw block paths, status, hashes,
  source ranges, and boundary event IDs.
- `raw/compaction-events.jsonl` records the raw compaction markers observed in
  the transcript.

`PostCompact` must queue this sealing work automatically. A later manual
`reindex-sessions` may rebuild the same artifacts from `raw/session.raw.jsonl`,
but it is not the normal collection path.

## Storage Weight Rule

The archive may compact generated route stores, but it must preserve raw
evidence and stable refs.

- Graph aggregate `nodes` and `edges` may omit full evidence refs because
  `node_contribs` and `edge_contribs` remain the per-source evidence store.
  Contribution payloads should keep compact refs only: session identity,
  segment identity, event identity, raw refs, bounded segment refs, and enough
  session refs for quality gates. Full route-signal lists are represented by
  graph edges, not duplicated inside event-node payloads. Graph packets must
  hydrate bounded refs from contribution rows before an agent relies on them.
- The monolith search projection may keep full body text in FTS and compressed
  `document_bodies` while `documents.body` stores only a slim hot preview.
  `documents.tags` is also a hot routing hint, not the route authority: it may
  drop `route_signal:*` and `route_layer:*` tokens because full structured
  route coverage lives in `route_terms` / `document_routes`. Repeated raw and
  segment-index paths may be omitted from hot `documents` rows when they are
  derivable from `manifest_path`, `segment_id`, and the live session archive;
  search results must still return resolved raw/segment/session refs before an
  agent relies on them. Search DB indexes should follow the lean route/date
  profile: keep the indexes needed for session, event/date, agent-event,
  task-episode, freshness, and route-posting filters, but do not materialize
  broad duplicate session composite indexes when shards and route postings
  already own that route. Default monthly shards are structured route
  projections and intentionally omit local FTS/body hydration; raw-text recall
  falls back to the monolith unless a shard was explicitly built with
  `search-shards --full-text`.
- Raw interval blocks are preserved evidence today. Do not remove block payloads
  just because `raw/session.raw.jsonl` also exists. Any cleanup first needs an
  offset/compressed raw-block reader and validation that segment/raw refs still
  resolve.
  `raw-block-ref-audit` is the current read-only gate for this: it maps sampled
  `raw:line:N` refs through `raw/blocks.index.json` and compares block-local
  lines back to the full raw transcript before any cleanup route exists.
  `raw-block-storage-compact` is the staged storage route after that gate. Its
  dry-run reports gzip sidecar and reclaim shape, `--apply` writes compressed
  raw-block storage metadata, and plaintext block removal requires
  `--confirm-remove-plain`. The full raw transcript remains the authority.
  Apply is a `manual-bulk` maintenance-coordinator writer touching raw blocks,
  session manifests, and the session registry.
  Storage reports must distinguish remaining plaintext duplicate bytes from
  compressed sidecar bytes; compressed sidecars are the active raw-block
  storage representation once plaintext blocks are removed. Use
  `--skip-no-plain` for archive-wide batches so already compressed sessions do
  not consume the next bounded apply window.

Use `storage-audit` to measure current weight and reclaim candidates. It is a
read-only gate; actual shrinkage of graph/search stores requires controlled
rebuilds, not blind `VACUUM` or file deletion.
The normal audit also exposes SQLite store metadata such as graph/search
payload modes, so agents can distinguish compact layout state from old payload
shape without running the heavy `dbstat` lane. Add `--deep-dbstat --row-counts`
only for an offline per-table size pass. Deep graph audits must pair per-table
sizes with an aggregate payload compaction sample; `nodes` plus `edges` table
size is not a reclaim estimate unless sampled payload rows actually shrink.
When the sample delta is zero, route the next slice to graph cardinality,
sharding, or task-specific projections instead of rebuilding for aggregate
payload compaction.
Use `graph-cardinality` for graph node/edge type counts. The read route uses
the materialized `graph_type_counts` projection and should stay interactive;
`graph-cardinality --refresh` is the heavy repair/materialization route and
must be run through the machine resource lane on large live stores. Do not use
ad hoc `GROUP BY node_type/edge_type` scans as the normal agent path.
`maintenance-status` surfaces the same cached signal as
`operations.graph_pressure`, together with the conservative SQLite compaction
headroom plan. Treat this as the agent-facing hot route for graph weight:
large top edge counts mean graph cardinality or query-projection work comes
before physical SQLite compaction.
When old live graph stores still contain generated standalone `raw_ref` nodes
and `has_raw_ref` edges, use `graph-raw-ref-prune` as the bounded projection
repair. It deletes only generated graph materialization rows, keeps raw/session
evidence refs in event and contribution packets, updates graph type counts, and
does not run `VACUUM`. The apply path is a `manual-bulk` single-transaction
delete with a default disk-headroom preflight (`--min-free-gb 20`) because WAL
growth can be large before checkpoint. Dry-run reports aggregate candidates
from materialized graph type counts; contribution-row delete counts are measured
only during apply.

When the generated graph store still needs physical SQLite shrink after a
projection prune, use `graph-sqlite-compact` as the preflight/staging route.
The default is read-only and computes conservative headroom for `VACUUM INTO`.
Apply defaults to a staged compact copy that is integrity-checked. Use
`--promote-copy` only when the operator wants the verified generated copy to
replace the live `graph.sqlite3` under the maintenance lock. Promotion first
checkpoints WAL, keeps a backup by default, verifies the promoted live DB, and
deletes that backup only with `--delete-backup-after-verify`. Source-mutating
`VACUUM` still requires `--confirm-source-vacuum`.

The same staged/promote route exists for the portable SQLite search store:
`search-sqlite-compact` is a physical generated-store maintenance route, not a
raw evidence cleanup route. Search weight should still be reduced first through
bounded raw lexical policy, structured shards, and route benchmarks; physical
search compaction is mainly for post-rebuild freelist reclaim.

Use `storage-maintenance` for the current safe live shrink lane. It only runs
SQLite WAL checkpoint/truncate for the graph and search stores, reports busy
readers/writers instead of killing them, and leaves raw evidence, graph rebuilds,
search rebuilds, and raw-block cleanup outside this route.

Use `maintenance-cleanup` for stale maintenance coordinator state and orphaned
generated graph rebuild temp files. Its temp-family detector includes SQLite
companions `-wal`, `-shm`, and `-journal`, including the live failure mode where
only `.graph.sqlite3.<pid>.rebuild.tmp-journal` remains after the base rebuild
tmp file is gone. This is generated-projection cleanup only; it must not delete
raw transcript, segment, search, atlas, or reviewed memory evidence.

Real Codex raw transcripts may express a compaction boundary as:

- top-level `{"type": "compacted", ...}`
- `{"type": "event_msg", "payload": {"type": "context_compacted"}}`
- `turn_context` payloads with a non-empty compaction summary

Treat the adjacent `compacted` -> post-compact `turn_context` / `token_count`
-> `context_compacted` marker sequence as one logical compaction boundary.
Keep those raw events in the same closing segment. Do not split them into
marker-only microsegments.

Do not create semantic micro-shards at the preservation layer. Semantic
extraction belongs to distillation.

## Index Rule

Every segment Markdown must have a sibling `.index.json`.

The session must have:

- `SESSION.md`
- `session.index.json`
- `session.manifest.json`
- `session-registry.json`

The archive directory must have:

- `sessions/AGENTS.md`
- `sessions/INDEX.md`
- `sessions/index.json`
- `SESSION_NAMES.md`
- `session-name-index.json`

The secondary route caches must be maintained as caches, not as authority.
Use `index-maintenance` as the automatic controller:

```bash
python3 scripts/aoa_session_memory.py index-maintenance all \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --apply \
  --write-report
```

It detects stale or missing route indexes, per-session source-fingerprint
drift for portable SQLite search, per-session source-fingerprint drift for the
atlas, and deferred raw mirrors. With `--apply`, it reindexes only stale route
indexes, updates only dirty search/atlas sessions when schemas are compatible,
falls back to full rebuild only for missing/corrupt/schema-mismatched stores,
and records a route-readiness report over the same selected target/date/limit
window. After token, route-index, search, or atlas mutation, the controller
rechecks the selected sources before planning graph maintenance; this prevents a
green search/atlas pass from leaving graph sources dirty. Its graph action
exposes `--graph-batch-limit` for source count and
`--graph-refresh-chunk-size` for aggregate node/edge recomputation chunks. Use
`--sample-audit` when a route schema or classifier change requires a new manual
calibration packet. Sample-audit commands inherit the same selected window as
the controller. Sample verdicts still require explicit review.

For recurring unattended work, use the session-memory auto route above the same
controller:

```bash
python3 scripts/aoa_session_memory.py auto-maintenance hot \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --apply \
  --write-report
```

`auto-maintenance` is the timer entrypoint. It takes a non-blocking
`diagnostics/auto-maintenance.lock`, runs a freshness gate first, and only
delegates to `index-maintenance` when that gate shows actionable work. A clean
hot/catchup gate (`needs_* = false`, search actionable/deferred counts `0`,
graph actionable queue/ledger/deferred counts `0`) must return
`status=nothing_to_do`, `mutates=false`, and a `skipped_clean` action without
touching graph/search read-model stores. Dirty runs still run freshness gates
before and after the maintenance pass and delegate actual
route/search/atlas/graph work to `index-maintenance`. Its profiles are:

- `hot`: two-day recent window, probe resource route, route/search/atlas repair
  for interactive agent routes, and a small bounded graph repair tick with
  explicit deferred remainder. If the route-cache repair spends the hot budget
  before graph work starts, it queues a bounded graph-maintenance job with the
  same batch, chunk, and aggregate refresh guards plus a separate profile graph
  budget.
- `backlog`: wider recent archive window, medium resource route, search/atlas
  repair, larger graph backlog batch, and medium aggregate refresh chunks.
- `catchup`: full archive search/atlas repair through bounded dirty-session
  batches, medium resource route, no inline graph repair, and explicit
  deferred graph follow-up. Use this after classifier or projection changes
  when `search-provider-status` reports many dirty historical sessions and a
  full repair would exceed the interactive or unattended budget. While backlog
  remains, a successful catch-up batch reports
  `applied_with_remaining_backlog` and `expected_catchup_remaining=true`;
  failed actions or hard diagnostics still keep the run red.
- `deep`: full archive, heavy resource route, full repair and
  calibration-capable batch with larger aggregate refresh chunks.

For deliberate post-classifier, post-schema, or generated-projection catch-up,
use the named projection route:

```bash
python3 scripts/aoa_session_memory.py projection-catchup all \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --apply \
  --write-report
```

This route is an agent/operator wrapper over the same maintenance coordinator.
It makes the purpose explicit, keeps raw/session evidence as authority, and
returns the next route in the same vocabulary. The default `catchup` profile is
bounded and may report `rerun_projection_catchup` while backlog remains. If a
schema mismatch requires a full search rebuild, it returns
`run_deep_projection_catchup` instead of starting an unsafe heavy rewrite from a
bounded profile. Use `--profile deep` when the intended operation is the full
heavy repair, including graph maintenance.

The payload also exposes `projection_completeness` as the agent-facing contract
for post-classifier/schema work. It normalizes the nested freshness/action
state into per-surface rows for route indexes, token ledgers, portable search,
search catalog/shards, atlas, entity registry, graph, live-tail deferrals, and
route-readiness. Agents should inspect that block before reading the heavier
`auto_maintenance` subtree; raw transcript/session evidence remains the
authority and this block is only a generated projection status.

Full search rewrites are outside the bounded timer profiles. If the freshness
gate reports a schema mismatch, missing/empty store, corrupt SQLite store, or
empty route-posting/term tables, `hot`, `backlog`, and `catchup` must return
`deferred_full_search_rebuild_to_deep` with a deep/heavy resource-launch
command. Only `deep` or an explicit operator-run `search-index all --rebuild`
may perform the atomic full SQLite replacement.

The lock is the writer guard; `diagnostics/maintenance-coordinator.json` is the
operator/agent explanation layer. Every writer that uses the shared maintenance
lock should publish owner job, mode, touched projection surfaces, lock wait,
start time, deadline, and last result. `hot` treats an active
`catchup`/`backlog`/`deep`/`manual-bulk` lease as a defer signal and must not
start a parallel heavy rewrite. `maintenance-status --full` is the read-only
entrypoint for checking the current owner, last completed job, DB/WAL sizes,
operations warnings, last successful auto-maintenance profiles, recent problem
jobs, bounded slow-session samples from the latest `search-index` /
`search-shards` reports, and `why_maintenance_long` search-index/storage
evidence before starting a manual catch-up.
Graph source hashing has its own generated cache under `graph/source-hash-cache.json`.
`graph-maintenance --hash-mode cached` may reuse entries whose path size and
`mtime_ns` still match, while `--hash-mode exact` forces file reads. Updating
the cache is automatic for mutating graph-maintenance source scans and can also
be requested explicitly with `--write-hash-cache`; that path is a maintenance
writer and must use the shared lock, but ordinary read-only deep checks may
consume an existing cache without mutating archive state.
Manual-bulk commands use the same shared lock but must not block indefinitely
behind an unattended timer. When the lock is still held after the bounded wait,
they return a `session_memory_maintenance_lock_conflict` packet with
`mutates=false`, the blocking owner, and lock-wait diagnostics. The coordinator
also persists that refusal under `maintenance-coordinator.json:last_conflict`,
including the requested owner/mode, blocking owner, touched surfaces, wait time,
timeout, and skipped/deferred reason, so a later `maintenance-status` call can
explain why the manual job did not mutate. Treat that as a clear retry/defer
signal, not as permission to start a second writer or kill the owner.

`maintenance-status` also exposes a `live_tail` packet for deferred live
sources. It separates actionable dirty work from quiet-window deferral, reports
`waiting_for_quiet_window` versus `ready_for_catchup`, includes
`quiet_remaining_seconds` / `next_ready_at`, and exposes the narrowest typed
catch-up route. Search-deferred live sessions use targeted
`index-maintenance <session> --skip-graph-repair --apply --write-report` first;
graph-deferred live sources use graph queue maintenance. This is the agent
surface for deciding whether to use stable graph/search now, wait for the live
quiet window, or run catch-up after the window has elapsed without dragging the
full hot profile onto the interactive path.
For graph state, the quiet-window boundary is session-wide: if a graph source
belongs to a Codex transcript that is still being written, older segment
indexes from that same transcript are still treated as deferred live sources.
Ledger/store count mismatches and latest maintenance remainders caused only by
those deferred live sources are reported separately and must not become
actionable graph repair.

Host timers should launch this command through
`auto-maintenance-resource <profile> --apply --write-report`. That wrapper uses
`abyss-machine resource launch --kind indexing --unattended --success-on-block`
under the hood, but records a session-memory diagnostic when the host resource
gate blocks or denies the child before `auto-maintenance` starts. This keeps
hooks and MCP read paths light while allowing the machine resource layer to use
available CPU, memory, IO, and thermal headroom without hiding resource-pressure
deferrals. `aoa_session_memory` MCP remains read-only and plan-only; it may
report freshness and the maintenance route, but it must not run maintenance.
For `catchup all`, the resource wrapper first checks the same `live_tail`
packet as `maintenance-status`: when a deferred search session is already past
the quiet window, the child command is the targeted
`index-maintenance <session> --skip-graph-repair --skip-token-accounting`
route, not broad `auto-maintenance catchup all`. This keeps timer catch-up from
turning a single live-tail repair into bulk archive selection or token-ledger
backfill.
For backlog and deep resource-blocked runs, graph drip is the safe fallback
route: both profiles enable it by default because unattended medium/heavy
indexing can be capped by host resource policy. If the requested
auto-maintenance launch is blocked by host pressure, the wrapper may run a
capped probe-class `graph-maintenance` batch, record `fallback_graph_drip`, and
still keep the outer report `ok=false` so agents do not mistake partial graph
progress for a completed backlog/deep profile. The default fallback is a small
progress drip, currently `25` graph sources with a `300s` budget and a `25`
candidate-pool window; profile graph-drip settings control the fallback batch,
budget, candidate-pool window, and node/edge refresh caps unless explicit CLI
overrides are passed. Installed user timer
units must either inherit those profile defaults or carry matching explicit
overrides; `maintenance-status` audits their `ExecStart` lines and reports
unit drift before agents trust the automatic graph-drip route. If MCP cannot
read the user systemd bus, the same check falls back to installed unit files so
read-only agent routes still see timer-contract drift. The fallback only
mutates when the outer resource route was called with `--apply`; use
`--no-graph-drip-on-block` only when an explicit diagnostic run must preserve
the raw resource-blocked state.

Use `auto-maintenance catchup --apply` or
`index-maintenance --repair-limit <n> --skip-graph-repair --apply` when a live
archive needs historical search/atlas catch-up but graph repair must stay
deferred. The report must show candidate counts, selected repair counts,
remaining counts, and `*_repair_limited=true` while backlog remains.
If catchup has no backlog, the report must stay a clean no-op instead of
reading or writing the full portable SQLite search store.

`maintenance-status` also exposes search-shard freshness as an agent action.
When `operations.search_shards.status` is not current and the stale rows are
not only deferred live-tail rows, `next_actions` includes
`refresh_search_shard_structured` with the selected shard, stale/missing counts,
raw-text fallback posture, and an exact bounded command. If the shard DB already
exists, the command uses `search-shards --no-rebuild --dirty-only`; otherwise it
uses a scoped structured rebuild only when the shard lane is already partially
materialized. It does not add `--full-text`, because full lexical shard
materialization is a separate weight/quality tradeoff.

Use `index-maintenance --skip-graph-repair` when a live investigation needs
fresh route/search/atlas caches without paying the graph-store repair cost.
The report must expose `defer_graph_repair` when graph sources are dirty, so a
future hot/backlog/deep pass can repair graph state without pretending the
route cache is incomplete.

Incremental portable SQLite search updates must not make read-only CLI or MCP
routes unavailable. Existing search DB updates use WAL so readers keep seeing
the last committed snapshot while a maintenance writer replaces dirty session
documents. Full rebuilds still build a temporary DB and atomically replace the
main DB; stale SQLite sidecars are removed around that replacement so an old
WAL file cannot attach to a fresh main database.

The hot profile uses a route-cache freshness gate, not full graph freshness.
It checks route drift, portable SQLite search, and atlas projection state while
allowing graph remainder to stay deferred after the bounded graph tick. When
the graph tick is starved by budget exhaustion, the queued graph job is the
automatic continuation route and uses the profile's graph-job budget rather
than inheriting the already-exhausted foreground budget; MCP remains read-only
and only reports this route. Search projection fingerprints exclude rendered
Markdown companions (`SESSION.md` and
segment `.md`) because search documents are sourced from manifests, session
indexes, segment indexes, incidents, and raw refs. If only the stored projection
state is stale while
documents are already current, `index-maintenance` refreshes
`session_index_state` instead of rebuilding all SQLite documents and route
rows for the session. Scoped search freshness must stay on this projection
state path: it may check schema and table presence, but it must not count the
full `documents`, `document_routes`, or `route_terms` tables just to decide
whether selected sessions are dirty. Hot live-quiescence is only a freshness
guard, so it uses source/live transcript mtimes and does not hash projection
sources before the real search/atlas gates.
For graph hot state, the generated SQLite store must not be treated as current
just because the old source-state ledger says most rows are clean. The hot gate
must compare non-retired ledger sources with stored `graph_sources`; a deficit
reports `graph_source_ledger_store_count_mismatch` and routes to bounded
`graph-maintenance --apply`. It must also read the latest fresh
`graph-maintenance` report: a non-zero `remaining_count` reports
`latest_graph_maintenance_remaining_sources` so partial recovery cannot turn
green after the queue or ledger is stale. Empty aggregate `nodes` or `edges`
after a killed generated-store rebuild are a generated-projection recovery case
and route to bounded incremental maintenance unless there is a real schema or
SQLite corruption reason.

Pre-GraphRAG trust has its own loop above the generated graph:

```bash
python3 scripts/aoa_session_memory.py graph-quality-audit --write-report
python3 scripts/aoa_session_memory.py graph-quality-review diagnostics/<stamp>__graph-quality-audit.json --write-report
python3 scripts/aoa_session_memory.py graph-quality-corpus check --write-report
python3 scripts/aoa_session_memory.py graph-freshness-check --write-report
python3 scripts/aoa_session_memory.py usage-chain aoa-session-memory-mcp --kind mcp --write-report
python3 scripts/aoa_session_memory.py entity-dossier aoa-session-memory-mcp --kind mcp --write-report
```

GraphRAG-style answers must pass the answer-rule gate: important claims need
raw, segment, and session refs. If refs are missing, weak, stale, or
unreviewed, the packet must say `insufficient_evidence`, `weak_route`, `stale`,
or `needs_review` instead of presenting synthesis as truth.

On a live archive where hooks or active sessions may rewrite session sources
during the check, use the explicit quiescent-subset route:

```bash
python3 scripts/aoa_session_memory.py graph-freshness-check all \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --stable \
  --quiet-seconds 120 \
  --write-report
```

The default command remains strict full-selection truth. `--stable` checks only
sessions whose projection sources and live Codex transcript source have been
quiet for the selected window. If `~/.codex/sessions/.../rollout-*.jsonl` is
still being written, the session is reported under `deferred_live_sessions`
even when the archive projection itself is older; that means
live-not-yet-archived, not stable corruption. Deferred sessions are visible but
not treated as checked.

Scoped readiness is a truth gate for the selected window, not for the full
archive unless the command selected the full archive. Portable SQLite freshness
can therefore report `scope=selected_records` inside route-readiness while the
global provider status remains stale because of sessions outside the current
repair window.

Segment indexes must keep both the legacy event map and the universal event
facets:

- `by_type` and `by_tag`
- `by_family`, `by_phase`, `by_actor`, `by_action`, and `by_outcome`
- `by_correlation` for tool-call/tool-output linkage
- `by_conversation_act` and `by_session_act` for operator/tool/memory/MCP/goal
  route queries
- `by_route_layer` and `by_route_signal` for operational map layers such as
  scope contract, authority surface, verification state, failure mode, memory
  provenance, freshness, owner route, mutation surface, access boundary,
  resource profile, and operator preference
- per-event `relationships` for sequence and call/output refs

The route-signal classifier also keeps lightweight canonical anchors for
repeatedly referenced operational names. `aoa-*` and `aoa_*` skill-like names
route through `by-entity`; names and paths shaped like `*-mcp` or
`mcp/services/<name>` route through both `by-entity` and `by-mcp`. These are
still evidence-derived route signals, not a hand-authored project registry.

The generated entity registry is the inventory layer above those route
signals. It merges active local source surfaces (`SKILL.md`, Codex user/plugin
skills, Codex MCP config, local MCP service directories, and MCP server
`@*.tool()` functions) with archived route-term evidence for skills, MCP
services/tools, hooks, tools, APIs, scripts, validators, tests, evals,
playbooks, techniques, mechanics, graph, and memory surfaces. The registry is
written under `maps/entity-registry.json` and `.md`; it is a navigation
snapshot, not source truth. If a previously active skill, MCP service, or MCP
tool source disappears, the entry remains visible as `stale` or `removed` while
archived use stays available through search and graph routes.

```bash
python3 scripts/aoa_session_memory.py entity-registry \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --lookup aoa-session-memory-mcp \
  --kind mcp
```

Use lookup for the agent hot path: it reads the generated snapshot and answers
source identity/registration questions without rebuilding runtime discovery.
Use `entity-dossier` for how the entity behaved in sessions and what graph/ref
context should be opened next. Use
`entity-registry --write` or `entity-registry-search-sync` only as maintenance
refresh routes.

`index-maintenance` refreshes the registry when the snapshot is missing, stale,
or older than its source surfaces. MCP may expose entity inventory and lookup
read-only; `--write` registry refresh stays outside MCP.
The search projection sync for `doc_type=entity_registry` is intentionally
delta-based. It rewrites the generated snapshot, then compares stored search
docs by semantic storage fingerprint and only inserts, replaces, or removes
changed rows. Snapshot-only volatility such as the registry file hash must not
turn an otherwise unchanged inventory into a full FTS/body rewrite. A
successful sync stores a stable snapshot fingerprint in SQLite `meta`; a later
registry-only refresh may return `skipped=true` when sources and synced docs
are already current, avoiding a cold route-term scan for no-op maintenance.
When the entity registry is the only dirty surface, use the direct sync route:

```bash
python3 scripts/aoa_session_memory.py entity-registry-search-sync \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --write-report
```

This route updates `maps/entity-registry.json` and the SQLite
`doc_type=entity_registry` rows under the maintenance lock without reindexing a
random session as a side effect. Its wall-clock budget is soft/observed rather
than an interrupt: the generated snapshot and SQLite registry docs are one
consistency unit and must not be split by a mid-transaction SQLite abort.

When an agent needs to debug or study one operational thing, use the resolver
instead of guessing one axis by hand:

```bash
python3 scripts/aoa_session_memory.py trace-route aoa-memo-writeback \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --write-report
```

`trace-route` expands skill, MCP, hook, tool, Git/GitHub, entity, and path
anchors into route candidates, queries `search` through `route_layer` and
`route_signal` filters, and returns raw/segment/session refs. It is an
investigation entrypoint over existing indexes, not a promoted registry.

The agent should use indexes before opening large Markdown or raw JSONL.
Naming-readiness data in `SESSION_NAMES.md`, `session-name-index.json`,
`sessions/INDEX.md`, and `sessions/index.json` should be checked before broad
semantic naming or physical relabeling.

`session.index.json` also carries generated `work_context`, which names the
best current workspace/repository route from `cwd` and indexed path evidence.
It is a naming aid and retrieval route, not reviewed ownership truth.
It also carries generated `route_signal_counts`, which are search and atlas
routes over event facets, not reviewed distillation.

The `latest` target is a live-session convenience route, not a generated-cache
rewrite route. It resolves by readable transcript or raw-source activity first,
then falls back to session date/sequence. Maintenance timestamps such as
`manifest.updated_at` must not make a historical archive look like the active
session just because reindexing refreshed generated files.

`maps/` is the source-owned atlas skeleton. Atlas generation writes entries
under `maps/by-*/entries/` plus per-axis `INDEX.md` / `index.json` files and
root `maps/INDEX.md` / `maps/index.json`. These files are navigation
projections over existing indexes and diagnostics; they must not introduce
claims that cannot be traced back to session, segment, raw, diagnostic, or
reviewed-distillation refs.

Build the atlas after reindexing or when route-signal classifiers change:

```bash
python3 scripts/aoa_session_memory.py atlas build all \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --write-report
```

Then audit route readiness when the question is whether the whole skeleton is
findable for a future agent:

```bash
python3 scripts/aoa_session_memory.py route-readiness all \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --write-report
```

This command checks session route-signal indexes, source atlas axes, generated
atlas entries, and the portable SQLite search route against the 22 operational
layers. It is a navigation-quality gate, not a promotion or distillation step.
Frequent health/status callers should pass `--sample-limit 0`; sample-bearing
readiness is an audit path, not the hot status path.

When the question changes from coverage to classifier quality, generate a
bounded manual-sampling packet:

```bash
python3 scripts/aoa_session_memory.py route-sample-audit all \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --sample-limit 1 \
  --write-report
```

`route-sample-audit` leaves every sample `unreviewed`. Its job is to expose
raw previews, signal source/confidence, and evidence refs so a later reviewer
can accept, reject, weaken, split, or convert a classifier observation into a
narrow rule change.

Record those verdicts as a separate diagnostic artifact:

```bash
python3 scripts/aoa_session_memory.py route-sample-review \
  /srv/AbyssOS/.aoa/diagnostics/<stamp>__route-sample-audit.json \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --verdict 'scope_contract:merge_requested:002356=accept:accept:raw supports the contract' \
  --write-report
```

The review artifact is append-only evidence. It does not mutate raw,
segment indexes, atlas entries, or the sample audit. Reject/weaken/split/add
rule verdicts become classifier feedback for a later targeted patch.

## Navigation Commands

List sessions:

```bash
python3 scripts/aoa_session_memory.py list --aoa-root .
```

Show a session:

```bash
python3 scripts/aoa_session_memory.py show latest --aoa-root .
```

`show` bounds segment lists by default. Use `--full` only when the full
manifest payload is intentionally needed.

Create a rehydration packet:

```bash
python3 scripts/aoa_session_memory.py rehydrate latest --aoa-root .
```

Inspect retrieval provider status:

```bash
python3 scripts/aoa_session_memory.py search-provider-status \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --include-host
```

`portable_sqlite` remains the authoritative `.aoa` search route. Optional host
providers such as `abyss_machine_nervous` are capability-gated overlays; their
context can accelerate orientation, but it cannot replace raw/segment refs or
reviewed promotion.

Local model accelerators can be layered over portable hits:

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

The embedding route is a host semantic-search overlay. The reranker route only
changes candidate order and writes `host_rerank` metadata onto `.aoa` hits.
Neither layer is portable authority, and neither may promote a claim without
the raw/segment refs already carried by the hit.

Literal raw-text FTS is a bounded read route. Default agent-facing queries keep
exact token matching but avoid `bm25` rank sorting so common terms do not block
the session. Use `--query-timeout-ms 0` only for an explicit offline scan where
rank sorting is worth the cost. A timed-out raw-text route must return a
`sqlite_query_timeout` diagnostic and `next_expansion_command`, not a hanging
agent workflow.

Before broad literal search, use the read-only planner route:

```bash
python3 scripts/aoa_session_memory.py literal-query-plan \
  --query "aoa-session-memory-mcp" \
  --kind mcp \
  --doc-type event
```

The planner classifies the literal shape, checks typed route candidates and the
generated entity registry, then reports the cheapest reliable first route:
entity usage/trace/graph for operational anchors, route-signal structured
search for noisy phrases that still resolve to concrete route signals, typed
registry/inventory for broad class questions such as `skills`, `MCP`, `hooks`,
or `tools`, session rehydration plus session-scoped search for exact session
ids, structured search for exact filters, scoped full-text shards when a
bounded shard can answer, or the monolith fallback only when raw literal recall
is the right safety net. The packet exposes `classifications`,
`cost_profile`, `fallback_plan`, and `next_expansion` so an agent can see the
selected plan, bounded fallback, timeout posture, and next command without
guessing. For broad class questions with use/error/consequence intent, the
plan includes an entity-usage scenario sample route after the inventory/registry
route. The planner is route advice, not evidence truth; returned commands still
route to raw/segment/session refs.
For command literals, the planner separates the executable/script anchor from
the full raw phrase. Structured routes use the command anchor; exact recall
still keeps the original command text as the last fallback.

Build a recipe-based retrieval packet:

```bash
python3 scripts/aoa_session_memory.py retrieve continue-techniques-session \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --query "aoa-techniques continuation" \
  --write-report
```

Retrieval packets are the Agentic RAG layer over the archive: search recall,
session identity, phase candidates, continuation signals, and next commands in
one bounded packet. They still route back to raw and segment refs.

## Graph And GraphRAG

The graph store is generated from the same session indexes, segment indexes,
route signals, event relationships, and raw refs that already feed search and
atlas routes. The live store is `graph/graph.sqlite3`; `nodes.jsonl` and
`edges.jsonl` are sidecar snapshots exported from that store:

Graph route-signal materialization is intentionally tiered. Segment sources
emit `segment_has_route_signal` summary edges for every indexed route signal,
with counts and segment refs. Event-level `mentions_route_signal` edges are
reserved for concrete operational anchors where graph traversal benefits from
exact event proximity: skills, MCPs, hooks, tools, APIs, plugins, agents,
scripts, validators, tests, evals, Git, playbooks, techniques, mechanics,
graph, memory, and goals. Wide facets such as scope contracts, authority
surfaces, verification state, operator preference, generic path/entity
mentions, freshness, confidence, and access-boundary signals stay exact in
segment/search indexes and appear in graph through segment/session summaries.
Do not schema-bump the graph solely for this policy; the policy is recorded in
graph metadata, `graph_sources.graph_event_route_signal_edge_policy`, and the
graph source fingerprint. Old sources therefore become normal projection drift
that hot status can see without a full session-source scan. The automatic route
is bounded `graph-maintenance`; a store-only rebuild is a manual,
resource-gated repair after explicit host/disk/memory review.

```bash
python3 scripts/aoa_session_memory.py graph-build all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write \
  --force-large-export
```

For normal growth, use the incremental maintenance route:

```bash
python3 scripts/aoa_session_memory.py graph-maintenance all \
  --apply \
  --batch-limit 3 \
  --budget-seconds 300 \
  --refresh-chunk-size 512 \
  --write-report \
  --write-hash-cache
```

That small batch is the hot/timer-safe route. For a large global backlog, the
agent-facing `maintenance-status` recommendation may use a manual budgeted
batch of `25` sources. Prefer launching that route through
`abyss-machine resource launch --class medium --kind indexing` so CPU, memory,
thermal, and swap pressure are explicit before the writer lock is taken.

Each session and segment is a graph source. Dirty sources are replaced
transactionally: old node/edge contributions for that source are removed, new
contributions are inserted, and only touched aggregate nodes/edges are
refreshed. Incremental maintenance groups selected dirty/missing sources by
session and refreshes aggregate nodes/edges through streamed SQLite cursors.
`--refresh-chunk-size` caps the touched node/edge id set per aggregate refresh
query; the report's `maintenance_detail` records requested ids, chunks, rows,
and missing aggregates. Automated maintenance keeps both source batches and
refresh chunks intentionally bounded; large historical sessions can still be
expensive without a full rebuild because a few source slices may touch many
aggregate edges. `--batch-limit` is a source-count bound, not a strict cost
bound. `--budget-seconds` is the wall-clock bound for live and unattended
passes; budget exhaustion defers unstarted sources as `deferred_time_budget`,
and an exhausted in-flight SQLite mutation is rolled back before reporting.
For unfiltered `all` runs, graph-maintenance reports keep matched source lists
bounded as `matched_source_key_count` plus `matched_source_key_sample`; the full
`matched_source_keys` list is retained only for explicit `--source-key` runs.
Graph source state reports include bounded reason counts, normalized reason
groups, examples, and a maintenance recommendation so an agent can distinguish
small missing-source repair from mass classifier/fingerprint drift without
defaulting to a full rebuild.
Graph source fingerprints include schema, classifier/policy versions, and the
contribution payload mode. A graph storage-layout change is therefore repaired
through the same dirty-source maintenance route as classifier or source-index
drift.
Use `graph-maintenance --plan-refresh-costs` for a dry exact-cost plan over the
candidate pool before applying a bounded repair; it parses the candidate
sources and reports planned aggregate node/edge refresh counts without mutating
`graph.sqlite3`. Dry exact-cost planning is intentionally capped by
`GRAPH_MAINTENANCE_PLAN_CANDIDATE_POOL_LIMIT` instead of scaling as
`batch-limit * N`; large backlog probes should read
`maintenance_detail.candidate_pool_policy`,
`candidate_pool_actionable_count`, and `candidate_pool_truncated_count` rather
than treating dry-plan `batch-limit` as permission to price hundreds of
sources in one foreground pass.
Incremental maintenance plans exact old-plus-new refresh cost, sorts
actionable sources cheap-first, and isolates individually oversized sources so
one historical session does not block smaller repairs. `index-maintenance` and
`auto-maintenance` also use `graph_max_refresh_nodes` /
`graph_max_refresh_edges` guards; individually oversized sources are reported
under `oversized_sources`, while sources that fit alone but not the current
combined pass are reported under `budget_deferred_sources` for a narrower or
heavier pass. Use `--source-key` with an explicit higher guard when the report
names a specific oversized graph source and the operator wants to repair that
source without widening the whole maintenance batch:

```bash
python3 scripts/aoa_session_memory.py graph-maintenance all \
  --source-key segment:<session-id>:<segment-id> \
  --apply \
  --batch-limit 1 \
  --max-refresh-nodes 12000 \
  --max-refresh-edges 20000 \
  --write-report \
  --write-hash-cache
```

Full `graph-build all --write --force-large-export` remains the fallback for
schema changes, corruption, invariant failure, or large historical imports that
have already been routed through the heavy/resource-gated lane. Excessive dirty
or missing-source backlog alone should continue through bounded
`graph-maintenance --apply` batches unless the operator deliberately chooses an
offline rebuild.

On a large live archive, treat full graph rebuild as an offline/resource-gated
repair, not the default continuation route. If a full store-only rebuild is
killed by memory pressure and leaves `graph/graph.sqlite3` empty, hot status
must surface `graph_store_nodes_empty` / `graph_store_edges_empty` and the next
safe route is bounded `graph-maintenance --apply` recovery. Raw/session/search
evidence remains the stronger source truth.

When the live archive is large and sidecar snapshots are not needed, prefer a
store-only rebuild to avoid multi-GB `nodes.jsonl` / `edges.jsonl` exports and
unnecessary peak disk pressure:

```bash
python3 scripts/aoa_session_memory.py graph-build all \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --write \
  --store-only \
  --in-place \
  --progress-every 10
```

Use `--in-place` only with `--store-only`. It is appropriate for the live
generated graph store when raw/search/atlas evidence is already preserved and
there is not enough disk headroom to hold both the old and rebuilt SQLite
stores. Store-only rebuild removes stale sidecar snapshots and reports the
sidecar state as `not_exported`.

Generated snapshot files live under `graph/nodes.jsonl`,
`graph/edges.jsonl`, and `graph/index.json` only when explicitly exported.
They are derived navigation aids, not reviewed truth. On a large live archive,
use the graph store or bounded trace/search packets for interactive work and
prune the snapshots after proof/export:

```bash
python3 scripts/aoa_session_memory.py graph-prune-sidecar --apply --write-report
python3 scripts/aoa_session_memory.py graph-raw-ref-prune --apply --min-free-gb 20 --write-report
python3 scripts/aoa_session_memory.py graph-sqlite-compact --write-report
```

A fully absent sidecar is `not_exported`, not a freshness failure, as long as
`graph.sqlite3` is intact. Partial, invalid, or stale sidecars stay visible in
freshness gates so stale snapshot data is not mistaken for current truth.
`needs_offline_graph_build` is reserved for store/schema/corruption fallbacks.
Full forced rebuild streams source contributions into `graph.sqlite3` and can
reclaim old generated sidecars before writing a fresh snapshot to avoid
unnecessary peak disk pressure.

Read-only graph packets:

```bash
python3 scripts/aoa_session_memory.py graph-neighborhood aoa-session-memory-mcp --kind mcp --depth 2
python3 scripts/aoa_session_memory.py graph-neighborhood aoa-session-memory-mcp --kind mcp --depth 2 --limit 12 --edge-limit 48
python3 scripts/aoa_session_memory.py graph-timeline aoa-session-memory-mcp --kind mcp
python3 scripts/aoa_session_memory.py graph-shortest-path aoa-session-memory-mcp exec_command --kind auto
python3 scripts/aoa_session_memory.py graph-bridge aoa-session-memory-mcp exec_command --source-kind mcp --target-kind tool
python3 scripts/aoa_session_memory.py graph-cooccurrence exec_command --kind tool
```

`graph-neighborhood` is compact by default: `--limit` bounds nodes and
`--edge-limit` bounds edges. Packets report `truncated`,
`omitted_node_count`, and `omitted_edge_count`; raise these budgets only for an
explicit deeper relation walk, then verify important claims through raw,
segment, or session refs.
`graph-bridge` is the consumer route for relation questions between two
operational anchors. It wraps shallow source/target neighborhoods, compact
side-neighborhood event/ref samples, freshness/noise flags, evidence refs,
phase timings, and next expansion commands; it remains generated route
evidence, not reviewed truth. Use the returned `graph-timeline` expansion when
deeper event ordering is needed, and `shortest_path` only when a deeper path is
actually needed.

GraphRAG combines lexical search entrypoints, optional semantic/rerank overlays,
graph-store expansion, cooccurrence clusters, evidence refs, and freshness:

```bash
python3 scripts/aoa_session_memory.py graphrag-packet \
  --query aoa-session-memory-mcp \
  --anchor aoa-session-memory-mcp

python3 scripts/aoa_session_memory.py graph-explain-packet \
  "debug aoa-session-memory-mcp" \
  --anchor aoa-session-memory-mcp

python3 scripts/aoa_session_memory.py graph-eval

python3 scripts/aoa_session_memory.py graph-quality-audit --write-report

python3 scripts/aoa_session_memory.py graph-quality-review diagnostics/<stamp>__graph-quality-audit.json \
  --verdict mcp_access_plane=accept:accept:"good MCP evidence route" \
  --write-report
```

The stop line is the same as search and atlas: no graph claim is usable without
raw, segment, or session refs, and no GraphRAG packet promotes durable memory.
`graph-quality-audit` is the quality gate for operational anchors: it samples
MCPs, skills, hooks, tools, and paths, then reports whether refs and freshness
are strong enough for a reviewer to make an evidence verdict. Use
`--full-graphrag` for slower offline runs that assemble full GraphRAG packets
for every sampled anchor. `graph-quality-review` records verdicts such as
`accept`, `reject`, `weak`, `wrong_anchor`, or `stale`, then emits quality
feedback and regression-candidate anchors. It writes only diagnostics reports;
it does not repair indexes, rewrite maps, or promote memory.

Run a focused stress pass over the first 100 compaction-closing intervals:

```bash
python3 scripts/aoa_session_memory.py stress-pass latest \
  --aoa-root . \
  --compactions 100 \
  --write
```

`stress-pass` writes the complete JSON/Markdown artifact when `--write` is
set and keeps stdout bounded by default. Use `--full` only for deliberate
complete JSON output.

Import historical Codex JSONL sessions in chronological order:

```bash
python3 scripts/aoa_session_memory.py import-codex-sessions \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --since-days 21 \
  --dry-run \
  --write-report
```

Remove `--dry-run` only after the report count is coherent. Existing indexed
archives are skipped by default; use `--force` only for a deliberate rebuild.
The full import report is written under `diagnostics/`.

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

Add `--apply` only after the planned candidates are coherent. Use
`--max-raw-mb` for bounded periodic runs and remove or raise it for deliberate
large-session recovery.

Create a provisional first-pass distillation map:

```bash
python3 scripts/aoa_session_memory.py distill latest --aoa-root .
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

Remove `--dry-run` for a bounded pass. Keep `--max-raw-mb` on broad archive
runs and set `--budget-seconds` for foreground maintenance. The budget is
checked between session rewrites so a selected session is not left
half-regenerated; large raw sessions should use an explicit heavy-session route
instead of silent unbounded regeneration.

Build a first-wave conveyor for many historical sessions:

```bash
python3 scripts/aoa_session_memory.py batch-distill \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --since-days 21 \
  --write-report
```

This command plans by default. It separates `auto_first_pass`,
`manual_review`, `manual_review_deep`, `manual_review_standard`,
`manual_review_sample`, `mechanics_candidate`, `low_risk_indexed`, and
`diagnostic` lanes. Add `--apply` only when writing provisional first-pass
distillation artifacts is intended. The conveyor report is written under
`diagnostics/` when `--write-report` is set.

`manual_review` is not a demand that the operator reread every transcript. It
marks a responsibility layer: an agent may continue the work, but it must use
project grounding, evidence references, and promotion gates. Session profiles
therefore keep the source `cwd` and nearest project guidance files when they
exist. Owner resolution is recorded separately so fallback-grounded sessions
can still recover a likely real owner from indexed paths without pretending the
fallback workspace is the owner.

Repair weak generated titles before a broad manual pass:

```bash
python3 scripts/aoa_session_memory.py repair-session-titles all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --since-days 21 \
  --write-report
```

Add `--apply` only after the plan is coherent. This repairs names and generated
identity surfaces; it does not change raw evidence.

Classify naming readiness before applying semantic names or relabels:

```bash
python3 scripts/aoa_session_memory.py naming-readiness all \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --since-days 21 \
  --refresh-indexes \
  --write-report
```

Treat `blocked` as lower-layer recovery, `needs_reindex` as a generated-index
refresh route, `needs_phase_discovery` as a segment review route, and
`ready_for_semantic_name` as the only direct semantic-name queue.

For a `needs_phase_discovery` session, write the unreviewed phase candidate
layer before naming. Then use its `review_queue` for candidates that need
semantic synthesis instead of applying path/event names directly:

```bash
python3 scripts/aoa_session_memory.py phase-discovery <session-label-or-id> \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write \
  --write-report
```

For high-volume naming passes, generate batch review packets before applying
names:

```bash
python3 scripts/aoa_session_memory.py phase-review-assist <session-label-or-id> \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --from-segment <segment-id> \
  --limit 8 \
  --write \
  --write-report
```

The assist packet is a speed layer, not a truth layer. It pre-collects the raw
refs and synthesis inputs an agent would otherwise fetch manually for every
segment.

After a reviewer fills the generated plan with reviewed names, preview or apply
the non-empty items in one guarded batch:

```bash
python3 scripts/aoa_session_memory.py apply-phase-review-plan <session-label-or-id> \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --plan sessions/<session>/naming/phase-review-plan.json \
  --apply \
  --write-report
```

This batch command still routes each item through the reviewed phase-name
writer, skips empty `reviewed_name` entries, and does not auto-accept machine
candidates.

For many sessions, create a mass naming wave:

```bash
python3 scripts/aoa_session_memory.py naming-wave build \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write \
  --write-report
```

The wave plan groups sessions by next action:

- `sync_source_transcript`: source transcript is newer than archived raw;
- `reindex_session`: generated indexes are stale or deferred;
- `semantic_session_name_review`: fill `reviewed_name` before applying;
- `review_phase_queue_then_refine_session_name`: resolve open phase queues
  before treating the umbrella session name as settled;
- diagnostic/low-signal skips.

Apply only reviewed or deliberately approved work:

```bash
python3 scripts/aoa_session_memory.py naming-wave apply \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --plan diagnostics/naming-waves/<wave-id>/naming-wave-plan.json \
  --apply \
  --write-report
```

Use `--apply-preflight` only when the sync/reindex preflight batch has been
sampled. Use `--accept-proposed` only after sampling high-confidence `ok`
candidate names. The default apply path requires `reviewed_name`.

Check naming quality separately:

```bash
python3 scripts/aoa_session_memory.py naming-wave audit \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --plan diagnostics/naming-waves/<wave-id>/naming-wave-plan.json \
  --write-report
```

This audit is not a proxy for reading raw evidence. It catches repeatable
quality failures: generic names, missing raw refs, duplicate slugs, stale
coverage, open phase queues, missing anchors, and accidental physical relabel
pressure.

Review one candidate through the guarded route before applying:

```bash
python3 scripts/aoa_session_memory.py review-phase-name <session-label-or-id> \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --segment <segment-id> \
  --reviewed-name "<reviewed phase name>" \
  --apply \
  --write-report
```

Write manual-review packets for the deep lane:

```bash
python3 scripts/aoa_session_memory.py manual-review \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --since-days 21 \
  --priority deep \
  --apply \
  --write-report
```

Manual-review apply is append-only. The first apply writes
`manual-review-wave1`; later applies choose the next `manual-review-waveN`
unless `--wave-id` is supplied. Each session keeps all waves in its manifest and
`distillation/review.index.*`, and every packet remains
`open_for_future_passes` until a reviewed promotion/distillation path closes it.

Then aggregate promotion candidates without promoting them:

```bash
python3 scripts/aoa_session_memory.py promotion-review \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --since-days 21 \
  --write-report
```

Mechanics candidates are counted from significant events only: failures,
process lessons, optimization/risk/dead-branch signals, destructive commands,
and failed outcomes. Generic command output or a successful verification
command by itself is not enough to put a session into the mechanics queue.

Use the bundle skill routes for deliberate agent work:

```text
aoa-session-memory-global-route -> top-level user router
aoa-session-history-import      -> historical Codex JSONL batch import
aoa-session-batch-distill       -> first-wave historical-session conveyor
aoa-session-manual-review       -> manual-review packets and promotion queue
aoa-session-reindex             -> regenerate generated indexes from raw
aoa-session-search              -> portable search, entity registry, route trace
aoa-session-memory-evidence-route -> cross-session entity usage, consequences,
                                   graph, and raw-ref evidence routing
aoa-session-memory-stress-pass  -> bounded large-archive checks
aoa-session-memory-audit        -> completion readiness
aoa-session-memory-doctor       -> filesystem and live health
aoa-codex-hooks-status          -> native Codex hook trust
aoa-codex-compact-probe         -> live PreCompact/PostCompact proof
```

Install the top-level router for the current Codex user:

```bash
python3 scripts/aoa_session_memory.py install-user-skill \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

Install the evidence route explicitly when agents in other owner contexts should
discover the prior-session entity/usage/consequence/graph route directly:

```bash
python3 scripts/aoa_session_memory.py install-user-skill \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --skill aoa-session-memory-evidence-route
```

Generate the user-level hook config for the selected install roots:

```bash
python3 scripts/aoa_session_memory.py hooks-config \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

Install the generated hook config with a backup of the previous file:

```bash
python3 scripts/aoa_session_memory.py hooks-config \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write ~/.codex/hooks.json
```

Export a clean bundle for a future standalone repository:

```bash
python3 scripts/aoa_session_memory.py export-bundle \
  --target-dir /tmp/aoa-session-memory-bundle \
  --source-aoa-root . \
  --force
```

Install the bundle into another workspace:

```bash
python3 scripts/aoa_session_memory.py install \
  --workspace-root /path/to/workspace \
  --source-aoa-root . \
  --force
```

Manually rebuild from raw:

```bash
python3 scripts/aoa_session_memory.py sync \
  --aoa-root /path/to/workspace/.aoa \
  --workspace-root /path/to/workspace \
  --session-id <session-id> \
  --transcript-path <raw-jsonl> \
  --cwd <cwd>
```

Run the full local doctor:

```bash
python3 scripts/aoa_session_memory.py doctor \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --check-live-hooks
```

Check the local Codex grounding:

```bash
python3 scripts/aoa_session_memory.py codex-grounding \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

Check native Codex hook discovery and trust:

```bash
python3 scripts/aoa_session_memory.py codex-hooks-status \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

If matching hooks are present but untrusted, add `--trust-current`.

Run a live manual compaction probe:

```bash
python3 scripts/aoa_session_memory.py codex-compact-probe \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --trust-hooks
```

Run an end-to-end pipeline validation in a temporary workspace:

```bash
python3 scripts/aoa_session_memory.py validate \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

Run the completion audit:

```bash
python3 scripts/aoa_session_memory.py audit \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

Run the standalone bundle audit from a clean package checkout:

```bash
python3 scripts/aoa_session_memory.py audit \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/aoa-session-memory \
  --portable-bundle
```

The audit may return non-zero while honest remaining gates exist. Do not treat
it as a replacement for tests or `doctor`.

## Failure Modes

### Invalid Hook JSON

Symptom: Codex reports invalid hook output.

Cause: hook stdout contains fields outside the Codex event schema.

Response: keep rich AoA receipts on disk, but return only Codex protocol fields
on stdout.

### Raw Session Unavailable

Symptom: `transcript_path` is missing, unreadable, moved, or stale.

Response: write `INCIDENT.md` and `DIAGNOSTIC.json`; do not create fake memory.
Global audit must treat this as `raw_exists=false` and skip raw parsing unless
the raw path points to a real file.

### Duplicate Hook Receipts

Symptom: user-level and project-level hooks both fire, or an event is retried.

Response: tolerate duplicate hook receipts; archive regeneration must remain
idempotent for the same raw transcript.

### Untrusted Native Hooks

Symptom: hooks are present in `~/.codex/hooks.json`, but Codex does not run one
or more of them.

Response: run `codex-hooks-status`. If the matching AoA hooks are `untrusted`,
rerun it with `--trust-current`.

### Premature or Repeated Compaction

Symptom: context loses details before the work is complete.

Response: rely on raw archive and segment indexes, not active context memory.

### Unindexed Bulk Markdown

Symptom: agent can only read huge generated Markdown files.

Response: fix the index route. The answer should be in `session.index.json` or
the relevant segment index before the full segment is opened.

## Verification Gates

Minimum gate after code or hook changes:

```bash
python3 -m py_compile scripts/aoa_session_memory.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_session_memory.py
python3 scripts/aoa_session_memory.py codex-grounding --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py codex-hooks-status --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py validate --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py codex-compact-probe --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --trust-hooks
python3 scripts/aoa_session_memory.py stress-pass latest --aoa-root /path/to/workspace/.aoa --compactions 100 --write
python3 scripts/aoa_session_memory.py export-bundle --target-dir /tmp/aoa-session-memory-bundle --source-aoa-root . --force
python3 scripts/aoa_session_memory.py doctor --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --check-live-hooks --check-codex-grounding
python3 scripts/aoa_session_memory.py audit --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
```

Manual hook schema check:

```bash
printf '{"session_id":"demo","transcript_path":"/no/such","cwd":"/tmp","hook_event_name":"PreCompact","trigger":"auto","turn_id":"turn"}' \
  | python3 scripts/aoa_session_memory.py hook \
      --event-name PreCompact \
      --workspace-root /path/to/workspace \
      --aoa-root /tmp/aoa-hook-check
```

Expected stdout:

```json
{"continue": true}
```

## Distillation Boundary

The pipeline does not distill during hooks.

Distillation is a later reviewed act:

```text
raw event
  -> observed
  -> distilled
  -> experience candidate
  -> pattern candidate
  -> reviewed pattern
  -> automation seed
  -> implemented
  -> validated
```

This keeps preservation cheap, stable, and evidence-heavy while still giving
the system a path to learn from its history.

The review path is layered. First-wave automation writes provisional maps.
Project-grounded agents connect those maps to the actual repository or
workspace laws. Operators sample and approve promoted claims. Only after that
may patterns become skills or automation.
