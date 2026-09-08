---
name: aoa-session-reindex
description: Use when existing `.aoa` session archives need generated segment Markdown and indexes rebuilt from preserved raw JSONL after taxonomy, classifier, relationship, or index-schema changes.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-reindex

Use this when the archive already has raw JSONL but generated segment indexes
need to be regenerated under the current classifier.

## Trigger Boundary

- Event taxonomy, universal facets, or relationship indexing changed.
- Existing sessions need fresh `segments/*.index.json` without re-importing raw.
- A batch report shows stale or missing index fields.
- The agent needs to verify old archives under the current index schema.

## Procedure

Start with a dry run for the selected session:

```bash
python3 scripts/aoa_session_memory.py reindex-sessions <session-label-or-id> \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --dry-run \
  --write-report
```

For an explicitly authorized bounded batch with a shared projection
dependency, use `all` with the same declared window and limit in every batch
command:

```bash
python3 scripts/aoa_session_memory.py reindex-sessions all \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --since-days 21 \
  --limit 10 \
  --write-report
```

`all` is never an automatic companion to a one-session trial. Carry the
selected session or the exact bounded batch predicate into each follow-on
route, and obtain separate scope plus a shared-dependency reason when moving
from one session to `all`.

For one target session:

```bash
python3 scripts/aoa_session_memory.py reindex-sessions <session-label-or-id> \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --write-report
```

After a classifier or schema reindex, refresh generated projections through the
named catch-up route for the same selected session:

```bash
python3 scripts/aoa_session_memory.py projection-catchup <session-label-or-id> \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --apply \
  --write-report
```

For a separately authorized bounded batch, repeat the same `all` selector and
window explicitly:

```bash
python3 scripts/aoa_session_memory.py projection-catchup all \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --since-days 21 \
  --limit 10 \
  --apply \
  --write-report
```

Use `--profile deep` only when the catch-up payload reports that a heavy full
search rebuild or graph repair is required.

## Verification

- `counts.diagnostic` is absent or zero.
- Segment indexes contain `by_family`, `by_phase`, `by_actor`,
  `by_action`, `by_outcome`, and `by_correlation`.
- Event records contain universal facets and relationship refs where available.
- `projection-catchup` reports no remaining projection backlog, or returns the
  explicit next route needed to finish it.
- `projection-status` reads the latest projection-catchup completeness packet
  without running the writer route, and uses cached maintenance diagnostics
  unless `--refresh-maintenance` is explicitly requested.
- Run `doctor`, `audit`, and tests after broad reindexing.

## Stop Line

Do not delete raw JSONL or distillation artifacts. Reindex regenerates generated
segments and indexes from raw evidence; it is not a semantic promotion step.
