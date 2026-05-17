# AoA Session Memory Readiness

## Snapshot

Date: 2026-05-17

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
- Distillation routes: `config/event-distillation-routes.json`
- Batch distillation policy: `config/batch-distillation-policy.json`
- Portable search route: `search-index`, `search`, runtime `search/`, and
  `skills/aoa-session-search`
- Optional search provider gates: `config/search-providers.json` and
  `search-provider-status`
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
python3 scripts/aoa_session_memory.py reindex-sessions all --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --write-report
python3 scripts/aoa_session_memory.py search-index all --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --write-report
python3 scripts/aoa_session_memory.py search-provider-status --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --include-host --write-report
python3 scripts/aoa_session_memory.py search --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --query "hook timed out" --explain
python3 scripts/aoa_session_memory.py retrieve continue-techniques-session --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --query "aoa-techniques continuation" --write-report
python3 scripts/aoa_session_memory.py batch-distill --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --since-days 21 --write-report
python3 scripts/aoa_session_memory.py naming-readiness all --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --refresh-indexes --write-report
python3 scripts/aoa_session_memory.py validate --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py codex-compact-probe --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --trust-hooks
python3 scripts/aoa_session_memory.py stress-pass latest --aoa-root /path/to/workspace/.aoa --compactions 100 --write
python3 scripts/aoa_session_memory.py doctor --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --check-live-hooks --check-user-skill --check-codex-grounding
python3 scripts/aoa_session_memory.py audit --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
```

Last observed result:

- `.aoa` tests: `42 passed`
- `codex-grounding`: `ok=true`, `codex-cli 0.130.0`, compact ratio `0.8`
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
- Optional host-provider proof: `search-provider-status --include-host`
  probes host capability gates without making them authority. If
  `abyss-machine nervous quality-audit` reports warnings, `.aoa` keeps
  authoritative hits on `portable_sqlite` and treats host output as contextual
  only.
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
| Preserved raw archives can be regenerated after taxonomy/classifier changes | `reindex-sessions all`, reindex report diagnostics, reindex regression test |
| Agents can search across many archived sessions without loading bulk raw into active context | `search-index`, `search --explain`, `search/aoa-search.sqlite3`, search-index regression test, 2026-05-17 live search report |
| Host retrieval tools can be used without merging `abyss-machine` into `.aoa` authority | `config/search-providers.json`, `search-provider-status`, `search --provider abyss_machine_nervous`, host-provider regression test |
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
| Live hooks match expected commands | `doctor --check-live-hooks` |
| Native Codex hook trust is inspectable and repairable | `codex-hooks-status`, app-server `hooks/list` and `config/batchWrite` |
| Local Codex compact/hook contract is grounded | `codex-grounding`, local `codex-cli 0.130.0`, project config |
| Live PreCompact/PostCompact receipts are observed | `codex-compact-probe --trust-hooks`, sessions `2026-05-12__005__...` and `2026-05-12__006__...`, `audit` |
| Clean bundle export excludes sessions by default | `export-bundle`, install/export CLI check |
| Workspace install regenerates hook example for target roots | `install`, install test |
| Install repair does not clear existing sessions by default | preservation test |
| Standalone GitHub repository exists | private repo `8Dionysus/aoa-session-memory`, local `origin` on `main` |
| Completion readiness is explicit rather than inferred from green tests | `audit` command |

## Remaining Gates

No completion-blocking gates remain in the current local proof surface.

Maintenance gates:

- Re-run `codex-grounding` and `codex-hooks-status` when the local Codex CLI
  version changes.
- Re-run `codex-compact-probe --trust-hooks` after changing hook commands.
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
