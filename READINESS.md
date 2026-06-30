# AoA Session Memory Readiness

## Snapshot

Date: 2026-05-26

This file maps the current `.aoa` session-memory goal to concrete evidence.
It is a readiness snapshot for agents, not a substitute for running the gates.

## Objective

Build the `.aoa` session-memory mechanism end to end:

- preserve full raw Codex session material
- preserve compaction intervals before and after context compression
- index raw material so agents can navigate without loading everything
- keep hook output schema-valid and fail-open
- provide skills and docs that route agents through the same pipeline
- keep the kernel portable and separable from local AoA overlays
- test the pieces alone and together

## Implemented Surfaces

- Design: `DESIGN.md`
- Agent route design: `DESIGN.AGENTS.md`
- Operation route: `PIPELINE.md`
- Install/export route: `INSTALL.md`
- Naming policy: `NAMING.md` and `config/naming-policy.json`
- Naming wave quality examples: `config/naming-golden-set.json`
- Event taxonomy: `config/event-taxonomy.json`
- Operational route-signal layer: event `facets.route_signals`,
  segment `by_route_layer` / `by_route_signal`, session
  `route_signal_counts`, search filters, and atlas generation
- Agent event and task episode layer: event `facets.agent_event`, segment
  `by_agent_event`, session `agent_event_counts`, `task_episode_counts`,
  generated `task_episodes`, SQLite `agent_event` / `task_episode_id`
  filters, and CLI routes `agent-responses`, `agent-closeouts`,
  `agent-progress-updates`, `agent-reasoning-windows`, `task-episodes`, and
  `answer-neighborhood`; structured list routes without text query expose
  `cost_profile` and skip raw preview/body hydration/FTS; agent-event routes
  can use the monthly shard catalog with `--use-shards`
- Agent event classification audit: `agent-event-audit` over real sessions,
  including longest-session selection, route probes, bounded raw event-shape
  samples, weak spots, and diagnostics without promoting generated classes to
  reviewed truth
- Agent atlas skeleton: `maps/`, `config/atlas-policy.json`, and
  `schemas/atlas-route-entry.schema.json`
- Distillation routes: `config/event-distillation-routes.json`
- Batch distillation policy: `config/batch-distillation-policy.json`
- Portable search route: `search-index`, `search`, `search-catalog`,
  `search-shards`, runtime `search/`, generated `search/catalog.json`, monthly
  shard DBs under `search/shards/`, and `skills/aoa-session-search`
  (`2026-06-21T10:20:10Z` live catalog: `ok=true`, `status=current`,
  `session_count=282`, `shard_count=3`, `materialized_shard_count=3`,
  `catalog_state_basis=live_session_indexes`, diagnostics report
  `diagnostics/20260621T102032Z__search-catalog.json`; live
  `search-shards all` report `diagnostics/20260621T101903Z__search-shards.json`,
  coordinator elapsed `1287190ms`, search monolith `9.5G`, monthly shards
  `9.4G`; structured shard fan-out for `assistant_answer` returned in `0.13s`,
  while broad FTS `hook timed out` remains slow: shard fan-out `79.57s`,
  monolith `127.63s`; later live catalog proof showed existing structured
  shard DBs can be used for structured agent-event routes even when the catalog
  cannot mark them fully materialized for raw FTS: `agent-responses
  --agent-event assistant_open_thread --use-shards --limit 3` returned through
  `materialized_shard_fanout` in `1.48s`, with `uses_fts=false`,
  `hydrates_body=false`, `uses_shards=true`, and diagnostic
  `search_shard_fanout_using_structured_nonmaterialized_shards:3`)
- Generated entity registry: `entity-registry`,
  `maps/entity-registry.json`, `doc_type=entity_registry`, active/observed/
  stale/removed/unknown states for skills, MCP services/tools, tools, APIs,
  hooks, scripts, validators, tests, evals, playbooks, techniques, mechanics,
  graph, and memory surfaces; active source discovery includes MCP server
  `@*.tool()` functions from stack MCP service sources, so newly added MCP
  tools can be registered before they appear in archived usage; MCP access is
  read-only; direct `entity-registry-search-sync` refreshes the generated
  registry snapshot and SQLite registry docs without selecting an arbitrary
  session for `search-index --no-rebuild`; registry refresh now defaults to
  `--observed-source auto`, preferring current operational route-rollup for
  observed archived entities, retaining previous observed anchors up to prior
  per-kind cardinality, and keeping full route-term aggregation behind the
  explicit `--observed-source route-terms` heavy/deep lane; sync reports expose
  `observed_route_source`, `document_count_source`, and `phase_timings`
- Entity usage-chain consumer route: `usage-chain` is the compact first packet
  for operational entity usage/consequence questions; it returns direct usage,
  result/consequence chains, evidence refs, freshness, noise flags, and next
  expansion commands while skipping GraphRAG, graph neighborhood, and
  raw-preview neighborhoods by default
- Entity usage fast path: `entity-usage-audit` starts from typed route signals
  and direct usage classes, skips raw semantic previews during the indexed
  harvest, avoids compressed full-body hydration when bounded search rows are
  enough, and only falls back to broad text search when structured route hits do
  not include direct usage evidence
- Entity dossier consumer route: `entity-dossier` is the heavier packet for
  operational entity usage/consequence/graph/ref questions that need full
  graph/cooccurrence/timeline context; it routes to usage audit, neighborhood
  windows, graph expansion, and raw/segment/session refs without becoming owner
  truth
- Route-trace resolver: `trace-route` / `resolve-anchor` over skill, MCP,
  hook, tool, Git/GitHub, entity, and path anchors; typed route hits now skip
  the broad text fallback once the requested evidence limit is satisfied, so
  MCP/skill/tool fast paths do not inherit raw FTS timeout diagnostics when the
  route index already answered the question
- Incremental graph store, sidecar snapshots, and GraphRAG packets:
  `graph-build`, `graph-maintenance`, `graph-neighborhood`,
  `graph-timeline`, `graph-shortest-path`, `graph-bridge`,
  `graph-cooccurrence`,
  `graphrag-packet`, `graph-explain-packet`, `graph-eval`, and
  `graph-quality-audit` / `graph-quality-review`
- Large-archive graph maintenance controls: store-only / in-place
  `graph-build`, progress heartbeat, optional sidecar export, grouped
  dirty/missing source repair by session, streamed aggregate refresh,
  `graph-maintenance --budget-seconds`, and profile-level refresh chunk sizes
  plus aggregate refresh budget guards for `index-maintenance` /
  `auto-maintenance`
- Storage weight controls: `storage-audit`, compact graph aggregate and
  contribution payloads with evidence hydration from contribution rows, sampled
  graph aggregate payload reclaim estimates, materialized
  `graph-cardinality` node/edge type counts, and search body storage with
  full-text FTS plus compressed selected-hit hydration; search-shard
  materialization reports expose per-document-type counts, event-document
  totals, and event-document ratio, while `maintenance-status` surfaces
  `operations.search_pressure.document_hotset` so agents can distinguish true
  structured event/document cardinality pressure from physical SQLite reclaim
  or full-text shard toggles
- SQLite physical compaction promotion: `graph-sqlite-compact` and
  `search-sqlite-compact` can now promote a verified `VACUUM INTO` copy over
  the live generated store with `--promote-copy`, keeping a backup by default
  and deleting it for actual reclaim only with
  `--delete-backup-after-verify`. The route stays under the manual-bulk
  maintenance lock, checkpoints WAL before promotion, verifies the promoted
  live DB, and never mutates raw/session evidence.
- Pre-GraphRAG trust layer: source-owned
  `config/graph-quality-regression-corpus.json`, `graph-quality-corpus`,
  `graph-freshness-check`, `entity-dossier`, and GraphRAG packet
  `answer_rules`; `graph-freshness-check --stable` provides an explicit
  quiescent-subset gate for live archives and reports recent writes as
  `deferred_live_sessions` instead of hiding them
- Automatic index maintenance route: `index-maintenance` / `maintain-index`
  over stale route indexes, per-session search/atlas projection fingerprints,
  bounded budgets, portable search freshness, atlas freshness, and readiness
  reports
- Partial atlas maintenance merges compact generated axis indexes, and scoped
  graph maintenance ignores out-of-scope graph sources instead of treating
  every non-selected row as an orphan
- Resource-gated unattended maintenance route: `auto-maintenance` /
  `maintain-auto` profiles `hot` (`probe`, recent route/search/atlas repair
  plus a small bounded graph tick with explicit graph remainder deferral),
  `backlog` (`medium`, recent index+graph repair), `catchup` (`medium`,
  full-scope bounded search/atlas catch-up without graph repair), and `deep`
  (`heavy`, full repair). Schema-level, missing, empty, or corrupt search
  stores are deferred from non-`deep` profiles to the heavy lane instead of
  being rebuilt by a bounded timer; MCP remains read-only and plan-only
- Maintenance coordinator state:
  `diagnostics/maintenance-coordinator.json` plus the shared
  `diagnostics/auto-maintenance.lock` expose active owner job, mode,
  deadline, lock wait, touched search/atlas/graph/entity projection surfaces,
  last result, DB/WAL size status, operations warnings, last successful
  auto-maintenance profiles, recent problem jobs, and `why_maintenance_long`
  search-index/storage evidence through `maintenance-status --full`;
  graph storage pressure is visible through `operations.graph_pressure` with
  cached graph cardinality, top edge types, physical compaction headroom, and
  the next safe route before any deep audit or SQLite compaction;
  `hot` defers when a bulk/catchup/backlog/deep/manual-bulk lease is active;
  manual-bulk writers return a bounded
  `session_memory_maintenance_lock_conflict` packet instead of waiting
  silently behind an active maintenance lease, and the coordinator persists the
  refusal as `last_conflict` with requested owner/mode, blocking owner,
  surfaces, lock wait, timeout, and skipped/deferred reason;
  `maintenance-status` exposes a `live_tail` packet over deferred live
  freshness rows with `waiting_for_quiet_window` vs `ready_for_catchup`,
  quiet-window remaining seconds, `next_ready_at`, and the typed catch-up
  command so agents do not confuse non-actionable live tail with broken search;
  `auto-maintenance-resource catchup all` uses that same packet as a fast-path
  preflight when live-tail is ready, instead of launching broad
  `auto-maintenance catchup all` for a single deferred live tail: search-deferred
  sessions wrap targeted `index-maintenance <session> --skip-graph-repair
  --skip-token-accounting`, while graph-only deferred live sources wrap the
  ledger-seeded `graph-maintenance --use-queue --queue-seed-include-deferred-live`
  route;
  2026-06-21 live proof: manual `graph-maintenance all --apply` behind an
  active `auto-maintenance:hot` lease returned `mutates=false` and persisted
  `last_conflict` with `blocking_owner=auto-maintenance:hot`,
  `requested_mode=manual-bulk`, `touched_surfaces=["graph"]`, and
  `lock_wait_ms=5004`;
  search-deferred live sessions route through targeted
  `index-maintenance <session> --skip-graph-repair`, with graph repair kept as
  an explicit follow-up
- Hot route-cache maintenance avoids graph scans on the gate path:
  `route-cache-freshness-gates` checks route/search/atlas state while the
  maintenance pass advances graph state in small batches; search projection
  fingerprints exclude rendered Markdown companions and can refresh stale
  `session_index_state` without rebuilding SQLite documents; scoped search
  freshness uses `session_index_state` and lightweight table-presence probes
  instead of counting the full SQLite document and route-posting tables; hot
  live-quiescence uses mtime-only source/live transcript checks before bounded
  search/atlas gates; if route-cache work spends the hot budget before graph
  work starts, a bounded graph job is queued as the automatic continuation
  route with a separate profile graph budget
- Search catalog freshness sync keeps shard route packets current after
  live-sync or freshness probes update `search_freshness_state`: deferred-live
  sessions now update `search/catalog.json` shard freshness counters without a
  heavy raw/session-index scan, so MCP/agent fast-path defaults do not fall
  back to monolith merely because catalog freshness lagged the SQLite state.
- Search catalog shard-only recovery keeps generated navigation complete when a
  monthly shard has a `session_index_state` row that the monolith catalog seed
  does not. The recovered row stays explicitly marked
  `catalog_source=shard_session_index_state_recovery` and
  `monolith_status=missing`; shard freshness and dirty-only maintenance own the
  repair route, while raw/session indexes remain the evidence authority.
- Operational route-rollup now has a scoped shard replacement lane: when one
  source shard changes, `maintenance-status` can surface
  `search-operational-route-rollup --shard <shard> --apply --write-report`
  instead of a full rollup rebuild. Live proof on `month/2026-06` replaced one
  shard in `8586ms` with `update_mode=scoped_shard_replace`, kept all `3`
  rollup shards, and left the combined rollup current with `53774` rows and
  `1030518` candidate route postings; the preceding full refresh over the same
  three shards took `217486ms`.
- Dirty-only shard catch-up keeps live-tail repairs bounded: `search-shards`
  accepts `--dirty-only` only with `--no-rebuild`, selects non-current
  sessions from `search/catalog.json`, skips `deferred_live` rows by default,
  refuses missing shard DBs, and reports `pre_filter_selected_count`,
  `dirty_selected_count`, `skipped_current_count`, and
  `deferred_live_skipped_count`. It also reports `selected_sessions`, phase
  timings, and budget-exhausted `active_session` / `remaining_sessions` rows,
  so a large dirty session becomes an explicit heavy-tail route instead of a
  silent `processed_count=0`. Dirty-only selection is cheap-first by catalog
  `document_count`, so small stale rows can drain before a known heavy-tail
  session. Scoped dirty-only catalog refresh uses selected records plus
  existing catalog fallback, avoiding a full live session-index scan after each
  bounded shard tick. This gives operators an automatic route for “repair the
  few stale sessions in this shard” without rematerializing the whole month or
  masking live-tail catch-up.
- `maintenance-status` surfaces actionable search-shard tails in the agent
  packet: `next_actions` can include `refresh_search_shard_structured` beside
  graph/live-tail repair, while `agent_route.search_shard_next_action` carries
  the selected shard and counts for compact MCP consumers. Existing stale shard
  DBs route to `search-shards --no-rebuild --dirty-only`; missing DBs route to a
  scoped structured rebuild only after the shard lane is already partially
  materialized, never to implicit `--full-text`.
  2026-06-27 live proof: `month/2026-06` dirty-only repaired `7` stale
  sessions, processed `243997` structured documents in `270581ms`, and left
  `search_shards.status=current`; the slowest session contributed `146325`
  documents and took `170372ms`, making large per-session document fan-out the
  visible bottleneck.
  2026-06-29 live proof: a bounded `month/2026-06` dirty-only tick selected
  the stale Gmail session
  `2026-06-13__003__подключайся-к-моему-gmail-и-анализируй-все`, exposed
  `candidate_document_count=208490`, `active_phase=delete_existing_documents`,
  and `remaining_sessions[0]` for the same session; scoped catalog refresh then
  used `selected_records_with_catalog_fallback` in `134ms` instead of the prior
  full-scan tail, while the heavy session remained an explicit budget-exhausted
  follow-up.
  A follow-up cheap-first live slice selected
  `2026-06-29__001__codex-in-memories` before the Gmail heavy-tail row and
  processed it in `217ms` (`document_count=5`), reducing `month/2026-06`
  stale rows from `2` to `1`; `maintenance-status` then switched the shard
  action to `search_shard_structured_dirty_only_drip` with `dirty_drip_limit=1`.
  The final dirty-only drip then processed the remaining Gmail heavy-tail row
  `2026-06-13__003__подключайся-к-моему-gmail-и-анализируй-все` in
  `246680ms`, indexed `208490` structured documents, returned
  `budget_exhausted=false`, and moved `month/2026-06` to `status=current`.
  Follow-up graph queue catch-up and route-rollup refresh returned the archive
  to `maintenance-status ok=true`, `search_shards=current`,
  `graph.status=current_with_retired_sources`, and
  `operational_route_rollup.status=current`.
- Operations warnings distinguish current failures from repaired shard
  freshness failures: an `index-maintenance` report that failed only because a
  monthly shard had `search_documents_stale_segment_refs` is no longer kept as
  a recent problem after a newer successful `search-shards` report repairs the
  same shard. The failed report remains evidence, but `maintenance-status`
  stops treating it as an active warning.
- Graph hot-state recovery guards: `maintenance-status` detects empty
  generated graph stores (`graph_store_nodes_empty` / `graph_store_edges_empty`)
  without a full source scan, routes them to bounded incremental
  `graph-maintenance`, compares non-retired ledger sources with stored
  `graph_sources` to catch partial-store recovery
  (`graph_source_ledger_store_count_mismatch`), and uses the latest fresh
  `graph-maintenance` report's non-zero `remaining_count` as
  `latest_graph_maintenance_remaining_sources` so stale ledgers or exhausted
  queues cannot make graph search look current
- Graph deep source scans have an explicit hash-cache contract:
  `graph-maintenance --mode deep --hash-mode exact --write-hash-cache` refreshes
  `graph/source-hash-cache.json` under the shared maintenance lock, while
  read-only `--hash-mode cached` consumes stat-matched entries and reports
  `source_hash_cache` hit/miss/compute counts. 2026-06-25 live proof: exact
  cache write took `21.677s` internal / `22.59s` wall, stored `5249` unique
  file hashes, then cached deep took `5.166s` internal / `6.06s` wall with
  `persistent_hit=14753`, `computed=0`, `remaining_count=0`. Regression proof:
  `test_graph_source_hash_cache_reuses_stat_matched_hashes_and_exact_bypasses`.
- Optional search provider gates: `config/search-providers.json`,
  `search-provider-status`, local embedding semantic context, and local
  reranker ordering metadata
- Retrieval packets: `retrieve` / `retrieval-packet` recipes over search,
  phase-discovery, continuation signals, and raw refs
- Hook docs and generated example: `hooks/`
- Schemas: `schemas/`
- Skills: `skills/`, including the user-level router
  `aoa-session-memory-global-route` and narrow operation skills for stress,
  historical import, audit, doctor, hook trust, compact probe work, and the
  consumer `aoa-session-memory-evidence-route` for prior-session entity usage,
  consequence, graph, and raw-ref evidence routing
- Mass naming route: `naming-wave build/apply/audit` and
  `skills/aoa-session-naming-wave`
- CLI and hooks: `scripts/aoa_session_memory.py`
- Tests: `tests/test_session_memory.py`
- Standalone repository: `https://github.com/8Dionysus/aoa-session-memory`
- Local standalone mirror: `/srv/AbyssOS/bundles/aoa-session-memory`

## Current Green Gates

Run from the bundle root, replacing `/path/to/workspace` and
`/path/to/workspace/.aoa` with the active install roots:

