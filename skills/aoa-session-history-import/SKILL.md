---
name: aoa-session-history-import
description: Use when historical Codex JSONL sessions from `~/.codex/sessions` need to be discovered, dry-run checked, and sequentially imported into `.aoa` archives.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-history-import

Use this when older Codex sessions need to be laid out into the `.aoa`
archive without manually calling `sync` for each transcript.

## Trigger Boundary

- The user asks to import prior sessions.
- A rolling window such as the last three weeks must be archived.
- `raw_unavailable` archives may be repairable from existing JSONL transcripts.
- A Codex session may have closed without a usable `Stop` hook receipt, leaving
  a missing, stale, deferred, or hook-only `.aoa` archive.
- The agent needs a bounded report instead of dumping many session records into
  active context.

## Procedure

Start with a dry run:

```bash
python3 scripts/aoa_session_memory.py import-codex-sessions \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --since-days 21 \
  --dry-run \
  --write-report
```

If the dry-run count is coherent, run the import:

```bash
python3 scripts/aoa_session_memory.py import-codex-sessions \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --since-days 21 \
  --write-report
```

Use `--force` only when an already indexed archive must be rebuilt.

For recent missed close/no-hook recovery, prefer the narrower sweeper before a
broad import:

```bash
python3 scripts/aoa_session_memory.py sweep-codex-sessions \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --since-days 7 \
  --min-age-sec 60 \
  --dry-run \
  --write-report
```

The sweeper is dry-run by default and uses `indexed_archive_freshness` to plan
only missing, stale, deferred, hook-only, or raw-unavailable transcripts. Add
`--apply` after the plan is coherent.

## Verification

- import report JSON and Markdown exist under `.aoa/diagnostics/`
- `counts.error` is absent or zero
- already indexed sessions are skipped unless `--force` was used
- sweep reports show only coherent planned/synced candidates before `--apply`
- imported sessions have readable date/sequence/title labels
- `doctor` and `audit` remain green after the run

## Stop Line

Do not open every raw transcript in context. Use the import report, registry,
manifests, and segment indexes as the navigation layer.
