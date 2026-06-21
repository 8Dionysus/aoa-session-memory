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
  monolith `127.63s`)
- Generated entity registry: `entity-registry`,
  `maps/entity-registry.json`, `doc_type=entity_registry`, active/observed/
  stale/removed/unknown states for skills, MCP services/tools, tools, APIs,
  hooks, scripts, validators, tests, evals, playbooks, techniques, mechanics,
  graph, and memory surfaces; MCP access is read-only
- Entity usage fast path: `entity-usage-audit` starts from typed route signals
  and direct usage classes, skips raw semantic previews during the indexed
  harvest, avoids compressed full-body hydration when bounded search rows are
  enough, and only falls back to broad text search when structured route hits do
  not include direct usage evidence
- Route-trace resolver: `trace-route` / `resolve-anchor` over skill, MCP,
  hook, tool, Git/GitHub, entity, and path anchors
- Incremental graph store, sidecar snapshots, and GraphRAG packets:
  `graph-build`, `graph-maintenance`, `graph-neighborhood`,
  `graph-timeline`, `graph-shortest-path`, `graph-cooccurrence`,
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
  full-text FTS plus compressed selected-hit hydration
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
  silently behind an active maintenance lease;
  `maintenance-status` exposes a `live_tail` packet over deferred live
  freshness rows with `waiting_for_quiet_window` vs `ready_for_catchup`,
  quiet-window remaining seconds, `next_ready_at`, and the typed catch-up
  command so agents do not confuse non-actionable live tail with broken search;
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
- Graph hot-state recovery guards: `maintenance-status` detects empty
  generated graph stores (`graph_store_nodes_empty` / `graph_store_edges_empty`)
  without a full source scan, routes them to bounded incremental
  `graph-maintenance`, compares non-retired ledger sources with stored
  `graph_sources` to catch partial-store recovery
  (`graph_source_ledger_store_count_mismatch`), and uses the latest fresh
  `graph-maintenance` report's non-zero `remaining_count` as
  `latest_graph_maintenance_remaining_sources` so stale ledgers or exhausted
  queues cannot make graph search look current
- Optional search provider gates: `config/search-providers.json`,
  `search-provider-status`, local embedding semantic context, and local
  reranker ordering metadata
- Retrieval packets: `retrieve` / `retrieval-packet` recipes over search,
  phase-discovery, continuation signals, and raw refs
- Hook docs and generated example: `hooks/`
- Schemas: `schemas/`
- Skills: `skills/`, including the user-level router
  `aoa-session-memory-global-route` and narrow operation skills for stress,
  historical import, audit, doctor, hook trust, and compact probe work
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
python3 scripts/aoa_session_memory.py graph-maintenance all --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --apply --batch-limit 3 --write-report
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
  `diagnostics/20260526T043629Z__route-trace__github.json`.
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
  --refresh-chunk-size 64 --write-report` completed under
  `abyss-machine resource launch --class medium --kind indexing` in `102.559s`,
  selected `25` sources, left `4679` global missing sources, consumed `4G`
  peak memory, and used `0B` swap.
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
| Segment and session indexes expose operational route signals for the 22-layer map | `facets.route_signals`, `by_route_layer`, `by_route_signal`, `route_signal_counts`, route-signal regression tests |
| Stable AoA skill and MCP service names route agents through canonical map axes | `entity:aoa_memo_writeback`, `entity:aoa_memo_mcp`, `mcp:aoa_memo_mcp`, `maps/by-entity/INDEX.md`, `maps/by-mcp/INDEX.md`, route-signal regression tests |
| Agents can start from a named operational anchor instead of hand-picking a map axis | `trace-route`, `resolve-anchor`, route-trace regression test, 2026-05-26 live route-trace reports |
| Preserved raw archives can be regenerated after taxonomy/classifier changes | `reindex-sessions all --max-raw-mb`, reindex report diagnostics, reindex regression test |
| Secondary route caches repair themselves through a bounded controller | `index-maintenance`, queued `index_maintenance` worker jobs, `auto-maintenance`, semantic-name maintenance regression test |
| Agents can search across many archived sessions without loading bulk raw into active context | `search-index --max-raw-mb`, `search --explain`, `search/aoa-search.sqlite3`, search-index regression test, 2026-05-17 live search report |
| Agents can query route layers directly | `search --route-layer`, `search --route-signal`, SQLite route-signal columns |
| The source atlas skeleton can be turned into generated entries and indexes | `atlas build`, `maps/by-*/entries/*.json`, `maps/by-*/INDEX.md`, atlas-build regression test |
| Agents can maintain graph state incrementally by session/segment contribution | `graph/graph.sqlite3`, `graph-maintenance`, graph source states, dirty-source replacement regression test |
| Agents can expand operational anchors through graph neighborhoods without losing evidence refs | `graph-build`, `graph-maintenance`, `graph-prune-sidecar`, `graph-neighborhood`, `graph-timeline`, `graph-shortest-path`, `graph-cooccurrence`, graph sidecar regression test |
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
| User-level router skill can be installed and checked from selected roots | `install-user-skill`, `doctor --check-user-skill`, audit checklist, tests |
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
  run `index-maintenance --apply --write-report`. Add `--sample-audit` when
  classifier/schema changes require a new manual calibration packet; apply
  `route-sample-review` verdicts explicitly after human/agent review.
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