```bash
python3 -m py_compile scripts/aoa_session_memory.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_session_memory.py
python3 scripts/aoa_session_memory.py codex-grounding --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py codex-hooks-status --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py install-user-skill --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py install-user-skill --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --skill aoa-session-memory-evidence-route
python3 scripts/aoa_session_memory.py import-codex-sessions --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --since-days 21 --dry-run --write-report
python3 scripts/aoa_session_memory.py sweep-codex-sessions --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --since-days 7 --min-age-sec 60 --dry-run --write-report
python3 scripts/aoa_session_memory.py reindex-sessions all --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --max-raw-mb 16 --write-report
python3 scripts/aoa_session_memory.py index-maintenance all --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --apply --token-max-raw-mb 512 --write-report
python3 scripts/aoa_session_memory.py search-index all --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --write-report
python3 scripts/aoa_session_memory.py search-provider-status --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --include-host --write-report
python3 scripts/aoa_session_memory.py search --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --query "hook timed out" --explain
python3 scripts/aoa_session_memory.py search --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --query "hook timed out" --doc-type event --query-timeout-ms 1000 --explain
python3 scripts/aoa_session_memory.py agent-responses --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --session latest --limit 20
python3 scripts/aoa_session_memory.py agent-responses --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --query "hook timed out" --agent-event assistant_answer --query-timeout-ms 1000 --limit 1 --explain
python3 scripts/aoa_session_memory.py agent-closeouts --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --session latest --limit 20
python3 scripts/aoa_session_memory.py agent-progress-updates --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --session latest --limit 20
python3 scripts/aoa_session_memory.py agent-reasoning-windows --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --session latest --limit 10
python3 scripts/aoa_session_memory.py task-episodes latest --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --limit 20 --order recent
python3 scripts/aoa_session_memory.py answer-neighborhood --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --session latest --limit 10
python3 scripts/aoa_session_memory.py agent-event-audit all --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --order longest --min-events 1000 --limit 5 --probe-routes --write-report
python3 scripts/aoa_session_memory.py trace-route aoa-memo-writeback --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --write-report
python3 scripts/aoa_session_memory.py search --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --query "hook timeout route" --include-semantic-context --rerank-local --allow-host-warnings --host-timeout 120 --explain
python3 scripts/aoa_session_memory.py atlas build all --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --write-report
python3 scripts/aoa_session_memory.py graph-build all --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --write --force-large-export
python3 scripts/aoa_session_memory.py graph-maintenance all --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --apply --batch-limit 3 --write-report --write-hash-cache
python3 scripts/aoa_session_memory.py graphrag-packet --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --query "aoa-session-memory-mcp" --anchor aoa-session-memory-mcp
python3 scripts/aoa_session_memory.py graph-explain-packet "debug aoa-session-memory-mcp" --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --anchor aoa-session-memory-mcp
python3 scripts/aoa_session_memory.py graph-eval --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py graph-quality-audit --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --write-report
python3 scripts/aoa_session_memory.py graph-quality-review /path/to/workspace/.aoa/diagnostics/<stamp>__graph-quality-audit.json --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --verdict mcp_access_plane=accept:accept:"good MCP evidence route" --write-report
python3 scripts/aoa_session_memory.py graph-quality-corpus check --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --write-report
python3 scripts/aoa_session_memory.py graph-freshness-check --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --write-report
python3 scripts/aoa_session_memory.py graph-freshness-check --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --stable --quiet-seconds 120 --write-report
python3 scripts/aoa_session_memory.py entity-dossier aoa-session-memory-mcp --kind mcp --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --write-report
python3 scripts/aoa_session_memory.py storage-audit --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --write-report
python3 scripts/aoa_session_memory.py route-readiness all --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --write-report
python3 scripts/aoa_session_memory.py route-sample-audit all --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --sample-limit 1 --write-report
python3 scripts/aoa_session_memory.py route-sample-review /path/to/workspace/.aoa/diagnostics/<stamp>__route-sample-audit.json --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --write-report
python3 scripts/aoa_session_memory.py retrieve continue-techniques-session --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --query "aoa-techniques continuation" --write-report
python3 scripts/aoa_session_memory.py batch-distill --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --since-days 21 --write-report
python3 scripts/aoa_session_memory.py naming-readiness all --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --refresh-indexes --write-report
python3 scripts/aoa_session_memory.py validate --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py codex-compact-probe --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --trust-hooks
python3 scripts/aoa_session_memory.py stress-pass latest --aoa-root /path/to/workspace/.aoa --compactions 100 --write
python3 scripts/aoa_session_memory.py doctor --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --check-live-hooks --check-user-skill --check-codex-grounding
python3 scripts/aoa_session_memory.py audit --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py audit --workspace-root /path/to/workspace --aoa-root /path/to/aoa-session-memory --portable-bundle
```

Last observed result:

- `.aoa` tests: `211 passed` on 2026-06-21
- `codex-grounding`: `ok=true`, `codex-cli 0.133.0`, compact ratio `0.8`
- `codex-hooks-status`: `ok=true`, all required native hooks present,
  matching, and trusted
- `install-user-skill`: `ok=true`, user-level router points to the active
  `.aoa` install
- `import-codex-sessions --since 2026-04-21 --write-report`: `ok=true`,
  discovered `142` transcripts, imported `133`, skipped `9` already indexed
  sessions; reports:
  `diagnostics/20260512T172827Z__codex-session-import.json` and `.md`
- `reindex-sessions all --write-report`: `ok=true`, selected `143`
  sessions, reindexed `142`, skipped `1` `raw_unavailable` diagnostic
  archive; reports:
  `diagnostics/20260512T210121Z__reindex-sessions.json` and `.md`
- `batch-distill --since 2026-04-21 --write-report`: `ok=true`, selected
  `143` sessions, planned `139`, skipped `3` already first-pass distilled,
  diagnostic `1`; lanes: `auto_first_pass=142`, `manual_review=129`,
  `manual_review_deep=17`, `manual_review_standard=33`,
  `manual_review_sample=79`, `mechanics_candidate=119`,
  `low_risk_indexed=13`, `diagnostic=1`; reports:
  `diagnostics/20260512T210131Z__batch-distill__first-wave.json` and `.md`
- Universal event index proof: segment indexes now carry `family`, `phase`,
  `actor`, `action`, `object`, `outcome`, `correlation_id`, and sequence or
  call/output `relationships`; the current classifier avoids tagging
  `session_meta` from non-semantic raw JSON fields, avoids promoting stream
  message duplicates, uses structured command status, and separates security
  policy/check mentions and sensitive touchpoints from actual risk signals.
- Portable search proof: `search-index all --write-report` built
  `559524` runtime documents across `161` sessions with no diagnostics; report:
  `diagnostics/20260517T161336Z__search-index.json` and `.md`. Control
  searches returned fresh refs for hook timeout signals, naming/techniques
  complaints, raw-unavailable incidents, commit/push/merge delivery requests,
  and `aoa-techniques` sessions. The generated SQLite DB under `search/` is a
  runtime route cache, not portable source.
- Route-layer readiness proof: the route-signal classifier is versioned
  separately from the route schema (`route_signal_classifier_version=7`), so
  stale route tags cannot silently masquerade as current classification.
  `reindex-sessions all --stale-route-indexes --max-raw-mb 1300
  --write-report` refreshed `157` current-indexable sessions and left `23`
  `raw_unavailable` diagnostic archives as non-indexable evidence rather than
  route-index failures. `atlas build all --write-report` built `36` axes and
  `27820` generated route entries. `search-index all --max-raw-mb 16
  --write-report` built `875817` runtime documents across `180` sessions,
  `1393` segments, and `874142` events with no diagnostics.
  `route-readiness all --write-report` returned `ok=true` and
  `covered_requirement_count=22/22`: `157` route indexes are current,
  `stale_route_classifier=0`, and the portable SQLite provider is ready.
  `route-sample-audit all --sample-limit 2 --max-raw-chars 420
  --write-report` generated `52` samples across all `26` required route
  layers with `stale_route_index_count=0`; `route-sample-review` accepted
  `52/52` with `open_count=0`. Version 7 folds the earlier calibration fixes
  into regression tests: failed command/test output no longer becomes
  `green_proof` or `tests_green`, successful source/doc reads that mention
  `exit code N` no longer become failures, casual hook discussion no longer
  creates lifecycle `hook_health`, and the path graph filters `/dev/null` plus
  git remote refs/ranges. Reports:
  `diagnostics/20260524T131717Z__reindex-sessions.json`,
  `diagnostics/20260524T132026Z__agent-atlas.json`,
  `diagnostics/20260524T132613Z__search-index.json`,
  `diagnostics/20260524T132758Z__route-layer-readiness.json`,
  `diagnostics/20260524T132804Z__route-sample-audit.json`, and
  `diagnostics/20260524T132909Z__route-sample-review.json`.
- Index-maintenance proof: `index-maintenance all --apply --write-report`
  detected source-newer-than-search and source-newer-than-atlas drift after
  the live session count moved to `181`, then applied `3` actions:
  rebuilt portable search to `880562` documents across `181` sessions,
  `1405` segments, `878870` events, and `106` incidents; rebuilt the atlas to
  `36` axes and `27833` entries; and reran `route-readiness` with `ok=true`
  and `covered_requirement_count=22/22`. The current route-index gate reports
  `157` current indexable sessions, `24` diagnostic non-indexable sessions,
  and `stale_route_classifier=0`. Reports:
  `diagnostics/20260524T144637Z__index-maintenance.json`,
  `diagnostics/20260524T144257Z__search-index.json`,
  `diagnostics/20260524T144612Z__agent-atlas.json`, and
  `diagnostics/20260524T144637Z__route-layer-readiness.json`.
- Latest route-maintenance proof: classifier version
  `route_signal_classifier_version=10` keeps canonical AoA skill/MCP names as
  evidence-derived route anchors rather than a hand-authored project registry.
  It recognizes `aoa-*` / `aoa_*` names, `skills/<name>/SKILL.md` paths, and
  MCP services such as `mcp/services/<name>` or `*-mcp` across both
  `by-entity` and `by-mcp` where applicable. `index-maintenance all --apply
  --write-report --max-raw-mb 1300` selected `197` sessions, refreshed `163`
  stale route indexes, rebuilt portable search to `930099` documents, rebuilt
  the atlas to `36` axes and `29771` entries, and reran `route-readiness`
  with `ok=true`, `covered_requirement_count=22/22`, and
  `stale_route_classifier=0`. Target probes confirmed
  `entity:aoa_memo_writeback` in `maps/by-entity` and
  `entity:aoa_memo_mcp` plus `mcp:aoa_memo_mcp` across search and maps, while
  derivative labels such as `mcp:aoa_memo_mcp_under_stack_mcp` no longer route
  as MCP services. Reports:
  `diagnostics/20260526T031416Z__reindex-sessions.json`,
  `diagnostics/20260526T033506Z__search-index.json`,
  `diagnostics/20260526T033900Z__agent-atlas.json`,
  `diagnostics/20260526T033920Z__route-layer-readiness.json`, and
  `diagnostics/20260526T033920Z__index-maintenance.json`.
- Route-trace resolver proof: `trace-route` resolves operational anchors into
  route candidates and evidence hits without adding a hand-authored registry.
  Live probes on 2026-05-26 returned `ok=true`, `result_count=8`, and written
  JSON/Markdown reports for `aoa-memo-writeback`, `aoa-memo-mcp`,
  `PreCompact`, `exec_command`, and `GitHub`. Reports:
  `diagnostics/20260526T043625Z__route-trace__aoa-memo-writeback.json`,
  `diagnostics/20260526T043629Z__route-trace__aoa-memo-mcp.json`,
  `diagnostics/20260526T043628Z__route-trace__precompact.json`,
  `diagnostics/20260526T043631Z__route-trace__exec-command.json`, and
  `diagnostics/20260526T043629Z__route-trace__github.json`. Live proof on
  2026-06-21: `trace-route aoa-session-memory-mcp --kind mcp --limit 5
  --per-route-limit 10` returned in `0.87s` with `ok=true`,
  `result_count=5`, `route_hit_count_before_text_fallback=13`,
  `text_search_skipped=true`, and no diagnostics; the same route previously
  spent about `9.3s` in raw text fallback and returned timeout diagnostics
  despite valid typed route hits.
- Graph quality proof: `graph-quality-audit --limit 3 --sample-ref-limit 1
  --write-report` sampled `9` stable operational anchors across MCPs, skills,
  hooks, tools, and path routes. It returned `ok=true`,
  `ready_for_manual_verdict_count=9/9`, no quality flags, raw and segment refs
  for every sample, and `bounded_current` freshness. Report:
  `diagnostics/20260526T144640Z__graph-quality-audit.json`.
- Graph quality review proof: `graph-quality-review` over the 2026-05-26
  audit accepted `mcp_access_plane` and marked `memo_writeback_skill` as
  `weak` with `expand_anchor_set` feedback. It returned `ok=true`,
  `reviewed_count=2`, `open_count=7`, `quality_feedback_count=1`, and
  `regression_candidate_count=2`; it wrote only diagnostics and did not mutate
  indexes or raw evidence. Report:
  `diagnostics/20260526T150119Z__graph-quality-review.json`.
- Pre-GraphRAG trust proof: expanded `graph-quality-audit` sampled `21`
  anchors across MCP, skill, hook, tool, goal, failure, decision, and path
  routes. `20/21` were ready for manual verdict; the stack MCP path control
  had no evidence refs and was correctly rejected in review. The review
  returned `reviewed_count=21`, `open_count=0`, verdict counts
  `accept=13`, `weak=6`, `wrong_anchor=1`, `reject=1`, and
  `regression_candidate_count=21`. A follow-up stale-control review over a
  fresh 21-anchor audit marked `mcp_access_plane` as `stale` because
  `graph-freshness-check` reported `source_newer_than_graph_sidecar`; bounded
  refs stayed usable, but full sidecar synthesis is blocked until rebuild. The
  source-owned regression corpus at `config/graph-quality-regression-corpus.json`
  covers positive, weak, negative, stale, and wrong-anchor controls;
  `graph-quality-corpus check` returned `ok=true`, `case_count=5`,
  `passed_count=5`, and `skipped_count=2` for fixture-required
  stale/wrong-anchor controls. An
  `entity-dossier aoa-session-memory-mcp --kind mcp` report returned
  `ok=true` with strong raw/segment/session refs and related MCP/path routes.
  `graph-freshness-check` correctly reported refs alive while distinguishing
  map/search drift, graph drift, and offline graph-build need. The full live
  `graph-build all --write --force-large-export` now succeeds through the
  SQLite accumulator path: `198` sessions, `2055446` nodes, `10280862` edges,
  `graph/nodes.jsonl` about `3.8 GB`, `graph/edges.jsonl` about `11.4 GB`,
  elapsed `41:07`, and peak RSS about `700 MB`. Follow-up
  `index-maintenance all --apply` refreshed search to `961944` documents,
  atlas to `29867` entries, and route-readiness to `22/22`. On the live
  archive, later gates may still report `source_newer_than_*` when active
  session indexes move after the rebuild; that is treated as live-churn
  telemetry, not as permission to synthesize without refs. Reports:
  `diagnostics/20260526T153341Z__graph-quality-audit.json`,
  `diagnostics/20260526T153404Z__graph-quality-review.json`,
  `diagnostics/20260526T155941Z__graph-quality-corpus-check.json`,
  `diagnostics/20260526T153442Z__entity-dossier__aoa_session_memory_mcp.json`,
  `diagnostics/20260526T155843Z__graph-freshness-gates.json`,
  `diagnostics/20260526T154418Z__index-maintenance.json`,
  `diagnostics/20260526T171244Z__graph-freshness-gates.json`,
  `diagnostics/20260526T171518Z__graph-freshness-gates.json`,
  `diagnostics/20260526T172359Z__graph-quality-audit.json`, and
  `diagnostics/20260526T172446Z__graph-quality-review.json`.
- Incremental graph-maintenance proof: `graph/graph.sqlite3` is now the live
  graph store, with per-session/per-segment graph sources, source hashes,
  node/edge contributions, and aggregate nodes/edges. `graph-maintenance`
  detects clean, dirty, missing, blocked, and orphaned sources, replaces dirty
  source contributions transactionally, and treats `nodes.jsonl` /
  `edges.jsonl` as optional export snapshots. `graph-prune-sidecar` can remove
  those generated snapshots while keeping `graph.sqlite3` as the live graph
  store. Full forced rebuilds stream contributions into the store and may
  reclaim old generated sidecars before fresh export. `graph-freshness-check`
  now distinguishes graph store freshness, optional sidecar snapshot state,
  sidecar export/prune need, graph maintenance need, and full offline rebuild
  need.
- 2026-06-11 large live graph proof: full store-only in-place
  `graph-build all --write --store-only --in-place --progress-every 10`
  rebuilt the live graph store across `258` session records, `3865` graph
  sources, `3048448` aggregate nodes, and `18807612` aggregate edges in
  `33:26`, with `sidecar_exported=false` and peak RSS about `2.6 GB`. A
  follow-up active-session repair showed the old maintenance loop was
  reparsing one large session once per dirty source; grouped maintenance now
  repairs selected sources by session and streamed-refreshes touched aggregates
  in explicit chunks.
  The real follow-up repair selected `150` live dirty/missing sources across
  `2` groups, refreshed `88168` nodes and `457254` edges in `251.58s`, then
  targeted `index-maintenance` refreshed the active session search projection
  from `2615` to `4026` docs, updated `343` atlas entries, removed `678`
  stale atlas artifacts, returned route-readiness `23/23`, and repaired `32`
  graph sources. Final maintenance dry-check returned `dirty=0`, `missing=0`,
  `orphaned=0`, `clean=3817`, and `blocked=55`; freshness refs were `alive`
  with `broken_count=0`. The sidecar state remains intentionally
  `not_exported` for the live archive.
- 2026-06-11 chunked graph-maintenance proof: targeted live
  `graph-maintenance 019eb82b-96a2-7fb1-a918-d29aa9c57507 --apply
  --batch-limit 3 --refresh-chunk-size 16 --write-report` updated `3`
  sources in one replacement group, refreshed `609` aggregate nodes and
  `1908` aggregate edges, and reported streamed refresh stats of `39`
  node chunks, `120` edge chunks, `291978` node contribution rows, and `1908`
  edge contribution rows. A second targeted pass reported the selected
  session clean with `dirty=0`, `missing=0`, and `remaining_count=0`.
- 2026-06-12 cost-aware graph-maintenance proof: incremental maintenance now
  plans exact old-plus-new aggregate node/edge refresh cost, sorts actionable
  sources cheap-first, reports individually oversized sources under
  `oversized_sources`, and keeps current-pass budget overflow under
  `budget_deferred_sources`. Regression coverage includes the case where a
  heavy first dirty source is skipped while a later cheap source is applied.
  Source `.aoa` and the standalone bundle passed py_compile, `107` pytest
  tests, `validate`, and `doctor`; the standalone portable audit also passed.
- 2026-06-13 agent-event/task-episode live proof: generated session indexes
  are current across `206` indexed live sessions with `6687` generated task
  episodes, `56347` assistant answers, and `147269` reasoning-boundary events
  in session indexes. Portable SQLite was refreshed to `1443382` documents,
  including `6698` `task_episode` docs and `496415` docs carrying
  `task_episode_id`; provider status is `ready`, route-readiness diagnostics
  are `0`, and atlas build produced `74860` entries across `52` axes.
  Live CLI/MCP probes on
  `2026-06-04__003__у-нас-в-отрефакторенных-репо-есть-определенным` returned
  fresh refs for agent responses, closeouts, progress updates, reasoning
  windows, answer neighborhoods, and task episodes. Graph maintenance remains
  a bounded blocker for this layer: `graph-maintenance all --apply
  --batch-limit 50 --refresh-chunk-size 250 --max-refresh-nodes 50000
  --max-refresh-edges 100000` was stopped after RSS grew past `9.9 GiB`; the
  read-only follow-up reported `remaining_count=3941` dirty graph sources in
  `diagnostics/20260613T043359Z__graph-maintenance.json`. Treat graph
  freshness as deferred until graph refresh memory profile is tightened.
- 2026-06-13 hot route-cache proof: on
  `2026-06-04__003__у-нас-в-отрефакторенных-репо-есть-определенным`, full hot
  maintenance with graph freshness had measured `elapsed=217.52s`. After
  splitting hot route-cache freshness from graph freshness, excluding rendered
  Markdown from search projection fingerprints, and adding
  `refresh_search_projection_state`, `index-maintenance --skip-graph-repair`
  returned current search/atlas with graph `deferred_not_checked` in
  `elapsed=7.36s`, and `auto-maintenance hot` completed in `elapsed=9.79s`.
  Reports:
  `diagnostics/20260613T221851Z__index-maintenance.json`,
  `diagnostics/20260613T222212Z__route-cache-freshness-gates.json`,
  `diagnostics/20260613T222218Z__index-maintenance.json`, and
  `diagnostics/20260613T222219Z__auto-maintenance-hot.json`.
