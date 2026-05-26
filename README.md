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
  -> session index
  -> agent atlas route entries
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
  --dry-run \
  --write-report
```

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
