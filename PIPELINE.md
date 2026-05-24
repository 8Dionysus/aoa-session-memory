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
  -> JSONL event classification
  -> route-signal classification for operational layers
  -> raw/blocks/*.raw.jsonl sealed by compaction interval
  -> raw/blocks.index.json and raw/compaction-events.jsonl
  -> compaction-interval segment Markdown
  -> sibling segment index JSON
  -> SESSION.md and session.index.json
  -> session.manifest.json
  -> session-registry.json
  -> optional search-index runtime cache
  -> optional provider capability status for host overlays
  -> retrieval packet recipes
  -> agent atlas route entries from generated route signals
  -> index-maintenance drift detector / repair pass
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

It detects stale or missing route indexes, source-newer-than-search drift,
source-newer-than-atlas drift, and deferred raw mirrors. With `--apply`, it
reindexes only stale route indexes, rebuilds portable SQLite search when
needed, rebuilds the atlas when needed, and records a route-readiness report.
Use `--sample-audit` when a route schema or classifier change requires a new
manual calibration packet. Sample verdicts still require explicit review.

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

The agent should use indexes before opening large Markdown or raw JSONL.
Naming-readiness data in `SESSION_NAMES.md`, `session-name-index.json`,
`sessions/INDEX.md`, and `sessions/index.json` should be checked before broad
semantic naming or physical relabeling.

`session.index.json` also carries generated `work_context`, which names the
best current workspace/repository route from `cwd` and indexed path evidence.
It is a naming aid and retrieval route, not reviewed ownership truth.
It also carries generated `route_signal_counts`, which are search and atlas
routes over event facets, not reviewed distillation.

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
  --dry-run \
  --write-report
```

Remove `--dry-run` for a bounded pass. Keep `--max-raw-mb` on broad archive
runs; large raw sessions should use an explicit heavy-session route instead of
silent unbounded regeneration.

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