- 2026-06-14 hot graph tick proof: `auto-maintenance hot latest --apply
  --budget-seconds 120` now repairs graph in the hot profile while allowing a
  deferred graph remainder. The live run selected `3` graph sources with
  `candidate_pool_limit=9`, completed graph maintenance in `elapsed_ms=63570`,
  reduced missing graph sources from `16` to `13`, and kept route-cache
  freshness green with `status=applied_with_deferred_graph`. Report:
  `diagnostics/20260614T022956Z__auto-maintenance-hot.json`.
- 2026-06-14 queued graph-continuation proof: a live
  `auto-maintenance hot latest --apply --budget-seconds 1` created/upserted a
  bounded `graph_maintenance` job with `batch_limit=3`,
  `candidate_pool_limit=9`, graph guards `20000` nodes / `60000` edges, and a
  separate `120s` graph-job budget instead of inheriting the exhausted
  foreground budget. `hook-worker --limit 1` then processed that pending job,
  selected `3` graph sources, completed in `elapsed_ms=48840` with
  `budget_exhausted=false`, and left `route-readiness latest` green at `23/23`
  while graph freshness honestly reported the remaining deferred graph sources
  (`dirty=183`, `missing=6`, `clean=6`). Reports:
  `diagnostics/20260614T025525Z__auto-maintenance-hot.json` and
  `diagnostics/20260614T025625Z__graph-maintenance.json`.
- 2026-06-14 graph/search live-maintenance proof: incremental search writes use
  WAL while full rebuilds clean SQLite sidecars before atomic replacement, so
  `agent-responses` and `search` stay readable during maintenance instead of
  returning `sqlite_locked`. Source and portable bundle tests both passed
  `135` pytest cases, `validate`, and portable audit. Stable freshness showed
  map/search can be current on the quiescent subset while live sessions are
  explicitly deferred; graph remains the bounded heavy lane with thousands of
  dirty sources and must not be hidden behind search/MCP readiness. A bounded
  graph-maintenance batch updated `3` missing sources in `76.226s`, growing the
  graph store to `3165723` nodes and `19490742` edges while leaving `4077`
  dirty, `21` missing, and `61` blocked sources. Current storage snapshot is
  `.aoa=112.4 GiB`, `graph=66.2 GiB`, `sessions=30.5 GiB`, `search=15.1 GiB`.
  `storage-audit --deep-dbstat --row-counts` is a heavy offline profile for this
  graph size; use the normal storage snapshot for interactive gates. Unfiltered
  graph-maintenance reports now keep matched source evidence bounded as
  `matched_source_key_count` plus `matched_source_key_sample`, preserving full
  `matched_source_keys` only for explicit `--source-key` probes.
- 2026-06-14 graph-drift route diagnosis proof: graph source state now exposes
  bounded raw reason counts, normalized reason groups, examples, and a
  maintenance recommendation. A live dry exact-cost plan
  (`graph-maintenance all --plan-refresh-costs --batch-limit 1
  --max-refresh-nodes 20000 --max-refresh-edges 60000 --write-report`) finished
  without mutating `graph.sqlite3` in `20.518s`, reported
  `source_sha_mismatch=4079`, `route_signal_classifier_mismatch=3892`,
  `missing_graph_source_path=61`, `graph_source_missing=20`, selected a
  `3` node / `3` edge source for a bounded incremental pass, and correctly
  recommended the store-only in-place rebuild route for mass classifier drift.
  Report: `diagnostics/20260614T102133Z__graph-maintenance.json`.
- 2026-06-14 bounded catch-up proof: a full dry maintenance scan found
  classifier/projection drift across the archive, with `261` dirty search
  sessions before the first foreground repair and `209` dirty search sessions
  still remaining after a budgeted medium run. `auto-maintenance catchup
  --repair-limit 3` planned a bounded follow-up with
  `search_reindex_candidate_count=209`, `search_reindex_session_count=3`,
  `search_repair_remaining_count=206`, `atlas_dirty_session_count=261`,
  `atlas_repair_session_count=3`, and both repair-limited flags set. Source
  `doctor` and standalone bundle validation pass; live `audit` remains
  honestly blocked on `portable_sqlite:stale` until the catch-up batches
  finish.
- 2026-06-14 host catch-up timer proof: user systemd now has
  `aoa-session-memory-catchup-maintenance.timer` and service. The service runs
  through `abyss-machine resource launch --class medium --kind indexing
  --unattended --force` with medium MemoryHigh/MemoryMax, `--repair-limit 3`,
  and `--budget-seconds 900`. A live manual start finished with systemd
  `status=0/SUCCESS` in `5min 18s`, peak memory `987.8 MiB`, and wrote
  `diagnostics/20260614T044241Z__auto-maintenance-catchup.json` with
  `ok=true`, `status=applied_with_remaining_backlog`,
  `expected_catchup_remaining=true`, search dirty `206 -> 203`, and atlas
  repair `3` selected / `255` remaining. `search-provider-status` still reports
  `portable_sqlite:stale` with `dirty_session_count=203`, so the timer is
  working as a bounded queue rather than pretending the archive is complete.
- 2026-06-21 resource-gate visibility proof: `auto-maintenance-resource` now
  wraps timer maintenance launches and records
  `diagnostics/*__auto-maintenance-resource-<profile>.json` when
  `abyss-machine resource launch --success-on-block` blocks before the inner
  `auto-maintenance` child starts. A live backlog smoke with `--limit 0` wrote
  `20260621T233243Z__auto-maintenance-resource-backlog.json` with
  `status=resource_blocked`, `ok=false`, and
  `blocked_reasons=[indexing_unattended_swap_used_pressure]`; `maintenance-status`
  now surfaces that report under `latest_reports.auto_maintenance_resource` and
  `operations.recent_problem_jobs`. Backlog and deep profiles now enable
  graph-drip fallback by profile default, so a blocked medium/heavy run can
  still run a capped probe-class graph-maintenance batch and expose it as
  `fallback_graph_drip` without marking the full backlog/deep profile as
  successful. The fallback now takes batch, budget, candidate-pool window, and
  node/edge caps from profile graph-drip settings unless explicitly overridden.
  Those defaults are intentionally small (`25` sources, `300s`,
  `25` candidate-pool window) so resource-blocked backlog/deep launches make
  bounded progress without spending the fallback window on a wide exact-planning
  pool. It mutates only when the outer resource route is called with `--apply`;
  dry resource probes preserve the raw blocked state.
- 2026-06-14 search read-availability proof: a live hot maintenance run opened
  a long rollback-journal write window on `search/aoa-search.sqlite3`; during
  that window both `agent-responses` and `search` returned
  `sqlite_locked`. Incremental search writers now use SQLite WAL, full rebuilds
  remove stale sidecars before atomic replacement, and regression coverage
  holds an uncommitted writer while `search-provider-status`, `search`, and
  `agent_event` routes keep returning ready results from the last committed
  snapshot. Live proof repeated the scenario with a held WAL writer and during
  real `index-maintenance --repair-limit 2 --skip-graph-repair`; read routes
  stayed `ok=true`. Source and standalone bundle passed py_compile, `135`
  pytest tests, `validate`, and portable audit.
- 2026-06-15 raw-unavailable retirement and hot/deep proof: the historical
  `63` `raw_unavailable` / `missing_graph_source_path` graph sources were
  audited against live `.aoa`, Codex sessions, `/abyss` vault roots, hooks, and
  logs. The recovery report classified `48` as `memory_writer`, `14` as
  `title_helper`, and `1` as `hook_partial`; all `63` now have explicit
  retired/tombstoned ledger state instead of actionable blocked backlog.
  Latest stable graph freshness report
  `diagnostics/20260615T165551Z__graph-freshness-gates.json` returned
  `ok=true`, `checked_count=265`, `deferred_live_session_count=8`,
  search/atlas `current`, graph `current_with_retired_sources`, refs alive,
  and graph source state `dirty=0`, `missing=0`, `blocked=0`,
  `retired=63`. The hot route-cache gate
  `diagnostics/20260615T165124Z__route-cache-freshness-gates.json` returned
  `ok=true` with `truth_status=hot_route_cache_cached_state_no_source_scan`;
  queue-empty `graph-maintenance --use-queue` returned `mutates=false` and
  `selection_strategy=queue_empty_no_source_scan`.
- 2026-06-15 live-deferred provider/MCP proof: `search-provider-status` now
  separates actionable projection drift from active Codex transcript churn. A
  live install can report `ready_with_deferred_live_updates` /
  `current_with_deferred_live_updates` with `actionable_dirty_session_count=0`
  while keeping dirty/deferred session samples visible. Completion `audit`
  passed with provider covered, `actionable=0`, and `deferred=6`; segment
  topology mismatches from a fresh live transcript are deferred as
  `recent_live_codex_transcript_not_yet_resegmented` instead of being treated
  as stable corruption. Source-local MCP smokes: default status `0.06s`,
  include-live status `19.89s`, entity inventory `1.43s`, graph neighborhood
  `1.53s`, GraphRAG packet `4.92s`, usage audit `27.95s`.
- 2026-06-21 entity usage MCP fast-path proof: a live
  `entity_usage_audit` for `aoa_session_memory_mcp` dropped from
  `elapsed_ms=16527.43` to `elapsed_ms=742.78` after disabling per-hit semantic
  previews in this route and skipping broad text fallback when typed route hits
  already include direct usage. A randomized live scenario audit across skill,
  MCP, hook health, tool, goal, and API samples returned `6/6` passed with raw
  previews available for proof windows in
  `diagnostics/20260621T015349Z__entity-usage-scenario-audit__codex_goal_fastpath_20260621.json`.
- 2026-06-21 usage-scenario audit hygiene proof: the randomized live scenario
  default now samples operational agent routes (`skill`, `mcp`, `tool`, `api`,
  `hook_health`, `goal`, `agent_event`) from event-scoped route postings,
  filters generated/runtime keys such as `__pycache__`, and treats
  hook/agent-event evidence by layer semantics instead of requiring fake direct
  usage. The regression seed `20260621` returned `8/8` passed, `0` warnings,
  `0` failures, raw previews available for all samples, `elapsed_ms=6353`, and
  slowest sample `api:graphql` at `843ms` in
  `diagnostics/20260621T124512Z__entity-usage-scenario-audit__20260621.json`.
- 2026-06-25 usage-scenario candidate-pool proof after search schema 13:
  the randomized live scenario seed `live-goal-continuation-20260625` returned
  `8/8` passed with `0` failures and raw previews available. The candidate
  pool now stages cheap route posting counts before indexed
  `usage/result/outcome` event buckets, cutting the observed run from about
  `36.5s` to `5.6s`; the report exposes
  `candidate_selection_elapsed_ms=3094`, `sample_total_elapsed_ms=2520`, and
  lives at
  `diagnostics/20260625T102340Z__entity-usage-scenario-audit__live_goal_continuation_20260625.json`.
- 2026-06-25 compact MCP/CLI provider proof: `goal-lifecycles all --limit 1`
  and `entity-usage-scenario-audit --sample-size 1 --seed
  live-provider-summary-smoke` both return a bounded `provider` summary with
  `portable_sqlite` ready, search schema `13`, route-index presence, and
  `freshness.status=current`; compact scenario output no longer drops provider
  freshness before MCP sees it.
- 2026-06-30 goal work-chain route proof: live
  `goal-lifecycles all --event-kind goal_completed --limit 1` returns
  `work_chain.status=linked_task_episodes` with `linked_episode_count=1`,
  `goal_event_ref.raw_ref=raw:line:28113`, canonical
  `answer_ref.raw_ref=raw:line:27276`, and next routes for `task-episodes`,
  `answer-neighborhood`, and `agent-reasoning-windows`. Its cost profile keeps
  `reads_session_index=true`, `uses_search=false`, `uses_graph=false`,
  `opens_raw=false`, and `hydrates_body=false`, so goal-to-work navigation is a
  compact bridge rather than a hidden raw/search expansion. The focused live
  scenario report `diagnostics/20260630T043402Z__live-scenario-audit.json`
  passed with `work_chain_linked_count=3`, `work_chain_episode_count=7`,
  `work_chain_answer_ref_count=18`, `elapsed_ms=210`, and no actionable gaps.
  The reviewed live scenario corpus report
  `diagnostics/20260630T043434Z__live-scenario-corpus-check.json` passed
  `14/14` cases with `actionable_gap_count=0`.
- 2026-06-26 entity usage compact-harvest proof: a live
  `aoa_session_entity_usage_audit` MCP call for
  `aoa-session-memory-evidence-route` with `limit=2` /
  `per_route_limit=2` now keeps the returned packet compact while using the
  bounded route harvest internally. The MCP packet returned in about `1.9s`
  with `usage_role_fast_path_fetch_limit=12`,
  `candidate_usage_event_count=12`, `freshness_counts={"fresh": 3}`,
  `stale_event_count=0`, and `consequence_present=true`, so a tiny
  presentation limit no longer forces a tiny usage candidate pool. A follow-up
  randomized live scenario with seed `compact-harvest-20260626` returned
  `3/3` passed, `0` warnings, `0` failures, evidence mode
  `usage_with_consequence` for all samples, `freshness_counts={"fresh": 13}`,
  raw previews available for proof windows, and report
  `diagnostics/20260626T215221Z__entity-usage-scenario-audit__compact_harvest_20260626.json`.
- 2026-06-21 structured agent-route proof: broad
  `agent-responses --limit 10 --explain` initially exceeded `90s` and had to be
  killed because the default SQL ordered by a computed stream-copy rank and
  missed the existing date index. The no-query route now avoids that computed
  order, uses the lightweight profile (`uses_fts=false`,
  `hydrates_body=false`, `semantic_preview=false`), and the same live route
  returned `10` results in `0.41s`. After shard fan-out integration,
  `agent-responses --use-shards --agent-event assistant_answer --limit 10
  --explain` returned `10` results in `0.46s` with
  `search_projection.mode=materialized_shard_fanout`, `queried_shard_count=3`,
  `uses_shards=true`, and raw/segment/session refs; MCP CLI
  `agent-responses --session latest --limit 5` returned in `0.13s` through the
  local SQLite fast path and exposes an archive shard expansion command.
- 2026-06-26 agent-event route ordering/quality proof: live
  `agent-responses --session 019e9388-dc4c-7f82-b6bf-04bea3aed7f4 --limit 5
  --explain` now orders the no-query shard fan-out by date and event position,
  returning the live tail first (`event_id=123022`, `segment_id=374`) instead
  of older same-session events. The packet exposes `quality` with
  `ordered_by=query_rank_then_session_date_then_event_position_desc`,
  `agent_event_counts={"assistant_answer": 3, "assistant_final_closeout": 1,
  "assistant_verification_report": 1}`, `freshness_counts={"stale": 5}`,
  `stale_result_present=true`, and raw/segment refs for every result; stale
  latest refs remain visible instead of being replaced by older fresh evidence.
- 2026-06-26 entity usage scenario quality proof: a fresh stdio MCP
  `aoa_session_entity_usage_scenario_audit` across typed layers (`skill`,
  `mcp`, `hook`, `tool`, `api`, `script`, `validator`, `test`, `eval`, `git`)
  with seed `typed-kinds-20260626` now surfaces actionable quality flags as
  sample warnings instead of silently passing them. The live packet returned
  `ok=true`, `10` samples, `passed_count=9`, `warn_count=1`,
  `failed_count=0`, and
  `quality_flag_counts={"direct_usage_without_consequence": 1}`; the warning
  sample was `api:http`, with `evidence_mode=usage_with_result` and
  `consequence_event_count=0`. The follow-up full live loop with seed
  `goal-live-loop-20260626` returned `6/6` profiles passed,
  `first_useful_packet_ms=395`, graph neighborhood `node_count=17` /
  `edge_count=16` / `evidence_ref_count=50`, and the literal planner selected
  `route_signal_structured_search`.
- 2026-06-27 literal planner session-id proof: the planner now exposes
  `classifications`, `fallback_plan`, and `next_expansion` on route packets,
  and exact UUID session ids route through `session_rehydrate` plus
  session-scoped structured search before global literal fallback. Live
- 2026-06-27 usage-chain/literal-planner route update: concrete operational
  entity queries now route through `entity_usage_chain` before the underlying
  `entity_usage_audit`, heavy dossier, graph, or raw-text fallback. Live
  `usage-chain aoa-session-memory-mcp --kind mcp --limit 2
  --per-route-limit 3 --consequence-window 4 --document-limit 12` returned
  `ok=true` in `1.38s`, with `usage_event_count=2`,
  `chain_with_result_or_consequence_count=2`, `noise_flag_count=0`,
  raw/segment/session refs, and `skipped_graph_rag_packet=true`. Live
  `live-scenario-audit --profile literal_planner --limit 4` returned
  `ok=true`, `failed_count=0`, `elapsed_ms=533`, with primary route counts
  including `entity_usage_chain=1`, `entity_inventory=1`,
  `route_signal_structured_search=1`, and `command_structured_search=1`.
- 2026-06-29 literal planner strategy contract: `literal-query-plan` now
  exposes `literal_route_strategy` and `literal_class_contracts` so MCP/skills
  consumers can read the query class, cheapest first route, ordered route
  sequence, fallback route, monolith position, exact-recall posture, and scoped
  full-text need without reconstructing the plan from scattered fields. Live
  checks covered command, concrete entity, broad skill inventory, exact
  session id, and the `literal_planner` scenario profile; the profile returned
  `ok=true`, `sample_count=5`, `failed_count=0`, and primary routes
  `command_structured_search`, `entity_inventory`, `entity_usage_chain`,
  `route_signal_structured_search`, and `session_rehydrate`.
- 2026-06-30 noisy literal embedded-entity precedence proof:
  `literal-query-plan 'найди как aoa-session-memory-mcp возвращал Transport
  closed'` now suppresses the broad `MCP` class diagnostic, resolves
  `route_anchor=aoa_session_memory_mcp`,
  `route_anchor_source=embedded_entity_registry`,
  `route_anchor_kind=mcp`, `match_relation=embedded`, and keeps
  `entity_usage_chain` as the first route with monolith fallback not first.
  Control query `найди все MCP которые агент использовал и ошибки рядом`
  remains a broad `entity_class` inventory route. The live scenario corpus
  returned `ok=true`, `case_count=14`, `passed_count=14`, `failed_count=0`,
  and `actionable_gap_count=0`.
- 2026-06-29 scoped full-text literal strategy proof: the planner now nests
  `scoped_full_text_strategy` inside `literal_route_strategy`. A live read-only
  scoped query for `hook timed out` over `2026-06-01..2026-06-30` kept
  `route_signal_structured_search` first, preserved `monolith_raw_text_fallback`
  for exact recall, and returned
  `materialize_scoped_full_text_first` with the exact
  `search-shards all --shard month/2026-06 --full-text --write-report`
  materialization command plus the scoped `search --use-shards` query to repeat
  afterward. Regression coverage also verifies a temp archive before and after
  full-text materialization: before, the plan recommends scoped materialization;
  after, the primary route becomes `scoped_shard_full_text` with no monolith
  fallback position.
- 2026-06-27 live scenario corpus gate: consumer-loop regression controls now
  live under `config/live-scenario-regression-corpus.json` and are checked by
  `live-scenario-corpus check`. The gate preserves allowed warnings as
  `actionable_gaps`, so route-quality debt remains visible even when a case
  does not fail.
- 2026-06-26 consumer MCP / graph-drip proof: live MCP registry and usage
  routes found both the new `aoa-session-memory-evidence-route` skill and the
  older `aoa-decision` skill as active generated navigation entities with
  source refs, observed usage, consequence refs, freshness, and full expansion
  commands. The live graph route correctly failed closed with
  `graph_store_stale`, `latest_graph_maintenance_remaining_sources`, and
  GraphRAG `answer_rule_gate:stale`; registry sync then refreshed the generated
  entity registry to `current`, and a bounded `graph-maintenance --apply`
  batch processed `25` graph sources without rollback. Backlog/deep
  auto-maintenance resource fallbacks use profile graph-drip defaults, and
  regression tests cover profile fallback, explicit disable, and the dry-run
  safety boundary that prevents graph mutation without outer `--apply`.
  `maintenance-status` also audits installed user timer `ExecStart` lines so a
  stale explicit graph-drip override is visible as unit drift instead of
  silently slowing automatic graph catch-up. 2026-06-28 live proof: after
  tightening both backlog/deep fallback defaults to `25` sources, `300s`, and
  `25` candidate-pool window, installed user timers were `current` with no
  explicit overrides, and
  `diagnostics/20260628T065210Z__graph-maintenance.json` processed `25`
  sources in `207.014s` with `candidate_pool_count=25`,
  `candidate_pool_limit=25`, `budget_exhausted=false`, moving archive graph
  queue from `625` to `600`.
