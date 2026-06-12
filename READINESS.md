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
- Agent atlas skeleton: `maps/`, `config/atlas-policy.json`, and
  `schemas/atlas-route-entry.schema.json`
- Distillation routes: `config/event-distillation-routes.json`
- Batch distillation policy: `config/batch-distillation-policy.json`
- Portable search route: `search-index`, `search`, runtime `search/`, and
  `skills/aoa-session-search`
- Route-trace resolver: `trace-route` / `resolve-anchor` over skill, MCP,
  hook, tool, Git/GitHub, entity, and path anchors
- Incremental graph store, sidecar snapshots, and GraphRAG packets:
  `graph-build`, `graph-maintenance`, `graph-neighborhood`,
  `graph-timeline`, `graph-shortest-path`, `graph-cooccurrence`,
  `graphrag-packet`, `graph-explain-packet`, `graph-eval`, and
  `graph-quality-audit` / `graph-quality-review`
- Large-archive graph maintenance controls: store-only / in-place
  `graph-build`, progress heartbeat, optional sidecar export, grouped
  dirty/missing source repair by session, streamed aggregate refresh, and
  profile-level refresh chunk sizes
- Storage weight controls: `storage-audit`, compact graph aggregate payloads
  with evidence hydration from contribution rows, and search body storage with
  full-text FTS plus compressed selected-hit hydration
- Pre-GraphRAG trust layer: source-owned
  `config/graph-quality-regression-corpus.json`, `graph-quality-corpus`,
  `graph-freshness-check`, `entity-dossier`, and GraphRAG packet
  `answer_rules`
- Automatic index maintenance route: `index-maintenance` / `maintain-index`
  over stale route indexes, per-session search/atlas projection fingerprints,
  bounded budgets, portable search freshness, atlas freshness, and readiness
  reports
- Partial atlas maintenance merges compact generated axis indexes, and scoped
  graph maintenance ignores out-of-scope graph sources instead of treating
  every non-selected row as an orphan
- Resource-gated unattended maintenance route: `auto-maintenance` /
  `maintain-auto` profiles `hot` (`probe`, graph-only/deferred index repair),
  `backlog` (`medium`, recent index+graph repair), and `deep` (`heavy`, full
  repair); MCP remains read-only and plan-only
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
python3 scripts/aoa_session_memory.py search-index all --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --max-raw-mb 16 --write-report
python3 scripts/aoa_session_memory.py search-provider-status --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --include-host --write-report
python3 scripts/aoa_session_memory.py search --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --query "hook timed out" --explain
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

- `.aoa` tests: `85 passed`
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
