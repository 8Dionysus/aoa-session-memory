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

Start with a dry run:

```bash
python3 scripts/aoa_session_memory.py reindex-sessions all \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --dry-run \
  --write-report
```

For a bounded smoke pass:

```bash
python3 scripts/aoa_session_memory.py reindex-sessions all \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --limit 10 \
  --write-report
```

For one target session:

```bash
python3 scripts/aoa_session_memory.py reindex-sessions <session-label-or-id> \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --write-report
```

After a classifier or schema reindex, refresh generated projections through the
named catch-up route:

```bash
python3 scripts/aoa_session_memory.py projection-catchup all \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
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
- Run `doctor`, `audit`, and tests after broad reindexing.

## Stop Line

Do not delete raw JSONL or distillation artifacts. Reindex regenerates generated
segments and indexes from raw evidence; it is not a semantic promotion step.