- 2026-06-28 auto-update live proof: a real
  `auto-maintenance-resource backlog --apply` run was blocked at the medium
  resource gate by `indexing_unattended_swap_used_pressure`, then successfully
  used the profile graph-drip fallback as a probe-class job with `batch=25`,
  `candidate_pool_limit=25`, and `elapsed_ms=31.943s`; this superseded the
  earlier stale `recent_problem_jobs` lock-conflict report without deleting
  diagnostics. The subsequent targeted live-tail catch-up for
  `2026-06-12__001__на-машине-есть-раскиданный-abyss-machine` applied `4`
  search/route actions in `122.455s`, and dirty-only `search-shards` refreshed
  `month/2026-06` to `current` with `1` dirty session and `65,473` structured
  documents in `75.150s`. A follow-up graph queue drip processed another `25`
  sources in `249.255s`, moving graph queue from `600` to `575`; live scenario
  corpus check passed `4/4` with `actionable_gap_count=0`. Remaining expected
  tails: graph dirty/actionable backlog and `search_projection_combined_large`.
- 2026-06-21 search raw-lexical policy proof: live `search-provider-status`,
  `maintenance-status --full`, and `storage-audit` showed the current search
  store has no recorded bounded raw-lexical metadata and is classified as
  `unbounded_or_legacy_policy`. `search-index` now applies the `16 MiB` bounded
  raw lexical budget by default, records the policy and raw-text skip counts in
  SQLite metadata/reports, and `maintenance-status` routes legacy stores to
  `repair_search_storage_policy` instead of silently treating weight policy as
  complete. Use `--unbounded-raw-text` only for an explicit full lexical
  rebuild/benchmark.
- 2026-06-21 bounded rebuild proof: `search-index all --write-report` rebuilt
  `281` sessions and `1,630,447` documents with `raw_text_status_counts` of
  `available=166`, `not_available=69`, `skipped_raw_too_large=46`; the search
  store dropped from `18.2 GiB`/`19G` displayed to `15.0 GiB`, and
  `maintenance-status --full` returned `ok=true`,
  `storage_policy_status=bounded_policy_recorded`, and `agent_route=use_graph_search`.
  During the rebuild, a pathological inline `PRAGMA optimize` phase was found
  and removed from full rebuilds; reports now expose phase timings so future
  long rebuilds show whether they are in bulk indexing, SQLite index build, or
  entity-registry refresh.
- 2026-06-21 route-index slimming proof: read-only `dbstat` on the bounded
  search store showed `idx_document_routes_doc` duplicated the SQLite UNIQUE
  autoindex over `(doc_rowid, route_id)` while route lookup is served by
  `idx_document_routes_route`. Removing the duplicate index and tightening hot
  route preview budgets rebuilt the store to `13.3 GiB` (`14G` displayed);
  `maintenance-status --full` stayed `ok=true`, `agent_route=use_graph_search`,
  and `storage_policy_status=bounded_policy_recorded`. The remaining search
  weight is now dominated by `documents` (`5.76 GiB`) and route postings plus
  the required UNIQUE/route index (`4.82 GiB`), not raw lexical FTS.
- 2026-06-21 aggregate route-posting policy proof: read-only dbstat on the
  current search store showed `document_routes` has `100,565,488` postings,
  dominated by aggregate `task_episode` rows (`path=47,260,244`,
  `entity=22,585,781`). Search schema 10 now caps route postings for aggregate
  docs while leaving event-level postings uncapped. A no-write sample over 10
  recent indexed sessions reduced generated postings from `10,479,376` to
  `1,899,859` (`81.87%` lower), with `event` postings unchanged. A controlled
  live rebuild through `abyss-machine resource launch --class heavy --kind
  indexing` completed in `30min 16s`, processed `282` sessions and
  `1,630,446` documents, and replaced the live SQLite store with schema `10`.
  `search-provider-status` returned `ok=true`, provider `ready`, freshness
  `current`, and no diagnostics. The search store dropped from `13.3 GiB` to
  `9.3 GiB`; `document_routes` dropped from `100,565,488` to `16,872,432`
  postings. `maintenance-status --full` now reports
  `agent_route=use_graph_search`, `needs_index_maintenance=false`, and only
  the graph-size warning remains.
  The failed timer-driven catch-up before the controlled rebuild left an
  orphan `.rebuild-*` file and a stale coordinator event; cleanup plus the
  successful manual-bulk run prove that schema-level full rebuilds need a
  long/heavy maintenance lane rather than the ordinary bounded catch-up timer.
  `auto-maintenance` now enforces that route by returning
  `deferred_full_search_rebuild_to_deep` from non-`deep` profiles when search
  freshness requires a full rewrite.
- 2026-06-21 entity-registry delta-sync proof: the generated registry search
  sync no longer deletes and reinserts all `doc_type=entity_registry` rows.
  It excludes registry docs from route-term evidence to avoid projection
  self-feedback, does not carry retired snapshot signal counts as fresh
  evidence, and compares stored rows by semantic storage fingerprint. It also
  records a stable snapshot fingerprint in SQLite `meta`, so a current
  registry-only refresh can return a bounded fast no-op without a cold
  route-term scan. The one-time live catch-up replaced old rows in `76.1s`;
  after the meta catch-up, a `budget_seconds=10` no-op completed in `0.643s`
  with `skipped=true`, `3442` unchanged docs, and `0` inserted, updated, or
  removed. `maintenance-status --full` then reported `ok=true`, search
  `current`, graph `current_with_retired_sources`, entity registry `current`,
  `warning_count=0`, and no `slow_phases`.
- 2026-06-25 scoped search-index hot-path proof: after the entity-registry
  projection was current, a live
  `search-index 2026-06-20__003__codex-in-dionysus --no-rebuild` completed via
  the maintenance coordinator in `139ms`. `session_bulk_index` took `23ms`,
  `entity_registry_refresh` took `65ms` with `skipped=true` and
  `skip_reason=entity_registry_search_sync_current`, and
  `search_catalog_refresh` took `14ms` with
  `catalog_state_basis=selected_records_with_catalog_fallback`. This proves the
  scoped hot path no longer cold-refreshes the whole entity registry or rescans
  all session indexes just to refresh the catalog.
- 2026-06-25 direct entity-registry sync proof: after a route-card/docs change
  made only the generated entity registry stale, `maintenance-status --full`
  proposed `entity-registry-search-sync` instead of
  `search-index all --limit 1 --no-rebuild`. The live sync completed in
  `8.394s`, with `selected_count=0`, `processed_count=0`, `updated=1`,
  `unchanged=3480`, and `removed=0`, under a maintenance coordinator lease that
  touched only `entity_registry` and `search`. The previous fallback route for
  the same class of source-card change took `84.125s`, including `27.019s` of
  unrelated session bulk indexing and `56.945s` of registry refresh. A later
  stale registry sync with a too-small hard SQLite progress budget produced
  `sqlite_error:interrupted`; the route now treats `--budget-seconds` as a
  soft observed budget because snapshot and SQLite registry docs are an atomic
  consistency unit.
- 2026-06-27 MCP tool source discovery proof: after adding a new
  `aoa-session-memory-mcp` tool, direct `entity-registry-search-sync` refreshed
  `4183` registry entities in `15.926s`, inserted `125` entity-registry search
  docs, and raised `mcp_tool` registry coverage to `126`. Lookup for
  `aoa_session_entity_usage_chain --kind mcp_tool` returned an active
  `mcp_tool` with source surface `abyss_stack_mcp_tool_source`, proving new MCP
  tools can be registered from source before they appear in archived usage.
- 2026-06-29 entity-registry observed-source proof: after diagnostics showed
  direct `entity-registry-search-sync` taking `122.955s` to `223.008s` while
  updating one registry doc, the observed archived entity lane was moved to
  current operational route-rollup by default. Live dry run built the same
  `4220` entities with `observed_route_source=operational_route_rollup` in
  about `280ms` versus about `10.038s` for explicit `route-terms` on a warm
  cache. The first live search sync after the route change reconciled `4049`
  registry docs in `3.332s`; the repeated current no-op completed in `219ms`
  with `document_count_source=session_index_state_plus_entity_registry` and
  `count_search_documents.elapsed_ms=0`.
  A later stale source-shard mismatch showed that `auto` could still fall back
  to `archived_route_terms` and spend `185.744s`; the route now uses a
  stale-but-readable materialized rollup as navigation evidence with explicit
  `observed_stale` refs and `observed_route_status`, leaving route-terms as the
  explicit heavy/deep lane.
- 2026-06-27 compact entity-usage scenario ref proof: after source-discovered
  MCP tools were registered, the live route audit exposed that compact
  `entity-usage-scenario-audit` samples had raw previews and document refs but
  did not surface bounded `first_ref` / `evidence_ref_counts` unless the heavy
  `--full` packet was requested. The compact sample now carries bounded
  `document_refs`, `evidence_refs`, `evidence_ref_counts`, and `first_ref`.
  Re-running `entity-usage-scenario-audit --seed
  mcp-tool-registry-source-scan --sample-size 2 --limit 2 --per-route-limit 12
  --consequence-window 6 --raw-preview-limit 2 --write-report` returned
  `2/2` passed, `raw_or_segment_ref_sample_count=2`, and raw previews
  available for all four checked events. Re-running `live-scenario-audit
  --profile entity_usage --profile literal_planner --profile graph_bridge
  --sample-size 2 --limit 2 --seed mcp-tool-registry-source-scan` returned
  `3/3` passed, `warn_count=0`, `actionable_gap_count=0`, and surfaced a first
  raw/segment ref directly in the `entity_usage` scenario packet.
- 2026-06-27 compact graph-bridge performance proof: the reviewed
  `graph_bridge_refs_contract` corpus case was correct but spent `62.841s`
  expanding the dense `tool:exec_command` side before returning evidence refs.
  `graph-bridge` now keeps side neighborhoods shallow in the first packet and
  leaves deeper path search behind the returned `shortest_path` expansion. A
  direct `graph-bridge aoa-session-memory-mcp exec_command --source-kind mcp
  --target-kind tool --limit 4 --max-depth 4` run returned in `3.85s` with
  `evidence_ref_count=8`, raw/segment/session refs, and
  `compact_side_neighborhood=true`. Re-running `live-scenario-corpus check`
  kept `graph_bridge_refs_contract` green and reduced the observed
  `graph_bridge` profile to `2.133s` with `raw_ref=16`, `segment_ref=16`, and
  `session_ref=16`.
- 2026-06-27 broad consumer live-loop proof: `live-scenario-audit --profile
  entity_usage --profile literal_planner --profile graph_bridge --profile
  graph_neighborhood --profile hook_failure --profile goal_lifecycle --profile
  agent_closeout --sample-size 3 --limit 3 --seed
  broad-route-proof-after-bridge-fastpath --write-report` returned `7/7`
  passed, `warn_count=0`, `failed_count=0`, `actionable_gap_count=0`, and
  `elapsed_ms=6802`. The run covered entity usage, literal routing, graph
  bridge, graph neighborhood, hook failures, goal lifecycle, and final closeout
  routes with raw/segment/session or receipt refs on all evidence profiles.
- 2026-06-25 resource live-tail fast-path proof: a timer-driven
  `auto-maintenance-resource catchup all` launched broad
  `auto-maintenance catchup all`, selected `285` sessions, touched
  `token_accounting`, and took `377.7s` for a situation where
  `maintenance-status` already exposed a targeted live-tail command. The
  resource wrapper now preflights that packet and, when ready, wraps
  `index-maintenance <session> --skip-graph-repair --skip-token-accounting`
  under `abyss-machine resource launch` instead of broad catch-up. The regression
  test proves the child command contains no `auto-maintenance` token and carries
  the bounded budget/reason into the targeted route.
- 2026-06-25 operations telemetry proof: `search-index` and `search-shards`
  reports now include bounded `slow_sessions` rows with session label,
  elapsed time, document count, docs/sec, raw-text status, and shard when
  applicable. Source and standalone bundle test suites both passed
  `258 passed`; source and bundle `validate` passed, and standalone
  `audit --portable-bundle` returned `completion_ready=true`. A live scoped
  incremental `search-shards` pass over
  `2026-06-01__001__что-сейчас-грузит-процессор` returned `ok=true`,
  `processed_count=1`, and surfaced the session in `maintenance-status`
  compact `operations.search_shards.latest_materialization.slow_sessions`.
  During an active Codex session, `maintenance-status` may still report
  `waiting_for_quiet_window` for recently written live transcripts; that is a
  live-tail deferral, not archive evidence loss.
- 2026-06-26 graph live-tail hot-gate proof: a stale graph ledger first exposed
  dirty/missing sources from an active long Codex transcript, then a live
  `maintenance-status` run after the deferred-live fix reported
  `graph.status=current_with_deferred_live_sources`,
  `graph.needs_maintenance=false`, `actionable_count=0`,
  `ledger_store_missing_total_count=10`,
  `deferred_ledger_store_missing_count=10`, and `diagnostics=[]`. Regression
  proof: `test_graph_hot_state_defers_old_source_when_live_transcript_recent`
  plus the existing graph hot-state mismatch tests.
- 2026-06-25 live-tail shard route proof: a month shard that was non-current
  only because of `freshness_counts.deferred_live` now reports
  `current_with_deferred_live_updates` instead of
  `search_shards_not_current`; the live-tail route owns the wait/catch-up
  action, and stable archive graph/search remains usable. After a targeted
  catch-up of
  `2026-06-12__001__на-машине-есть-раскиданный-abyss-machine`,
  `search-shards <session> --no-rebuild --write-report` processed exactly one
  session in `18.356s`, `maintenance-status --full --no-timers` returned
  `ok=true`, `recommendation=use_graph_search`, `warnings=[]`, and
  `projection-catchup all --write-report` returned `status=nothing_to_do`,
  empty actionable/deferred surfaces, and `next_route=verify_projection_status`.
  MCP `projection-status` reads that report without running catch-up and
  returns empty actionable/deferred surfaces.
- 2026-06-21 structured shard slimming contract: default `search-shards`
  materialization now builds monthly structured-route shard projections that
  skip local raw-text FTS inserts, compressed `document_bodies`, and raw event
  semantic-text extraction. The shard catalog records `storage_mode` and
  `raw_text_query_support`; text queries with `--use-shards` fall back to the
  monolith via `search_shard_fanout_raw_text_uses_monolith_fallback`, while
  structured routes still use bounded shard fan-out. Use
  `search-shards --full-text` only for an explicit heavy lexical shard
  benchmark. A live `search-shards all --write-report` rebuild processed `282`
  sessions and `1,640,926` shard documents into structured-only shards
  (`monolith_fallback_required` for raw text); `search/shards` dropped from
  about `9.4 GiB` to `7.9 GiB`. `agent-responses --use-shards --agent-event
  assistant_answer --limit 5` returned through `materialized_shard_fanout` with
  `uses_fts=false`, `hydrates_body=false`, `uses_shards=true`, and
  `maintenance-status --full` returned `ok=true`, route `current`, and
  `agent_route=use_graph_search`.
- 2026-06-21 MCP live route proof after schema 10 rebuild:
  `aoa_session_maintenance_status(full=true)` returned through MCP in about
  `1.45s` with search ready, graph usable, no writer, and the completed
  manual-bulk job as latest writer evidence. `aoa_session_entity_inventory`
  for `layer=skill`, `query=aoa-session` returned indexed skill entities with
  atlas, segment, and raw refs. `aoa_session_entity_usage_audit` for
  `aoa_session_search` returned direct usage events, consequence events,
  document refs, and provider schema `10` in about `1.09s`;
  `aoa_session_entity_usage_neighborhood` returned bounded before/after
  windows in about `1.74s` with raw previews intentionally disabled for the
  fast route. A fresh MCP stdio smoke after the inventory normalization accepts
  `layer=mcp_service`, returns canonical `layer=mcp`, uses `source=atlas`, and
  resolves `aoa_session_memory_mcp`; already-running Codex MCP processes need
  a restart to load the source change.
- 2026-06-11 storage weight proof: read-only `storage-audit --deep-dbstat
  --row-counts --write-report` measured `.aoa` at `119.7 GiB`; top weights
  are graph `78.7 GiB`, sessions `28.9 GiB`, and search `11.6 GiB`. SQLite
  freelists are tiny (`11.6 MiB` graph, `1.3 MiB` search), so plain `VACUUM`
  is not the answer. Measured reclaim candidates are compact graph aggregate
  payloads `31.7 GiB`, search body storage v2 `8.8 GiB`, and raw-block
  duplication `6.1 GiB`. Graph/search compaction is implemented for controlled
  rebuilds and touched sources; raw-block cleanup remains a planned safe route
  until offset/compressed raw-block readers preserve stable refs. Report:
  `diagnostics/20260611T231448Z__storage-audit.json`.
- 2026-06-21 graph storage correction proof: the earlier graph aggregate
  reclaim estimate was table-size based and is superseded by sampled payload
  delta. A read-only `storage-audit --deep-dbstat --write-report` on the live
  archive measured graph `57.2 GiB`, aggregate `nodes` + `edges` tables
  `17.8 GiB`, sampled `400` aggregate payload rows, and found
  `sample_delta_ratio=0.0`. The graph aggregate recommendation is now
  `status=already_compact_sampled_cardinality_dominates`,
  `estimate_status=sampled_no_payload_delta`, and reclaim `0 B`; the next
  route is graph cardinality, sharding, or query projections, not a rebuild
  solely for aggregate payload compaction. Report:
  `diagnostics/20260621T091705Z__storage-audit.json`.
- 2026-06-28 search/graph physical compaction proof: read-only
  `storage-audit --write-report`, `search-sqlite-compact --write-report`, and
  `graph-sqlite-compact --write-report` showed current physical SQLite reclaim
  is tiny relative to store size: search monolith `10.5 GiB` with `28.2 MiB`
  conservative reclaim, graph `28.7 GiB` with `46.2 MiB` conservative reclaim.
  The `search_projection_combined_large` warning is therefore a projection
  strategy issue (`monolith_fallback_required` plus structured shards), not a
  safe `VACUUM` cleanup opportunity. Keep raw-text recall on the monolith until
  a scoped full-text shard policy is intentionally chosen and benchmarked.
- 2026-06-21 graph cardinality projection proof: before materialization,
  read-only `graph-cardinality --limit 12` returned
  `projection_missing` in `2 ms`. A resource-gated
  `graph-cardinality --refresh --limit 12` materialized
  `graph_type_counts` in `134.182s` for `3,483,100` nodes and `24,120,097`
  edges. The next read-only `graph-cardinality --limit 12` returned
  `projection.status=current`, `row_count=60`, and `elapsed_ms=1` with top
  pressure at `mentions_route_signal=13,971,830`,
  `event_mentions_registered_entity=2,297,969`, and `event/raw_ref=1,601,970`
  each. Use this projection for agent graph size/cardinality questions instead
  of ad hoc full `GROUP BY` scans.
- 2026-06-21 raw-ref materialization policy: new/rebuilt graph sources no
  longer emit standalone `raw_ref` nodes or `has_raw_ref` edges; raw refs remain
  in event `evidence_refs`, which keeps raw/segment/session authority intact
  while reducing future graph cardinality. The live graph store is intentionally
  mixed until a controlled rebuild/prune lane runs: `storage-audit` reports
  `graph_raw_ref_materialization_policy=event_evidence_refs_only_v1`,
  `raw_ref_node_count=1,602,750`, `has_raw_ref_edge_count=1,602,750`, and
  `status=disabled_for_new_builds_existing_store_mixed`. Do not schema-bump the
  live graph solely for this; reclaim needs a reserved rebuild/prune plus
  SQLite compaction route.
- 2026-06-21 event route-signal graph materialization policy: new/rebuilt graph
  sources keep exact `mentions_route_signal` event edges only for concrete
  operational anchors (skills, MCPs, hooks, tools, APIs, plugins, agents,
  scripts, validators, tests, evals, Git, playbooks, techniques, mechanics,
  graph, memory, and goals) and emit `segment_has_route_signal` summaries for
  every route signal. Wide facets remain exact in segment indexes and search
  postings, while graph uses segment/session summaries to avoid
  event-by-route-signal fanout. The policy is tracked as
  `graph_event_route_signal_edge_policy=anchor_event_edges_segment_summary_v1`
  in graph metadata and source fingerprints rather than a graph schema bump;
  old graph sources should therefore refresh as normal source fingerprint drift.
  Regression proof:
  `test_graph_route_signal_materialization_keeps_wide_facets_at_segment_level`.
- 2026-06-21 graph hot-state empty-store guard: a killed in-place generated
  graph rebuild must not leave `maintenance-status` green. The hot path now
  reads cheap SQLite state counts, reports `graph_store_nodes_empty` /
  `graph_store_edges_empty` as structural stale state, and routes recovery to
  bounded `graph-maintenance --apply` instead of retrying a full in-place
  rebuild by default. Mass classifier, fingerprint, policy, or missing-source
  drift likewise recommends budgeted graph maintenance; full store-only rebuild
  stays a manual heavy/resource-gated route. Regression proof:
  `test_graph_hot_state_detects_empty_store_without_source_scan`.
- 2026-06-21 graph partial-store and lock-conflict proof:
  `maintenance-status --full` now detects a partial generated graph store by
  comparing non-retired source-state ledger entries with stored
  `graph_sources`, carries only global fresh `graph-maintenance.remaining_count`
  as a global hot-gate signal, and ignores scoped latest reports for global
  remaining counts. It emits real-root bounded graph-maintenance commands
  without `/path/to/workspace` placeholders; large manual budgeted routes use
  batch `25`, while hot timer ticks stay small. Manual maintenance lock
  conflicts return a bounded `session_memory_maintenance_lock_conflict` packet
  instead of blocking indefinitely. Regression proof:
  `test_graph_hot_state_detects_ledger_store_source_count_mismatch`,
  `test_graph_hot_state_uses_latest_graph_maintenance_remaining_count`,
  `test_graph_hot_state_ignores_scoped_latest_graph_maintenance_remaining_count`,
  `test_graph_source_recommendation_routes_mixed_backlog_to_bounded_apply`,
  `test_maintenance_next_actions_uses_budgeted_graph_batch_limit`,
  and `test_manual_maintenance_lock_returns_conflict_instead_of_blocking`.
  Live proof: a 2026-06-21 resource-gated manual batch
	  `graph-maintenance all --apply --batch-limit 25 --budget-seconds 300
	  --refresh-chunk-size 64 --write-report --write-hash-cache` completed under
	  `abyss-machine resource launch --class medium --kind indexing` in `102.559s`,
	  selected `25` sources, left `4679` global missing sources, consumed `4G`
	  peak memory, and used `0B` swap.
- 2026-06-28 interactive graph-drip cap proof: near-budget live graph drips
  showed that limiting only `batch-limit` and `candidate-pool-limit` is not
  enough for predictable interactive maintenance. `maintenance-status` now emits
  graph queue/heavy-tail commands with aggregate caps
  `--max-refresh-nodes 20000 --max-refresh-edges 60000`; heavy-tail source
  recommendations carry the same caps and an
  `interactive_drip_uses_aggregate_refresh_caps` note. Regression proof:
  `test_graph_source_recommendation_*heavy_tail*`,
  `test_maintenance_next_actions_drips_existing_budgeted_graph_queue`,
  `test_maintenance_next_actions_preserves_heavy_tail_candidate_pool`, and
  `test_maintenance_next_actions_seeds_empty_graph_queue_from_ledger`.
  Live proof: uncapped `25`-source drip refreshed `18,478` nodes and `70,142`
  edges in `241.855s`; capped exact planning chose `20` sources, `14,584`
  nodes, and `58,808` edges; capped apply refreshed those same aggregate counts
  in `239.897s`, moved the generated graph queue `550 -> 530`, and deferred
  `5` sources by refresh budget. The cap prevents oversized rewrite slices but
  does not yet solve the deeper `replace_sources` / aggregate-refresh cost.
  Follow-up route adaptation: graph status now exposes a bounded
  `latest_maintenance` summary, chooses the latest global graph-maintenance
  report instead of letting scoped `selected_sessions` reports hide global
  evidence, keeps scoped/source-key graph reports out of global queue-drip
  sizing, and switches queued graph repair to a `10`-source micro-drip with
  `10000`/`30000` aggregate caps only after a recent broad queue/heavy-tail
  drip made progress but was slow or near the interactive budget.
  Follow-up timing proof: `graph-maintenance` reports now include
  `maintenance_detail.phase_timings_ms` plus nested
  `replaced_phase_timings_ms` / `replaced_aggregate_refresh_timing`. A live
  one-source apply before the aggregate-refresh fix
  (`diagnostics/20260628T082319Z__graph-maintenance.json`) took `45.991s`;
  `apply_replace_ms=42354`, `aggregate_refresh_ms=41515`, and
  `replaced_node_refresh.elapsed_ms=36386` after scanning `229584`
  `node_contribs` rows. The fix changes node/edge aggregate refresh from
  Python JSON merge of every contributing row to SQL summary plus one
  representative compact payload per aggregate id; evidence remains hydrated
  from contribution rows. Live proof after the fix
  (`diagnostics/20260628T082916Z__graph-maintenance.json`) processed a similar
  source in `10.904s`, with `apply_replace_ms=6904`,
  `aggregate_refresh_ms=5953`, `replaced_node_refresh.elapsed_ms=3085` over
  `154846` node contrib rows, and queue `500 -> 499`. Regression proof:
  `350 passed` for `tests/test_session_memory.py`; live `validate` returned
  `ok=true`.
  After targeted search catch-up, dirty-only `month/2026-06` shard refresh,
  and the graph aggregate-refresh fix, `maintenance-status --full` reports
  search/search shards `current_with_deferred_live_updates`, no recent problem
  jobs, graph queue `499`, graph actionable `2177`, `latest_queue_maintenance`
  absent for targeted source-key proof reports, and next action
  `repair_graph_queue_drip` with `25` sources and `20000`/`60000` aggregate
  caps.
- 2026-06-27 graph rebuild cleanup proof: live maintenance found an orphaned
  `.graph.sqlite3.<pid>.rebuild.tmp-journal` after interrupted graph work while
  the base `.rebuild.tmp` file was already gone. `maintenance-cleanup` now
  groups rollback journals with graph rebuild temp families, reports them in
  storage status, and removes only stale generated maintenance artifacts.
  Regression proof:
  `test_maintenance_cleanup_detects_orphaned_graph_rebuild_tmp_journal_without_base`.
- 2026-06-21 raw-ref prune route: `graph-raw-ref-prune` is the controlled lane
  for that mixed-store tail. Dry-run is read-only and uses materialized
  `graph_type_counts`; apply runs under the maintenance coordinator, deletes only
  generated `raw_ref`/`has_raw_ref` aggregate and contribution rows, updates graph
  type counts/metadata, checkpoints WAL, and leaves raw transcripts plus
  session/segment/event evidence refs untouched. The command intentionally does
  not run `VACUUM`; any physical `graph.sqlite3` shrink needs a separate
  reserved-disk route. The live 2026-06-21 repair removed 1,602,750 `raw_ref`
  nodes, 1,602,750 `has_raw_ref` edges, and matching contribution rows
  (6,411,000 rows total) in about 56 minutes; the apply path is therefore
  documented as `manual-bulk`, has a disk-headroom preflight, and should not be
  used as an interactive query path.
- 2026-06-21 graph SQLite compaction route: `graph-sqlite-compact` is the
  explicit preflight/staging lane for physical graph DB shrink after generated
  projection cleanup. Dry-run is read-only and reports conservative headroom for
  `VACUUM INTO`; apply runs under the maintenance coordinator, creates an
  integrity-checked compact copy by default, and does not replace live
  `graph.sqlite3`. Source-mutating `VACUUM` requires `--confirm-source-vacuum`.
  On the live 57.2 GiB graph store the default 25 GiB post-operation reserve
  currently blocks compaction until more disk headroom is reserved or graph
  cardinality is reduced.
- 2026-06-21 raw-block ref reader route: `raw-block-ref-audit` is the read-only
  gate before any raw-block duplication cleanup. It resolves sampled
  `raw:line:N` refs through `raw/blocks.index.json` / manifest raw-block ranges,
  reads the block-local line, and compares it to the full raw transcript. This
  proves the reader path and mismatch detection; it does not delete raw blocks
  or replace raw transcript authority.
- 2026-06-21 raw-block storage compact route: `raw-block-storage-compact`
  stages gzip-backed raw-block storage after `raw-block-ref-audit` passes.
  Dry-run can estimate compression without mutation; apply writes compressed
  sidecars, updates manifest/index/segment source-block metadata, and reruns
  the ref audit. Removing plaintext block duplicates requires the explicit
  `--confirm-remove-plain` flag and keeps `raw/session.raw.jsonl` as authority.
  Live cleanup completed in bounded batches: 4,584 plaintext raw-block
  duplicates were converted to gzip-backed sidecars and removed. Final
  `raw-block-storage-compact all --skip-no-plain --limit 200` reports
  `current_no_plain_candidates`; `storage-audit` reports 0 B plaintext
  duplicate candidate, 2.9 GiB compressed raw-block sidecars, and 29.2 GiB
  session storage total. A broad post-cleanup `raw-block-ref-audit` sampled 400
  refs across 240 sessions with 0 missing/mismatch and no raw text previews.
  During the live batches, timer-driven `auto-maintenance hot` overlapped a
  manual raw-block apply; the CLI apply route now runs under the maintenance
  coordinator as `manual-bulk` for `raw_blocks`, `session_manifests`, and
  `session_registry`. A live tail apply waited 339,859 ms for an active hot
  maintenance lock, then completed with post-apply ref audit clean; future hot
  maintenance should defer instead of competing.
- Optional host-provider proof: `search-provider-status --include-host`
  probes host capability gates without making them authority. If
  `abyss-machine nervous quality-audit` reports warnings, `.aoa` keeps
  authoritative hits on `portable_sqlite` and treats host output as contextual
  only.
- Local semantic/rerank accelerator proof: optional host model gates expose
  embedding freshness and reranker health; `search --include-semantic-context
  --rerank-local` keeps `portable_sqlite` as the authoritative result provider
  while adding host semantic context and `host_rerank` ordering metadata. Live
  probe on 2026-05-24: embedding `ready`, reranker `ready`,
  `semantic_overlay.ok=true`, local rerank `applied`; provider report:
  `diagnostics/20260524T150706Z__search-provider-status.json`.
- Retrieval packet proof: `retrieve continue-techniques-session` returns a
  bounded evidence packet with selected session identity, search hits,
  continuation signals, phase-discovery queue state, raw refs, and next route
  commands.
- `batch-distill --since 2026-04-21 --limit 3 --write-report`: project
  grounding fallback is present for broad `cwd=/srv` sessions through
  `/srv/AbyssOS/AGENTS.md` and `/srv/AbyssOS/README.md`; report:
  `diagnostics/20260512T183224Z__batch-distill__first-wave.json` and `.md`
- `naming-readiness all --refresh-indexes --write-report`: `ok=true`,
  selected `147` sessions; status counts: `diagnostic_only=4`,
  `low_signal=9`, `named=2`, `needs_phase_discovery=5`,
  `needs_reindex=1`, `phase_discovery_ready=1`, `readable_label=119`,
  `ready_for_semantic_name=6`; report:
  `diagnostics/20260513T222601Z__naming-readiness.json` and `.md`
- `phase-discovery`: `ok=true`; wrote unreviewed candidate layers for
  `2026-04-23__068__коммить-пуш-мердж` (`100` candidates) and
  `2026-05-12__001__aoa-session-dist-exp-идея` (`21` candidates after
  reindex); reports:
  `diagnostics/20260514T000124Z__phase-discovery__2026-04-23__068.json`
  and `diagnostics/20260513T235954Z__phase-discovery__2026-05-12__001__aoa-session-dist-exp.json`.
  Candidates now carry `name_basis`, `quality_flags`, `linked_signals`, and
  `review`; the idea session currently has `5` candidates in `review_queue`
  for semantic synthesis before application.
- `review-phase-name`: guarded route added for one phase-discovery candidate at
  a time. It previews raw samples and rejects `--use-candidate` for
  `needs_semantic_synthesis`; successful application refreshes
  `SESSION_NAMES.md`, `session-name-index.json`, `sessions/INDEX.md`, and
  `sessions/index.json`.
- `name-session`: applied `aoa session-memory archive design and naming
  pipeline` as the active session name for
  `2026-05-12__001__aoa-session-dist-exp-идея`, plus `16` reviewed phase
  names with raw-line coverage; then `reindex-sessions` refreshed that archive
  to `indexed`, `16158` events, `21` segments.
- `validate`: `ok=true`
- `codex-compact-probe --trust-hooks`: `ok=true`, live `PreCompact` and
  `PostCompact` completed and archived; latest probe raised live counts to
  `PreCompact=4`, `PostCompact=4`
- `stress-pass --compactions 100 --write`: `ok=true` on the largest archive
- `doctor --check-live-hooks --check-user-skill --check-codex-grounding`:
  `ok=true`, no problems, no warnings
- `audit`: `completion_ready=true`, `remaining=[]`, `session_count=147`;
  indexed archive topology has `mismatch_count=0`. The audit separates
  deferred hook mirrors from indexed archives so `raw_mirrored_index_deferred`
  sessions do not masquerade as complete indexed topology.
- 2026-05-13 route-design verification: `DESIGN.AGENTS.md` is present in the
  source root and exported bundle; `sessions/AGENTS.md` is present as the
  archive-district route card; portable source district cards are present for
  `config/`, `hooks/`, `schemas/`, `scripts/`, `skills/`, and `tests/`;
  `diagnostics/AGENTS.md` is present as a live-only evidence guard; required
  root-file checks include the portable route layers; source `doctor` is
  `ok=true` with no problems or warnings, and the standalone mirror validates
  as a clean bundle.
- local workspace doctor: `ready=True`
- local workspace hooks doctor: `ready=True`

Current real compaction segmentation, from the 2026-05-13 audit expected/actual
segment evidence:

- `2026-05-01__001__в-прошлой-сессии-мы-на-протяжении-почти-недели`:
  expected `157`, actual `157`.
- `2026-05-06__001__codex-in-abyssos`:
  expected `51`, actual `51`.
- `2026-05-12__001__aoa-session-dist-exp-идея`:
  expected `18`, actual `18`.
- `2026-05-12__005__aoa-manual-compact-live-hook-probe-preserve-this`:
  expected `2`, actual `2`.
- `2026-05-12__006__aoa-manual-compact-live-hook-probe-preserve-this`:
  expected `2`, actual `2`.

Current deferred hook mirror:

- `2026-05-07__001__srv-abyssos-abyss-stack-и-src-abyss-stack-нам-на`:
  `archive_status=raw_mirrored_index_deferred`, expected after reindex `36`,
  current actual `36`. This is a live hook-preservation state, not reviewed
  completion of that active source session.

Stress-pass evidence:

- Largest archive first-100 compaction interval pass:
  `diagnostics/20260512T060632Z__stress-pass__first-100-compactions.json`
  and `.md`; `ok=true`, selected segments `000..099`, raw span `1..72177`,
  no compaction-marker microsegments.

## Coverage Map

| Requirement | Evidence |
| --- | --- |
| Agent-facing route shape is documented separately from root law and system design | `DESIGN.AGENTS.md`, required root file checks, install/export regression test |
| Portable source districts have local route cards before agents edit them | `config/AGENTS.md`, `hooks/AGENTS.md`, `schemas/AGENTS.md`, `scripts/AGENTS.md`, `skills/AGENTS.md`, `tests/AGENTS.md`, required root file checks |
| Full raw transcript mirror when `transcript_path` is readable | `handle_hook_event`, `sync_session_from_transcript`, tests for raw mirror |
| Raw unavailable is diagnostic, not fake memory | `write_raw_unavailable_incident`, raw-unavailable test |
| `raw_unavailable` archives do not crash global audit | raw-unavailable completion-audit regression test |
| PreCompact/PostCompact and large Stop hooks stay timeout-safe while queueing automatic background sync | lifecycle hook worker regression test, largest-transcript hook benchmark |
| PostCompact worker sealing writes raw interval blocks, raw ledgers, segment Markdown, and sibling indexes | raw block checks in `validate`, lifecycle hook worker regression test |
| Explicit full-sync routes regenerate compaction interval indexes as recovery/rebuild paths | manual sync regression test, `validate`, `sync`, import, reindex |
| Real Codex `compacted` and `context_compacted` raw events define one logical segment boundary | rebuilt live archives, `audit`, real compact marker regression test |
| Large-session stress pass can audit the first 100 compaction intervals without loading bulk raw into the agent context | `stress-pass --compactions 100 --write`, largest-session diagnostics |
| Hook stdout is schema-limited | `codex_hook_output`, protocol-field tests |
| UserPromptSubmit stays light by default | prompt-hook test |
| Real Codex CLI hooks run in standalone sessions | live `codex exec` smoke sessions under `sessions/2026-05-12__002__...` and `__003__...` |
| Session names are readable date/sequence/title labels | naming policy, relabel test |
| Later semantic names can route agents without renaming archives or weakening raw provenance | `name-session`, scoped `semantic_names`, raw anchor regression tests |
| Session/phase names are comparable through a lightweight root name index | `session-name-index.json`, `SESSION_NAMES.md`, scoped name index regression tests |
| Broad naming starts from route readiness instead of cosmetic relabeling | `naming-readiness`, `SESSION_NAMES.md`, `sessions/INDEX.md`, naming-readiness regression test |
| Large-session names can be prepared by an open candidate layer before promotion | `phase-discovery`, `review-phase-name`, `naming/phase-discovery.json`, phase-discovery/review regression tests |
| Session archives have a local route card and table of contents before agents open individual sessions | `sessions/AGENTS.md`, `sessions/INDEX.md`, `sessions/index.json`, doctor checks, semantic-name and registry recovery regression tests |
| Segment Markdown has sibling indexes | segment generation, doctor, tests |
| Segment indexes classify universal session events by facets and relationships | event taxonomy config, segment index schema, reindex report, universal facet regression tests |
| Agent answers, progress updates, closeouts, blockers, handoffs, verification reports, and reasoning boundaries are searchable without treating generated classes as reviewed truth | `facets.agent_event`, `by_agent_event`, `agent_event_counts`, `agent-responses`, `agent-closeouts`, `agent-progress-updates`, `agent-reasoning-windows`, agent-event regression test |
| Task intervals can be inspected as generated navigation packets with raw/segment refs | `task_episodes`, `task_episode_counts`, `task-episodes`, `answer-neighborhood`, task-episode regression test |
| Goal lifecycles bridge into the surrounding task and answer route without raw/search expansion | `goal_lifecycles`, `goal-lifecycles`, `work_chain`, `task_episodes`, `answer-neighborhood`, goal lifecycle regression test |
| Segment and session indexes expose operational route signals for the 22-layer map | `facets.route_signals`, `by_route_layer`, `by_route_signal`, `route_signal_counts`, route-signal regression tests |
| Stable AoA skill and MCP service names route agents through canonical map axes | `entity:aoa_memo_writeback`, `entity:aoa_memo_mcp`, `mcp:aoa_memo_mcp`, `maps/by-entity/INDEX.md`, `maps/by-mcp/INDEX.md`, route-signal regression tests |
| Agents can start from a named operational anchor instead of hand-picking a map axis | `trace-route`, `resolve-anchor`, route-trace regression test, 2026-05-26 live route-trace reports |
| Preserved raw archives can be regenerated after taxonomy/classifier changes | `reindex-sessions all --max-raw-mb`, reindex report diagnostics, reindex regression test |
| Secondary route caches repair themselves through a bounded controller | `index-maintenance`, queued `index_maintenance` worker jobs, `auto-maintenance`, semantic-name maintenance regression test |
| Agents can search across many archived sessions without loading bulk raw into active context | `search-index --max-raw-mb`, `search --explain`, `search/aoa-search.sqlite3`, search-index regression test, 2026-05-17 live search report |
| Agents can query route layers directly | `search --route-layer`, `search --route-signal`, SQLite route-signal columns |
| The source atlas skeleton can be turned into generated entries and indexes | `atlas build`, `maps/by-*/entries/*.json`, `maps/by-*/INDEX.md`, atlas-build regression test |
| Agents can maintain graph state incrementally by session/segment contribution | `graph/graph.sqlite3`, `graph-maintenance`, graph source states, dirty-source replacement regression test |
| Agents can expand operational anchors and bridge two operational anchors through graph packets without losing evidence refs | `graph-build`, `graph-maintenance`, `graph-prune-sidecar`, `graph-neighborhood`, `graph-timeline`, `graph-shortest-path`, `graph-bridge`, `graph-cooccurrence`, graph sidecar regression test |
| GraphRAG packets combine lexical entrypoints, graph expansion, cooccurrence, refs, and freshness without promoting claims | `graphrag-packet`, `graph-eval`, graph/GraphRAG regression test |
| Graph/RAG quality can be sampled before trusting an operational anchor route | `graph-quality-audit`, raw preview refs, freshness flags, graph quality regression test, 2026-05-26 live 9-anchor sample |
| Graph/RAG quality verdicts can produce feedback and regression candidates without mutating evidence | `graph-quality-review`, verdict/action counts, quality feedback, regression candidates, graph quality review regression test |
| The full 22-layer operational skeleton can be audited as one readiness gate | `route-readiness`, source atlas axes, generated atlas index, portable SQLite provider, route-readiness regression test |
| Route-signal classifier quality can be manually sampled without opening bulk raw | `route-sample-audit`, reviewed calibration packets, raw previews, route-sample regression test |
| Route-signal sample verdicts can become durable classifier feedback without mutating evidence | `route-sample-review`, append-only review diagnostics, classifier feedback list, route-sample review regression test |
| Host retrieval tools can be used without merging `abyss-machine` into `.aoa` authority | `config/search-providers.json`, `search-provider-status`, `search --provider abyss_machine_nervous`, `search --include-semantic-context --rerank-local`, host-provider and local-rerank regression tests |
| A future agent can request a bounded continuation packet instead of scanning a long session manually | `retrieve`, `retrieval-packet`, continuation recipe regression test, real `continue-techniques-session` probe |
| Rehydration uses indexes before bulk files | `rehydrate`, tests |
| First-pass distillation is provisional | `distill`, tests |
| Historical sessions can be split into automatic, prioritized responsible review, mechanics, low-risk, and diagnostic lanes before review | `batch-distill`, batch distillation policy, tests |
| Batch distillation keeps project grounding instead of treating sessions as generic text | `project_grounding`, workspace fallback test, batch report |
| Fallback-grounded sessions keep owner resolution separate from project grounding | `owner_resolution`, indexed-path fallback regression test |
| Weak imported titles can be repaired without changing raw evidence | `repair-session-titles`, title repair regression test |
| Manual review packets and promotion candidates remain unreviewed until promotion review | `manual-review`, `promotion-review`, manual review packet regression test |
| Repeated manual-review passes are append-only and remain open for future passes | manual-review wave regression test, live wave2 diagnostics |
| User-level hooks can be generated from selected roots | `hooks-config`, tests |
| Approved user-level session-memory skills can be installed, surfaced, and checked from selected roots | `install-user-skill`, `doctor --check-user-skill`, `doctor --check-installable-user-skills`, audit checklist, tests |
| Historical Codex JSONL sessions can be discovered, dry-run checked, and sequentially imported | `import-codex-sessions`, import report diagnostics, tests |
| Missed close/no-hook and stale Codex transcripts can be found without trusting active context | `sweep-codex-sessions`, `indexed_archive_freshness`, sweep report diagnostics, tests |
| Session token accounting remains count-only and separates provider, exact tokenizer, and estimated ledgers | `token-accounting`, `token-accounting-backfill`, token accounting regression test, host `aoa-summary` bridge self-test |
| Live hooks match expected commands | `doctor --check-live-hooks` |
| Native Codex hook trust is inspectable and repairable | `codex-hooks-status`, app-server `hooks/list` and `config/batchWrite` |
| Local Codex compact/hook contract is grounded | `codex-grounding`, local `codex-cli 0.133.0`, project config |
| Live PreCompact/PostCompact receipts are observed | `codex-compact-probe --trust-hooks`, sessions `2026-05-12__005__...` and `2026-05-12__006__...`, `audit` |
| Clean bundle export excludes sessions by default | `export-bundle`, install/export CLI check |
| Workspace install regenerates hook example for target roots | `install`, install test |
| Install repair does not clear existing sessions by default | preservation test |
| Standalone GitHub repository exists | private repo `8Dionysus/aoa-session-memory`, local `origin` on `main` |
| Completion readiness is explicit rather than inferred from green tests | `audit` command |

## Remaining Gates

Completion-blocking gates in the current local proof surface:

- None for the 22-layer route atlas proof as of the 2026-05-26 v10 reports:
  `route-readiness` is `ok=true`, all `163` current indexable route indexes
  are current, `stale_route_classifier=0`, and `34` diagnostic/non-indexable
  archives are explicitly routed as non-indexable evidence rather than route
  failures.

Maintenance gates:

- After route schema, classifier, semantic-name, or generated-cache changes,
  run `projection-catchup all --apply --write-report`. The route wraps the
  maintenance coordinator, keeps generated projections below raw/session
  authority, and returns either a bounded rerun route or
  `projection-catchup --profile deep` when heavy search/graph repair is needed.
  Its `projection_completeness` block is the compact proof surface for agents:
  each generated projection surface reports status, dirty/deferred counts, and
  the next route without forcing an agent to parse the full maintenance tree.
  Use `index-maintenance` directly only for narrower manual repair. Add
  `--sample-audit` when classifier/schema changes require a new manual
  calibration packet; apply `route-sample-review` verdicts explicitly after
  human/agent review.
- After search-provider or local accelerator changes, run
  `search-provider-status --include-host --write-report` and a bounded
  `search --include-semantic-context --rerank-local --allow-host-warnings
  --host-timeout 120` probe. Treat host warnings as accelerator state, not
  archive failure.
- Re-run `codex-grounding` and `codex-hooks-status` when the local Codex CLI
  version changes.
- Re-run `codex-compact-probe --trust-hooks` after changing hook commands.
- Re-run `token-accounting all --since-days 7`, `token-accounting-backfill`
  dry-run, and host `abyss-machine ai token-accounting aoa-summary --json`
  after changing token observation, generated ledgers, or the host planning
  bridge.
- Static `hooks/codex-hooks.user.example.json` uses neutral placeholder paths;
  live hooks must still be generated by `hooks-config` or `install`.

2026-06-21 live bounded raw-text search proof:

- `search --query aoa-session-search --doc-type event --use-shards --limit 1
  --query-timeout-ms 1000 --explain` returned `ok=true` in the live archive
  with `rank_mode=bounded_date_order_no_bm25` and the expected
  `search_shard_fanout_raw_text_uses_monolith_fallback` diagnostic, proving the
  structured shard fallback no longer hangs on broad literal FTS.
- `agent-responses --query "task-0040 mechanics parts" --agent-event
  assistant_answer --limit 1 --query-timeout-ms 1000 --explain` returned an
  `assistant_answer` hit with raw and segment refs, proving targeted
  agent-event raw-text recall remains live.
- `agent-responses --query aoa-session-search --agent-event assistant_answer
  --limit 1 --query-timeout-ms 1000 --explain` returned
  `sqlite_query_timeout` with `bounded_timeout.next_expansion_command`, proving
  no-match or too-broad answer queries fail as bounded route packets rather than
  blocking the agent workflow.

2026-06-14 live graph/index repair proof:

- A full live graph repair was run through `abyss-machine resource launch
  --class heavy --kind indexing` with `graph-build all --write --store-only
  --in-place`. It completed successfully in `48min 41.326s`, with `4G` memory
  peak and `531.8M` swap peak. The graph store was rebuilt as
  `3,206,841` nodes, `20,022,161` edges, and `4,185` graph sources.
- The rebuild removed the mass classifier/fingerprint drift:
  `graph-freshness-check --stable --quiet-seconds 120 --write-report`
  reported `ok=true` in
  `diagnostics/20260614T113029Z__graph-freshness-gates.json`.
  Search is `current`, atlas is `current`, refs are `alive`, and graph is
  `current_with_blocked_sources`: `4,124` clean sources, `61` blocked lower
  layer sources, `0` dirty, `0` missing. The blocked group is
  `missing_graph_source_path`; maintenance recommendation is `none` until the
  lower layer evidence is repaired.
- The required follow-up `index-maintenance all --apply --skip-graph-repair`
  repaired the two dirty search/atlas projections in `230.415s`; final search
  and atlas dirty counts are `0`.
- Live scenario probes after repair:
  `entity-usage-neighborhood aoa-session-memory-mcp --kind mcp` found entity
  and MCP route candidates, usage events, consequence events, raw previews, and
  document refs. `graphrag-packet` found graph evidence for the same anchor
  even when lexical entrypoints for the long Russian query returned zero.
  `agent-reasoning-windows aoa-session-memory-mcp` now bridges from
  query-matched assistant answer events to nearby `assistant_reasoning_boundary`
  windows, so reasoning can be inspected even when the boundary event itself
  does not contain the searched entity.
- Weight is still a real pressure point, not solved by rebuild alone:
  `graph/` is about `68G`, `search/` about `16G`, `maps/` about `718M`, and
  `/srv` had about `63G` free at `88%` use after the repair. Full graph rebuild
  is a heavy repair route and should remain resource-gated; normal upkeep
  should prefer incremental graph/index maintenance.

2026-06-14 graph store compact-v2 / OOM recovery proof:

- A later full `graph-build all --write --store-only --in-place` after the
  agent-event/task-episode reindex was resource-gated through
  `abyss-machine resource launch --class heavy --kind indexing`, but the
  kernel OOM killer stopped the unit after about `53m` at `200/272` processed
  records. Because `graph.sqlite3` is a generated read model, the recovery path
  reset only `graph/graph.sqlite3` and rebuilt from preserved session indexes.
- The pre-reset live partial graph baseline was `525.6 MiB`, `19` sources,
  `25,658` nodes, `149,661` edges. `dbstat` showed the weight concentrated in
  contribution payload tables: `edge_contribs=220.8 MiB`,
  `node_contribs=115.1 MiB`, plus aggregate `edges=97.6 MiB` and
  `nodes=41.1 MiB`.
- Graph store schema `2` now writes `compact_column_evidence_refs_v3`
  contribution payloads: repeated absolute refs, route-signal copies inside
  event-node payloads, repeated session refs, repeated raw-block refs, and
  fields already stored as contrib table columns (`id`, `type`, `source`,
  `target`) are removed or bounded while `session_id`, `segment_id`,
  `event_id`, `raw`, segment refs, and enough session refs remain for hydration
  and quality gates.
- The contribution payload mode is part of graph source fingerprints. Payload
  layout changes therefore become normal graph-maintenance drift instead of a
  hidden manual rebuild requirement.
- Live dry proof after the v3 change:
  `graph-maintenance all --plan-refresh-costs --batch-limit 5
  --budget-seconds 180 --refresh-chunk-size 64 --write-report` selected `5`
  sources from a bounded candidate pool of `50`, saw `4725` actionable graph
  sources, and planned `7593` aggregate-node plus `31285` aggregate-edge
  refreshes without mutating `graph.sqlite3`.
- Live size proof on those same `5` selected sources built a temporary graph
  store outside the live projection: `9641` node-contrib rows and `31603`
  edge-contrib rows kept hydrated node/edge evidence while removing redundant
  column fields. Simulated compact-v2 contribution payloads were `34.2 MiB`;
  compact-v3 actual stored contribution payloads were `26.6 MiB`, a `22.15%`
  reduction (`25.88%` for edge contrib payloads, `11.96%` for node contrib
  payloads).
- A bounded live `graph-maintenance all --apply --batch-limit 25
  --refresh-chunk-size 64 --max-refresh-nodes 50000 --max-refresh-edges
  150000 --budget-seconds 300 --write-report` rebuilt the same scale of graph
  evidence in compact-v2: `19` sources, `25,335` nodes, `148,388` edges in
  `80.378s`. The resulting `graph.sqlite3` is `353 MiB`; `dbstat` reports
  `edge_contribs=148.0 MiB`, `node_contribs=39.6 MiB`, `edges=96.8 MiB`, and
  `nodes=17.9 MiB`.
- Live route proof after compaction: `graph-neighborhood validate_playbooks
  --kind script --depth 2 --limit 12` resolved script/entity/validator/path
  graph nodes and hydrated raw/segment/session evidence refs from contribution
  rows. `graphrag-packet --query "validate_playbooks script usage" --anchor
  validate_playbooks --limit 3` returned `ok=true`,
  `answer_rules.status=needs_review`, `important_claim_allowed=true`, and raw,
  segment, and session refs. `graph-quality-audit --anchor
  script:validate_playbooks --limit 3 --sample-ref-limit 3 --write-report`
  returned `ok=true` with no quality flags.
- The strict freshness state at the compact-v2 proof point was intentionally
  partial, not hidden: search and atlas were `current`, refs were `alive`, and
  graph store had `19` clean sources, `4114` missing graph sources, and `62`
  blocked lower-layer sources. Later bounded graph ticks may advance those
  counts. Continue with bounded graph maintenance; do not retry full rebuild by
  default until the weight profile is reduced further.
- 2026-06-21 bounded dry exact-cost proof: after a prior unbounded dry
  `graph-maintenance all --plan-refresh-costs --batch-limit 75` route expanded
  into a large candidate pool and had to be stopped, dry exact-cost planning now
  uses `candidate_pool_policy=bounded_dry_exact_plan`. A live resource-lane run
  selected and priced `75` candidates from `4685` actionable graph sources in
  `elapsed_ms=72829` with `budget_exhausted=false`, `candidate_pool_count=75`,
  `candidate_pool_truncated_count=4610`, `planned_candidate_count=75`, and
  no mutation. The `abyss-machine` wrapper completed in `73.93s` with service
  runtime `1min 13.909s`, memory peak `4G`, and swap `0B`. Report:
  `diagnostics/20260621T185958Z__graph-maintenance.json`.
- 2026-06-28 live queue-drip throughput proof: a real generated-queue
  `graph-maintenance all --apply --batch-limit 25 --budget-seconds 300
  --refresh-chunk-size 64 --max-refresh-nodes 20000 --max-refresh-edges 60000
  --use-queue --candidate-pool-limit 25 --write-report --write-hash-cache`
  completed without rollback or budget exhaustion, but still spent
  `139.226s` for `19` selected sources. The bottleneck was aggregate refresh:
  `102.879s` total, with `node_refresh_ms=31873`,
  `edge_refresh_ms=51188`, `type_count_before_ms=19611`, `213` node chunks,
  and `931` edge chunks. Report:
  `diagnostics/20260628T084212Z__graph-maintenance.json`.
- The bounded graph aggregate refresh chunk was then raised from `64` to `512`
  across source defaults, auto-maintenance profiles, next-action commands, and
  operator docs. A follow-up live queue drip on the same real backlog completed
  in `56.547s` for `18` selected sources, again with no rollback, no
  diagnostics, and no budget exhaustion. Aggregate refresh dropped to
  `27.866s`: `node_refresh_ms=8117`, `edge_refresh_ms=14562`,
  `type_count_before_ms=5013`, `27` node chunks, and `116` edge chunks.
  Queue depth moved from `480` to `462`; the larger backlog remains a bounded
  drain problem, not a reason to run a full rebuild by default. Report:
  `diagnostics/20260628T084949Z__graph-maintenance.json`.
- Post-change validation kept the consumer route green: `validate` and
  `doctor` returned `ok=true`, and
  `live-scenario-corpus check --write-report --full` passed `4/4` reviewed
  scenarios with `actionable_gap_count=0`. The slowest remaining consumer
  profile is `graph_bridge` at `42.082s`; it returned raw, segment, and session
  refs, so the debt is latency rather than evidence loss. Report:
  `diagnostics/20260628T085412Z__live-scenario-corpus-check.json`.
- The follow-up maintenance snapshot surfaced a separate
  `search_shards_not_current` warning: monolith search and the catalog were
  current, but `month/2026-06` had one stale session. This was repaired through
  scoped incremental shard materialization:
  `search-shards all --shard month/2026-06 --no-rebuild --dirty-only
  --write-report --full`, which processed `1` session and `67014` documents in
  `72.752s` without diagnostics. The next `maintenance-status` reported
  `search_shards_status=current`, `materialized=3/3`, `noncurrent=0`; remaining
  warnings were `graph_actionable_sources` and
  `search_projection_combined_large`. Report:
  `diagnostics/20260628T085710Z__search-shards.json`.
- 2026-06-28 hook-worker coordination proof: the next real graph queue drip
  used the same bounded command shape and still completed safely, but regressed
  to `134.322s` for `18` selected sources. Aggregate refresh again dominated:
  `98.425s` total, with `type_count_before_ms=20989`,
  `node_refresh_ms=30893`, and `edge_refresh_ms=46350`. A follow-up
  rollback-only microbench over the same current node/edge set finished in
  about `9-11s`, so the slow path was not explained by row count alone. Nearby
  live evidence showed a large hidden hook worker had just synced a
  `PreCompact` transcript job with `66888` events and `314` segments, while the
  maintenance coordinator did not expose that worker as an active job. The
  `hook-worker` command is now wrapped in the shared maintenance coordinator
  with owner/mode `hook-worker`, target `hook-jobs`, and touched surfaces
  covering `hooks`, `sessions`, `search`, `route_indexes`, `atlas`,
  `entity_registry`, `token_accounting`, and `graph`. Regression proof:
  `test_hook_worker_command_reports_shared_maintenance_lock`; full suite:
  `351 passed`. Installed proof:
  `hook-worker --limit 1` returned `ok=true`, `status=processed`,
  `processed=0`, `coordinator_status=completed`, and
  `maintenance_lock_path=/srv/AbyssOS/.aoa/diagnostics/auto-maintenance.lock`.
  Post-install `validate` and `doctor` returned `ok=true`; `doctor` retained
  only the known hook-only receipt-dir warning. The remaining live status is
  now explicit, not hidden: `graph_actionable_sources` and
  `search_projection_combined_large`, with the next action still
  `repair_graph_queue_drip`.
- 2026-06-28 dense graph-bridge route proof: the next live consumer-loop slice
  confirmed that graph-bridge latency was a first-packet route issue, not
  evidence loss. Baseline `graph-bridge aoa-session-memory-mcp exec_command
  --source-kind mcp --target-kind tool --limit 4 --max-depth 4` returned
  refs but took `46.55s`; new packet timings showed `target_neighborhood`
  alone at `44.555s` against dense `tool:exec_command`. `graph-bridge` now
  builds its first packet from bounded side-neighborhood refs/events, defers
  full `graph-timeline` hydration to the returned expansion commands, and
  records phase timings. The graph-store neighborhood query also avoids the
  dense `source_node = ? OR target_node = ? ORDER BY ...` path for compact
  edge budgets, using split bounded edge reads instead. Source sequential proof
  on the same anchors returned in `1.789s` and `1.739s` internally (`2.4s`
  wall); installed live proof after copying the script to `.aoa` returned in
  `1.059s` internally (`1.73s` wall), with `evidence_ref_count=32`,
  raw/segment/session refs, `side_timelines_deferred=true`, and timeline phases
  at `0ms`. The reviewed `live-scenario-corpus check --write-report --full`
  gate passed `4/4` with `actionable_gap_count=0`; the installed
  `graph_bridge_refs_contract` case dropped to `1.047s` while keeping raw,
  segment, and session refs. A follow-up dirty-only `month/2026-06`
  search-shard refresh processed `2` sessions and `97942` documents in
  `94.061s`, restoring `search_shards_status=current`. Final
  `maintenance-status --full` kept only the known tails:
  `graph_actionable_sources` and `search_projection_combined_large`.
  Regression proof:
  `test_graph_bridge_defers_side_timeline_hydration_when_neighborhood_has_refs`;
  full suite: `352 passed`. Report:
  `diagnostics/20260628T093929Z__live-scenario-corpus-check.json`; shard
  report: `diagnostics/20260628T094708Z__search-shards.json`.
- 2026-06-28 graph queue-report route proof: the next bounded
  `graph-maintenance --use-queue` drip processed `17` selected sources,
  moved the generated queue `444 -> 427`, kept `budget_exhausted=false` and
  `mutation_rolled_back=false`, but took `139.599s` because aggregate refresh
  dominated (`aggregate_refresh_ms=103360`, `node_refresh_ms=36204`,
  `edge_refresh_ms=49257`). That run also exposed a route-surface bug:
  `maintenance-status` kept showing the older global report as the latest
  graph evidence and did not surface the new queue-drip report, because real
  queue reports may include selected `source_keys` while their
  `source_state.selection_scope` remains `selected_sessions`. The queue-report
  selector now recognizes queue drips by `use_queue` plus queue evidence
  (`queue_update`, `queue_path`, or queue selection detail) instead of requiring
  empty `source_keys`. Installed proof after copying the script to `.aoa`:
  `maintenance-status --full` reports
  `latest_queue_maintenance.path=diagnostics/20260628T095408Z__graph-maintenance.json`,
  `selected_count=17`, `queue_removed_count=17`, `queue_queued_count=427`,
  while keeping the global hot-gate `latest_maintenance` separate. Regression
  proof: `test_latest_graph_queue_maintenance_report_prefers_latest_use_queue`.
  The remaining route tails are still explicit:
  `graph_actionable_sources` and `search_projection_combined_large`.
- 2026-06-28 graph queue micro-drip proof: the queue-report route now carries
  `aggregate_refresh_ms` from full graph-maintenance diagnostics through the
  compact `maintenance-status` packet. A live status read of
  `diagnostics/20260628T095408Z__graph-maintenance.json` exposed
  `elapsed_ms=139599` and `aggregate_refresh_ms=103360`; the next action
  switched from ordinary queue drip to `repair_graph_queue_micro_drip` with
  `--batch-limit 10`, `--max-refresh-nodes 10000`, and
  `--max-refresh-edges 30000`. Running that exact live micro-drip wrote
  `diagnostics/20260628T101255Z__graph-maintenance.json`, processed `8`
  selected sources, moved the queue `427 -> 419`, kept rollback and budget
  exhaustion false, and reduced aggregate refresh to `79012ms` for
  `6524` planned nodes and `27730` planned edges. Because the run still took
  `104712ms`, the practical slow queue-drip threshold now keeps the next
  action on `repair_graph_queue_micro_drip` instead of bouncing back to a
  larger drip too early. Regression proof:
  `test_graph_status_preserves_latest_queue_aggregate_refresh_ms`,
  `test_graph_maintenance_report_aggregate_refresh_ms_reads_real_queue_timing`,
  and `test_maintenance_next_actions_micro_drips_after_slow_queue_aggregate_refresh`.

- 2026-06-28 search projection cardinality plan proof: after targeted live
  search catch-up, `index-maintenance
  2026-06-12__001__на-машине-есть-раскиданный-abyss-machine --apply
  --skip-graph-repair --skip-token-accounting --write-report` repaired the
  single deferred search session in `66488ms`, then `search-shards all --shard
  month/2026-06 --no-rebuild --dirty-only --write-report` repaired the stale
  structured shard row in `70838ms` (`69071` documents, `68496` event
  documents). With search and shards current, `search-projection-plan
  --write-report` returned from cached summaries with
  `status=large_projection_stack`, `freshness_status=current`,
  `actionability=actionable_design_lane`, combined search projection
  `15.8 GiB`, document hotset `1888501`, and next route
  `design_compact_operational_event_projection`. `maintenance-status --full`
  now exposes `agent_route.search_projection_action_pending=true` and appends
  `plan_search_projection_cardinality` after the graph micro-drip action. This
  is intentionally a planning route, not a weight fix: it prevents future
  agents from treating SQLite vacuum, full-text shards, or broad monolith
  `GROUP BY` scans as the solution to structured event cardinality. Fast route
  proof after the plan:
  `agent-responses --agent-event assistant_answer --use-shards --limit 5`
  returned through `materialized_shard_fanout` with `uses_fts=false`,
  `hydrates_body=false`, `uses_shards=true`, and empty diagnostics. Deep
  measurement proof remains intentionally red:
  `performance-baseline assistant_answer --kind agent_event --limit 5`
  reported `answer_rule_gate:stale`, `search_fts_query_timeout:8000ms`, and
  `sqlite_query_timeout:interrupted`, making GraphRAG/raw-text paths the next
  measurement target rather than a green gate for this search projection plan.
  Follow-up route-family correction: `performance-baseline --kind agent_event`
  now measures the structured `agent_event_route` through `agent-responses`
  instead of treating `assistant_answer` as an operational entity and opening
  entity usage plus GraphRAG. Live source proof returned `ok=true` in `722ms`
  (`agent_event_route=535ms`), `result_count=5`, `uses_shards=true`,
  `uses_fts=false`, `hydrates_body=false`, five raw refs, five segment refs,
  and `freshness_counts={"fresh":5}`. The live-tail shard diagnostic
  `search_shard_fanout_using_structured_nonmaterialized_shards:1` is preserved
  as a warning rather than a blocking diagnostic.
  A post-install live-tail recheck kept the action visible with
  `search_shards_status=current_with_deferred_live_updates` and
  `search_projection_action_pending=true`; the same `agent-responses` route
  remained `ok=true` with a `search_shard_fanout_using_structured_nonmaterialized_shards:1`
  diagnostic for the newest nonmaterialized shard instead of hiding the
  cardinality plan.

- 2026-06-29 search hotset audit proof: `search-hotset-audit --max-shards 3
  --per-shard-timeout 8 --top-limit 12 --write-report` now provides the fast
  shard breakdown between the cached `search-projection-plan` and the heavier
  operational projection planner. The live run wrote
  `diagnostics/20260629T051751Z__search-hotset-audit.json`, returned
  `ok=true`, `status=hotset_measured`, `successful_shard_count=3`, empty
  diagnostics, and completed in `13753ms` without opening the monolith or using
  FTS. Across the April/May/June structured shards it measured `1,889,196`
  documents, `1,874,956` event docs (`99.2462%`), `654,790` context events,
  `458,996` generic context-tail candidates, and agent-event coverage
  `covered`: `446,851` eligible assistant/reasoning/agent-state events,
  `446,851` classified, `0` missing. The `1,428,105` event rows without
  `agent_event` are intentionally outside that lane and route through
  `usage_role`, `event_type`, `session_act`, and route signals instead of being
  treated as an `agent_event` classification gap. The pressure focus is
  therefore event document cardinality, context-tail projection pressure, and
  the remaining monolith raw-text fallback dependency, not SQLite vacuum,
  full-text shard expansion, or blanket agent-event relabeling. Regression proof:
  `test_search_hotset_audit_breaks_down_structured_shard_pressure_without_monolith`,
  `test_search_projection_plan_uses_cached_projection_summaries`, and
  `test_search_operational_projection_plan_samples_candidate_tail_without_mutation`.

- 2026-06-28 operational event projection measurement proof:
  `search-operational-projection-plan --max-shards 2 --per-shard-timeout 5
  --write-report` sampled the two largest structured shard DBs in about
  `4.85s` wall time and wrote
  `diagnostics/20260628T113120Z__search-operational-projection-plan.json`.
  The packet returned `status=candidate_tail_measured`, `ok=true`,
  `mutates=false`, and `successful_shard_count=2`. Across sampled May/June
  shards it found `1572436` event docs, `996874` direct
  usage/result/outcome/entrypoint docs, `575562` context docs, and `407178`
  generic context-tail candidates (`25.8947%` of sampled events). Crucially,
  `320271` of those candidates still carry route-signal previews
  (`78.6563%` of the candidate tail), so the next design route is
  `design_route_ref_preserving_operational_event_rollup`, not row deletion,
  SQLite vacuum, or full-text shard expansion. Regression proof:
  `test_search_operational_projection_plan_samples_candidate_tail_without_mutation`
  and `test_search_projection_plan_uses_cached_projection_summaries`.

- 2026-06-28 route-ref rollup proof: the operational event projection planner
  now includes a bounded route-ref rollup over candidate context-tail rows.
  After replacing the broad aggregate CTE with smaller index-friendly counts and
  deriving exact route posting totals from the full route-layer aggregate,
  `search-operational-projection-plan --max-shards 2 --route-rollup-limit 8
  --write-report` used the default `per_shard_timeout_seconds=12.0`, returned
  `ok=true`, `status=candidate_tail_measured`, `successful_shard_count=2`, and
  wrote `diagnostics/20260628T121146Z__search-operational-projection-plan.json`.
  The live May/June sample found `1,573,103` event docs, `407,305` generic
  context-tail candidates, `320,394` candidates with route signals, `858,883`
  candidate route postings, and `43,630` sampled route terms. Top rollup layers
  were `resource_profile`, `entity`, `path`, `confidence`, `tool`,
  `mutation_surface`, `authority_surface`, and `mechanic`; the top terms include
  `resource_profile:context_token_count`, `confidence:low_structural_confidence`,
  `tool:namespace_codex_developer_tool`, and `tool:apply_patch`. The packet now
  reports `core_elapsed_ms`, shard total `elapsed_ms`, and
  `route_ref_rollup.elapsed_ms`; the sampled route-rollup elapsed total was
  `3861ms` and the wall command completed in about `10s`. Full verification:
  bundle pytest `359 passed`, active pytest `352 passed`, bundle `validate
  ok=true`, and active `doctor ok=true status=current`. Active
  `maintenance-status --full` remains `ok=false` only for existing graph backlog
  and the large search projection warning; search shards are current and this
  planner is the documented design route for that projection pressure.

- 2026-06-28 operational route-rollup materialization proof:
  `search-operational-route-rollup --max-shards 2 --per-shard-timeout 30
  --ref-sample-limit 2 --apply --write-report` materialized the generated
  replacement read-model at `search/operational-route-rollup.sqlite3`. The
  rerun proof wrote
  `diagnostics/20260628T122847Z__search-operational-route-rollup.json`,
  returned `ok=true`, `status=current`, `written=true`, empty diagnostics, and
  completed in `11210ms`. The DB is `24.5 MiB`, has `43,630` route-rollup
  rows across the May/June shards, `858,883` candidate route postings, and
  sampled raw plus segment refs for every route term. Only the main SQLite file
  remains after the repeat apply; stale target `-wal`/`-shm` sidecars are
  removed around the atomic replace. This is still generated navigation rather
  than authority: raw transcripts and segment refs remain the proof route, and
  physical context-tail shrinkage remains blocked until this projection proves
  fresh and useful as the replacement route. Regression proof:
  `test_search_operational_route_rollup_materializes_ref_samples`, bundle
  focused pytest `3 passed`, active focused pytest `2 passed`, and active
  script equals the bundle script.

- 2026-06-28 operational route-rollup status proof: `maintenance-status --full`
  now surfaces `operations.search_pressure.operational_route_rollup` as a
  read-only freshness packet derived from the materialized rollup DB and its
  source shard size/mtime evidence. A live active-script check returned
  `search_pressure.status=large_projection_stack`,
  `operational_route_rollup.status=current`, `needs_refresh=false`, `43,630`
  route rows, `858,883` candidate route postings, `24.5 MiB` size, and sampled
  raw/segment terms for all rollup rows. The search projection next-action now
  becomes `use_operational_route_rollup_projection` with route kind
  `search_operational_route_rollup_ready` instead of repeating
  `plan_search_projection_cardinality`. The command still exits non-zero while
  graph maintenance is pending, but that is unrelated graph backlog, not a
  route-rollup failure. Regression proof:
  `test_operational_route_rollup_status_tracks_source_shard_freshness`,
  `test_search_projection_next_action_requires_current_large_projection`, and
  active `test_search_projection_next_action_prefers_route_rollup_over_repeated_plan`.
  The route-aware plan proof is
  `diagnostics/20260628T124004Z__search-projection-plan.json`, where
  `search-projection-plan` returned `actionability=replacement_route_ready`,
  `next_route=use_operational_route_rollup_before_physical_shrinkage`, and
  candidate lane `compact_operational_event_projection` with
  `status=route_rollup_ready`.
  Auto-update proof: `index-maintenance` now plans
  `refresh_operational_route_rollup` when the generated rollup is missing or
  stale and search shards are current. A live active-script dry-run
  `index-maintenance all --skip-graph-repair --skip-token-accounting
  --budget-seconds 45 --write-report` wrote
  `diagnostics/20260628T125144Z__index-maintenance.json`, kept
  `operational_route_rollup_repair_needed=false` because the real rollup was
  already current, and reported both initial and final rollup status as
  `current`. The missing/stale apply branch is covered by
  `test_index_maintenance_refreshes_missing_operational_route_rollup`, which
  proves the action moves `final_operational_route_rollup.status` to `current`
  through the normal maintenance pipeline.

- 2026-06-29 operational projection / route-rollup sync proof:
  `search-operational-projection-plan --max-shards 3 --per-shard-timeout 8
  --route-rollup-limit 12 --write-report` now keeps sampled context-tail
  pressure separate from the current materialized replacement read-model. The
  live run wrote
  `diagnostics/20260629T083242Z__search-operational-projection-plan.json`,
  returned `ok=true`, `status=candidate_tail_measured`, and, despite two
  bounded shard probe timeouts, reported
  `route_ref_rollup_plan.status=materialized_rollup_ready`,
  `replacement_read_model_status=ready`, materialized rollup size `31.4 MiB`,
  `51,676` route rows, `977,275` materialized route postings, and
  `source_mismatch_count=0`. Sampled candidate counts remain pressure evidence:
  the measured shard showed `51,683` candidate context-tail rows and `118,386`
  sampled candidate route postings. The next design route is now
  `design_physical_context_tail_shrink_using_materialized_route_rollup_guard`
  rather than another route-rollup build. Physical compaction is still not safe
  from this packet alone; raw/segment refs remain authority. Regression proof:
  `test_search_operational_projection_plan_samples_candidate_tail_without_mutation`.
  Follow-up live proof
  `diagnostics/20260629T085037Z__search-operational-projection-plan.json`
  added the explicit `physical_shrink_plan` packet. It reported
  `status=guarded_plan_ready`, `safe_to_apply_physical_compaction=false`,
  `apply_status=not_implemented`, `51,683` sampled context-tail candidates,
  `45,913` route-ref-backed omission candidates, `5,770` unrouted keep
  candidates, route-ref coverage `0.888358`, materialized rollup `current`,
  `51,676` rollup rows, and `977,275` materialized route postings. The same
  run kept two bounded shard-probe timeouts in diagnostics, so this remains a
  partial pressure sample plus current materialized rollup proof, not a claim
  that physical shrink is safe. Required gates are now named in the packet:
  live scenario corpus, search-hotset before/after, route-rollup ref check,
  literal exact-recall check, agent-event route regression, storage before/after,
  and bundle parity.
  Follow-up gate proof
  `diagnostics/20260629T090557Z__search-operational-shrink-gates.json` added
  the read-only `search-operational-shrink-gates` route and connected
  `maintenance-status` next action to `run_operational_shrink_gates` while the
  rollup is current. The live gate returned `ok=true`,
  `status=blocked_before_apply`, `apply_ready=false`, passed
  `projection_guard`, `route_rollup_refs`, `agent_route_lane_coverage`,
  `literal_exact_recall`, `live_scenario_corpus`, and `storage_baseline`, with
  no failed gates. It blocked `storage_before_after_comparison` and
  `explicit_apply_route`, which is the intended posture before a real generated
  search omission/apply path exists. The two bounded shard-probe timeouts remain
  visible as diagnostics, so the gate is live route evidence, not a claim of
  full archive cardinality coverage.
  After the Gmail heavy-tail shard was repaired and the rollup was refreshed,
  `diagnostics/20260629T200720Z__search-operational-shrink-gates.json`
  returned the same guarded posture with current sources: `ok=true`,
  `status=blocked_before_apply`, `apply_ready=false`, no failed gates,
  `470723` context-tail candidates, `377579` route-ref-backed omission
  candidates, `93144` unrouted keep candidates, current rollup size `32.8 MiB`,
  `53583` rollup rows, and `1027653` candidate route postings. This proves the
  next weight-reduction step is an explicit generated-search omission policy
  with before/after storage and recall gates, not physical SQLite compaction or
  raw fallback removal.
  Follow-up code slice added that explicit structured-shard policy:
  `search-shards --context-tail-omission-policy route-ref-backed` omits only
  route-ref-backed generated context-tail event rows from structured shards,
  keeps agent-event, task-episode, protected context, and unrouted context-tail
  rows, refuses `--full-text`, and records `context_tail_omission` counts in
  shard reports and search DB metadata. Live gate
  `diagnostics/20260629T202328Z__search-operational-shrink-gates.json`
  returned `ok=true`, `status=blocked_before_apply`, `apply_ready=false`,
  passed `explicit_apply_route`, and now blocks only
  `storage_before_after_comparison`. The next live step is an operator rebuild
  through the explicit policy followed by before/after storage and recall
  comparison; raw/segment evidence and monolith raw-text fallback remain
  authority.
  2026-06-30 sticky maintenance repair: `search-shards` now defaults
  context-tail omission selection to `auto`. Fresh shards resolve to
  `keep_all_context_tail_v1`, but dirty-only/incremental refresh inherits an
  existing shard `search_context_tail_omission_policy` from SQLite metadata.
  Live scoped repair on `month/2026-06` with explicit `route-ref-backed`
  processed `1` stale/deferred session, indexed `5462` documents, omitted
  `1071` generated context-tail documents, and stored `2713` omitted route-ref
  rows in `diagnostics/20260630T023319Z__search-shards.json`. A following
  ordinary no-policy dirty-only run wrote
  `diagnostics/20260630T023632Z__search-shards.json` with
  `requested_context_tail_omission_policy=auto`,
  `context_tail_omission_policy=route_ref_backed_context_tail_v1`,
  `context_tail_omission_policy_resolution.source=existing_shard_meta`, and
  `status=no_dirty_sessions`; this proves routine maintenance no longer
  silently rolls the shard back to keep-all after a slim rebuild.
  The follow-up bounded `index-maintenance` catch-up report
  `diagnostics/20260630T023913Z__index-maintenance.json` returned `ok=true`
  with `search_shards.status=current`, `deferred_live_session_count=0`, and all
  three materialized shards (`month/2026-04`, `month/2026-05`,
  `month/2026-06`) exposing
  `context_tail_omission_policy=route_ref_backed_context_tail_v1`.
  Follow-up regression repair added compact omitted route-ref preservation:
  route-backed omitted context-tail rows are now stored in
  `omitted_context_tail_route_refs`, search schema advanced to `14`, and
  operational route-rollup aggregates both remaining candidate `documents`
  rows and that compact sidecar. Regression tests:
  `test_search_index_sessions_applies_explicit_context_tail_omission_policy`
  now checks the compact sidecar, and
  `test_search_operational_route_rollup_preserves_omitted_context_tail_refs`
  proves post-omission rollup refs survive. Live rebuild through
  `abyss-machine resource launch --class medium --kind indexing` completed in
  `2153806ms` (`35min55s`, memory peak `4G`, swap `338.2M`), processed `288`
  sessions, omitted `377579` generated context-tail documents, and wrote
  `1027653` compact omitted route-ref rows. `search-schema-migrate` upgraded
  the monolith and all three shards to schema `14`; refreshed
  `search-operational-route-rollup` produced `53583` rows, `1027653` candidate
  route postings, current source status, and a `32.8 MiB` read-model. Final
  live reports `diagnostics/20260629T220331Z__maintenance-status.json` and
  `diagnostics/20260629T220457Z__search-operational-shrink-gates.json`
  returned `ok=true`: search, graph, entity registry, and rollup are current;
  shrink gates pass projection, route refs, agent route lane coverage, literal
  exact recall, live scenario corpus, storage baseline, and explicit apply
  route, while still blocking only `storage_before_after_comparison`.
  Follow-up auto-maintenance route repair fixed the stale-rollup clean-skip
  gap: `route-cache-freshness-gates` now reports
  `operational_route_rollup_repair_needed=true` when structured shards are
  current but the materialized rollup is stale/source-mismatched, and
  `auto-maintenance-resource hot all --apply --skip-graph-repair` no longer
  presents child `skipped_lock_held` as a completed repair. Live proof:
  `diagnostics/20260629T223907Z__auto-maintenance-resource-hot.json` wrapped
  child status `applied_with_deferred_live`; the child
  `diagnostics/20260629T223907Z__auto-maintenance-hot.json` applied
  `refresh_operational_route_rollup` in `121148ms` and moved
  `final_operational_route_rollup.status` to `current` with
  `source_mismatch_count=0`. Final route query and route-cache checks returned
  rollup `current`, `needs_refresh=false`, and the next shrink-gate report
  returned `ok=true`, `status=blocked_before_apply`, with all quality gates
  passing and only `storage_before_after_comparison` blocked.
  Follow-up guarded apply route added
  `search-operational-shrink-apply`: it runs the shrink-gate preflight,
  structured shard omission rebuild, route-rollup refresh, rollup ref query,
  live scenario corpus, and before/after storage comparison in one operator
  packet. Live apply
  `diagnostics/20260629T235453Z__search-operational-shrink-apply.json`
  completed in `2199188ms`, rebuilt `290` sessions, produced `1579266`
  structured shard documents, omitted `377900` route-ref-backed generated
  context-tail documents, and wrote `1028878` compact omitted route-ref rows.
  The refreshed rollup stayed current with `53721` rows and `1028878`
  candidate route postings; route-rollup query and one-case live scenario
  corpus both passed without opening monolith, FTS, or body hydration. The
  first comparison exposed a measurement bug: catalog counts still reflected
  stale monolith/freshness document counts even though shard DBs had the new
  post-omission counts. The repair makes current/existing shard DB counts the
  physical-cardinality source for shard projection summaries, records
  `document_count_source`, preserves monolith/freshness counts separately, and
  leaves catalog mismatches visible as diagnostics such as
  `shard_document_count_catalog_mismatch:month/2026-06`. Live verification
  after `search-catalog --refresh --write-report` shows snapshot
  `search_shards.document_count=1579266`,
  `status=current_with_deferred_live_updates`, April/May matching catalog and
  DB counts, and June counted from the existing shard DB while one deferred-live
  catalog row remains stale. Physical bytes did not decrease after the rebuild,
  so future wrapper reports use `applied_with_storage_warning` when the route
  is otherwise good but storage bytes do not shrink; this is a cardinality/ref
  win, not a proven physical weight win.
  Follow-up guarded apply proof
  `diagnostics/20260630T033731Z__search-operational-shrink-apply.json`
  completed the route with `status=applied`, rebuilt `291` sessions, produced
  `1579290` structured shard documents, omitted `377900` route-ref-backed
  context-tail documents, and captured a physical generated-search reduction:
  shard DB bytes `5259296768 -> 5226123264`, combined search projection bytes
  `17088774144 -> 17055600640`, and search root bytes
  `17124258884 -> 17090845447`; the monolith stayed unchanged. The read-only
  gate report `diagnostics/20260630T034830Z__search-operational-shrink-gates.json`
  now consumes that latest apply diagnostic as
  `latest_shrink_apply_proof.status=found`, passes
  `storage_before_after_comparison`, returns `blocked_gate_ids=[]`, and keeps
  `apply_ready=false` / `safe_to_apply_physical_compaction=false` because the
  gate is evidence, not an authorization route. The live gate elapsed
  `171317ms`, making route-cost reduction the next pressure. The follow-up
  fast-path proof
  `diagnostics/20260630T040758Z__search-operational-shrink-gates.json` keeps
  the same gate result (`ok=true`, `blocked_gate_ids=[]`,
  `storage_before_after_comparison=pass`) but uses
  `projection_plan_source=latest_shrink_apply_proof` with
  `cost_profile.resamples_shards=false`. The live elapsed time dropped to
  `6078ms`; phase timings show `projection_plan=211ms`,
  `route_rollup_query=862ms`, `literal_exact_recall=451ms`,
  `live_scenario_corpus=874ms`, and `storage_baseline=3552ms`. Fresh heavy
  shard sampling remains available through `search-operational-projection-plan`
  when an agent needs new unrouted-tail counts rather than the latest apply
  proof.

- 2026-06-28 operational route-rollup query proof:
  `search-operational-route-rollup-query` is now the fast consumer route over
  the materialized `search/operational-route-rollup.sqlite3` read-model. It
  reads the existing DB instead of resampling structured shards, aggregates
  route rows by `layer/key/route_signal`, and returns raw, segment, and session
  refs plus a cost profile. Live query without filters over the current
  `31.4 MiB` rollup returned `ok=true`, `status=matched`, `result_count=5`,
  `matched_group_count=39328`, and `elapsed_ms=532`; filtered live query for
  `tool/exec_command` returned one route row with `posting_count=781`, raw and
  segment refs, and `elapsed_ms=12`. In both packets
  `resamples_shards=false`, `opens_monolith=false`, `uses_fts=false`, and
  `hydrates_body=false`. `maintenance-status` now points
  `use_operational_route_rollup_projection` at
  `search-operational-route-rollup-query --limit 12 --ref-limit 3
  --write-report`; materialization remains the repair route for missing or
  stale rollups. Regression proof:
  `test_search_operational_route_rollup_query_reads_materialized_projection`,
  updated `test_search_projection_next_action_requires_current_large_projection`,
  source pytest `371 passed`, standalone bundle pytest `371 passed`, source
  `validate ok=true`, standalone `validate ok=true`, and portable-bundle audit
  `ok=true`.

- 2026-06-28 route-rollup consumer scenario proof:
  `live-scenario-audit --profile route_rollup_query --limit 3` returned
  `ok=true`, `scenario_count=1`, `passed_count=1`, `elapsed_ms=9`,
  `raw_or_segment_ref_scenario_count=1`, raw/segment/session ref counts of
  `3/3/3`, `freshness_status=current`, `uses_materialized_route_rollup=true`,
  and `resamples_shards=false`, `opens_monolith=false`, `uses_fts=false`,
  `hydrates_body=false`. The reviewed live scenario corpus now includes
  `route_rollup_query_materialized_contract`; `live-scenario-corpus check
  --case-limit 12` returned `12/12` passed with `actionable_gap_count=0`.
  The `aoa-session-memory-evidence-route` skill also routes
  `use_operational_route_rollup_projection` to
  `search-operational-route-rollup-query` / `aoa_session_route_rollup_query`
  before broad search or raw expansion.

- 2026-06-29 route-rollup agent-route summary proof:
  `search-operational-route-rollup-query --limit 6 --ref-limit 2
  --write-report` now returns `agent_route_summary` over the current
  materialized `31.4 MiB` rollup instead of making agents infer useful lanes
  from the unfiltered top rows. Live report
  `diagnostics/20260629T052937Z__search-operational-route-rollup-query.json`
  returned `ok=true`, `status=matched`, `freshness_status=current`,
  `agent_route_summary.status=covered`, `covered_lane_count=18`,
  `missing_lane_count=0`, `resamples_shards=false`, `opens_monolith=false`,
  `uses_fts=false`, and `hydrates_body=false` with `elapsed_ms=2122`.
  Covered lanes include tools, skills, MCP, hooks, APIs, plugins, goals,
  answers, errors, tests, validators, decisions, memory surfaces, graphs,
  evals, scripts, mechanics, and agents. The packet includes lane-specific
  rollup commands and dedicated first routes for goals, answers, and graphs,
  while keeping raw/segment refs as authority. Regression proof:
  `test_search_operational_route_rollup_query_reads_materialized_projection`
  now checks `agent_route_summary`, lane coverage, top keys, and dedicated
  route commands; `test_live_scenario_result_enforces_route_rollup_query_cost_contract`
  warns when the route-rollup query packet loses the agent-route summary. Live
  scenario proof:
  `diagnostics/20260629T053144Z__live-scenario-audit.json` returned
  `passed_count=1`, `warn_count=0`, `first_useful_packet_ms=1375`,
  `agent_route_summary_status=covered`, and
  `agent_route_covered_lane_count=18`. Corpus proof:
  `diagnostics/20260629T053327Z__live-scenario-corpus-check.json` returned
  `case_count=12`, `passed_count=12`, `failed_count=0`, and
  `actionable_gap_count=0`.

- 2026-06-30 promoted agent-route rollup proof: route-rollup materialization now
  includes protected `goal`, `agent_event`, and `decision_thread` route layers
  in addition to context-tail and omitted sidecar refs. The full live rebuild
  `diagnostics/20260630T020435Z__search-operational-route-rollup.json`
  returned `ok=true`, `status=current`, `route_rollup_row_count=53847`, and a
  still-compact `32.9 MiB` DB while adding typed `decision_thread` and
  `agent_event` navigation. Live `search-operational-route-rollup-query decision
  --layer decision_thread --limit 5 --ref-limit 3 --write-report` returned
  `ok=true`, `status=matched`, `result_count=5`, `freshness_status=current`,
  `raw_or_segment_ref_present=true`, `resamples_shards=false`,
  `opens_monolith=false`, `uses_fts=false`, and `hydrates_body=false` in
  `457ms`; the decision lane had `exact_layer_group_count=7` and
  `term_match_group_count=0`. A broad `decisions` query now returns
  `query_route_advice.status=typed_lane_detected` with recommended layer
  `decision_thread`, preventing path/entity decision-document noise from being
  treated as the lane result. The reviewed live corpus now includes
  `route_rollup_decision_thread_contract`; live corpus proof
  `diagnostics/20260630T020743Z__live-scenario-corpus-check.json` returned
  `case_count=14`, `passed_count=14`, `failed_count=0`, and
  `actionable_gap_count=0`. Manual operator-style route proof
  `diagnostics/20260630T021611Z__live-scenario-audit.json` returned
  `passed_count=1`, `first_useful_packet_ms=375`, `layer_counts` containing only
  `decision_thread`, raw/segment/session refs, and no monolith/FTS/raw-body
  hydration.

- 2026-06-29 route-rollup canonical human-anchor proof:
  `search-operational-route-rollup-query aoa-session-memory-mcp --layer mcp
  --limit 3 --ref-limit 1 --write-report` now canonicalizes the human anchor
  to `normalized_filters.query_terms=["aoa-session-memory-mcp",
  "aoa_session_memory_mcp"]` and returns the current materialized MCP route row
  `mcp:aoa_session_memory_mcp` without shard resampling, monolith reads, FTS,
  or raw-body hydration. Live report
  `diagnostics/20260629T062417Z__search-operational-route-rollup-query.json`
  returned `ok=true`, `status=matched`, `result_count=2`,
  `freshness_status=current`, `agent_route_summary_status=covered`,
  `covered_lane_count=18`, and first evidence refs
  `raw:line:27697`,
  `136__compaction-to-compaction.md#event-027697--security_touchpoint--tool-output-call_bdoxqrgjyp3qamrir8hxx2iv`,
  session `019edd27-0d1b-7d83-ad01-c7c72effc9bc`. The profile live proof
  `diagnostics/20260629T062417Z__live-scenario-audit.json` returned
  `passed_count=1`, `warn_count=0`, `first_useful_packet_ms=1363`,
  `uses_materialized_route_rollup=true`, `opens_monolith=false`,
  `uses_fts=false`, and `hydrates_body=false`. The reviewed corpus gate
  `diagnostics/20260629T062448Z__live-scenario-corpus-check.json` returned
  `case_count=12`, `passed_count=12`, `failed_count=0`, and
  `actionable_gap_count=0`. A direct live MCP call through the exposed
  operational rollup tool also returned `status=matched`,
  `normalized_filters.query_terms=["aoa-session-memory-mcp",
  "aoa_session_memory_mcp"]`, `mcp_access.response_compacted=true`, and
  `mcp_access.does_not_materialize_rollup=true`.

- 2026-06-30 maintenance route ordering proof: `maintenance-status --full`
  no longer lets stale operational route-rollup hide behind generic
  `index-maintenance all` or graph-only live-tail catch-up. A live stale rollup
  first exposed `materialize_search_operational_route_rollup`, then after a
  targeted search live-tail catch-up exposed a scoped
  `search-operational-route-rollup --shard month/2026-06 --apply
  --write-report` route. The scoped replacement returned `ok=true`,
  `status=current`, and `elapsed_ms=88132`; follow-up graph queue live catch-up
  returned `ok=true`, `selected_count=23`, `remaining_count=0`,
  `budget_exhausted=false`, and `elapsed_ms=14334`. Final
  `maintenance-status --full` returned `ok=true`,
  `recommendation=use_graph_search`, `route_diagnostics=[]`,
  `rollup_status=current`, `search_deferred=0`, and graph actionable count
  `0`; `live-scenario-corpus check --write-report` returned `case_count=14`,
  `passed_count=14`, `failed_count=0`, and `actionable_gap_count=0`.
  Regression coverage now checks that rollup repair outranks generic
  `index-maintenance all`, graph-only live catch-up does not hide rollup
  repair, and current-rollup shrink gates remain read-only advisory actions
  rather than blocking maintenance.

- 2026-06-28 graph queue aggregate-refresh tail reduction: live graph queue
  reports showed that the remaining interactive cost was dominated by
  `replace_sources` aggregate refresh, especially edge representative payload
  scans over large `edge_contribs` windows. Incremental refresh now keeps fresh
  representative payloads for low-cardinality node ids, reuses existing compact
  aggregate payloads for high-fanout nodes, and disables representative payload
  scans for edge aggregates because edge `source`/`target`/`type`/count come
  from the summary and evidence refs hydrate from `edge_contribs` at packet
  read time. Live proof before the edge route fix:
  `diagnostics/20260628T190807Z__graph-maintenance.json` took `128.919s`
  with `aggregate_refresh_ms=97180`; after bounded node representative reuse,
  `diagnostics/20260628T191905Z__graph-maintenance.json` took `114.187s`
  with `aggregate_refresh_ms=83834`; after disabling edge representatives,
  `diagnostics/20260628T192135Z__graph-maintenance.json` took `46.449s`
  with `aggregate_refresh_ms=18176`, `node_refresh_ms=4247`,
  `edge_refresh_ms=10866`, and `edge_refresh.representative_payload_count=0`.
  `maintenance-status --no-timers` now surfaces the latest queue maintenance
  as `elapsed_ms=46449`, `aggregate_refresh_ms=18176`, and moves the next
  graph action back from micro-drip to ordinary queue drip while search,
  entity registry, and operational route-rollup remain current. Route proof:
  `graph-neighborhood aoa-session-memory-mcp --kind mcp --limit 4
  --edge-limit 12` returned a compact stale-aware graph packet with raw/segment
  refs, and `usage-chain aoa-session-memory-mcp --kind mcp --limit 2` returned
  `ok=true`, `event_count=2`, `consequence_event_count=7`,
  `evidence_ref_count=24`, and search freshness `current`. Regression proof:
  source `py_compile` passed; targeted graph refresh tests passed; full source
  pytest returned `374 passed`; source `validate` returned `ok=true`; source
  `doctor` returned `ok=true`; standalone bundle `py_compile` passed, bundle
  pytest returned `374 passed`, bundle `validate` returned `ok=true`, and
  bundle `doctor` returned `ok=true` with the expected installed user-skill
  symlink still pointing at the live `.aoa` source rather than the Git mirror.

- 2026-06-30 targeted search-hotset measurement proof: the broad
  `search-hotset-audit --max-shards 3 --top-limit 12 --write-report` route
  returned `ok=true` and `status=hotset_partially_measured` because optional
  breakdown queries on the largest shards hit bounded timeout guards. The
  packet now exposes `measurement_gap` and targeted
  `search-hotset-audit --shard <key>` follow-up commands instead of leaving
  the agent with a non-operational warning. Live targeted proof on
  `month/2026-05` returned `ok=true`, `status=hotset_measured`,
  `sample_quality.status=exact_sample`, `document_count=698009`,
  `event_document_count=692076`, and no monolith/FTS/raw opening in `3554ms`.
  Targeted proof on `month/2026-06` also returned exact counts while the shard
  remained `current_with_deferred_live_updates` due to a quiet-window live
  tail, which is a freshness boundary rather than a broken stable archive. The
  operational projection report
  `diagnostics/20260630T075423Z__search-operational-projection-plan.json`
  measured `candidate_context_tail_v1_count=471084` across the sampled shards,
  with `377900` of those carrying route signals and
  `candidate_route_posting_count=1028878`. This confirms the next weight work
  belongs to compact operational-event/read-model design, not blind SQLite
  vacuum or monolith deletion. Regression coverage now checks parser support
  for `search-hotset-audit --shard` and verifies that partial hotset samples
  return a targeted measurement gap route.

- 2026-06-30 targeted hotset to operational projection handoff proof:
  targeted `search-hotset-audit --shard month/2026-06 --max-shards 1`
  correctly sampled `month/2026-06`, but the old deeper next route only carried
  `search-operational-projection-plan --max-shards 1`; live repro showed that
  command selected the larger `month/2026-05` shard instead. The handoff now
  preserves shard scope: targeted hotset packets emit
  `search-operational-projection-plan --shard month/2026-06 --max-shards 1`,
  and the operational projection command itself accepts `--shard`. Live proof
  after the fix returned `target_shard=month/2026-06`,
  `selected_shards[0].shard=month/2026-06`, `event_total=762495`,
  `candidate_context_tail_v1_count=168527`, and
  `candidate_context_tail_with_route_signals_count=145859` in
  `diagnostics/20260630T082129Z__search-operational-projection-plan.json`.
  Regression coverage now checks parser support, targeted hotset next-route
  propagation, and operational projection shard selection against a competing
  larger shard.

## Probe Notes

Two live `codex exec` probes confirmed that `SessionStart`, `UserPromptSubmit`,
and `Stop` hooks are captured by the installed user-level hooks.

A separate low-threshold compaction probe using a deliberately tiny
`model_auto_compact_token_limit` did not produce `PreCompact`/`PostCompact`.
Instead, the agent repeated the harmless tool call until the probe was stopped.
Do not treat low-threshold `codex exec` as a reliable live compaction trigger.
The completed live gate used Codex app-server `thread/compact/start`, not the
low-threshold `codex exec` route. This produced native `hook/started` and
`hook/completed` events for `preCompact` and `postCompact`, and the AoA archive
recorded `PreCompact=2` and `PostCompact=2` after the latest repeatable probe.

## Rule

Do not mark future changes complete from tests alone. Re-run the audit and keep
the prompt-to-artifact checklist green.
