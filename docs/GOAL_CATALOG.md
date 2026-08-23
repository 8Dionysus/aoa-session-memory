# Public Goal catalog

`aoa-session-memory` is the owner of the generated Goal lifecycle index. The
`goal-catalog` command is a read-only, public-safe publication surface over
that index; it is not a replacement for the preserved transcript or the
Codex Goal owner.

```bash
python3 scripts/aoa_session_memory.py goal-catalog \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --page-size 50 \
  --order recent
```

The command returns one immutable page. When `pagination.next_cursor` is not
`null`, pass that opaque value to the next read:

```bash
python3 scripts/aoa_session_memory.py goal-catalog \
  --aoa-root /path/to/workspace/.aoa \
  --page-size 50 \
  --cursor '<opaque cursor>'
```

The cursor binds the query, page size, source generation, source watermark,
and complete snapshot digest. A changed registry or session index makes the
cursor `stale` and returns no records; it never silently mixes pages from two
source generations. A malformed cursor is `invalid` and also returns no
records. Source reads use a bounded retry budget and expose the attempts and
whether retry was exhausted in `snapshot`; an unstable or torn source is
`deferred` and admits no records.

Each admitted record contains only stable Goal/thread correlation, lifecycle
state, lifecycle grouping, bounded observation timestamps, an owner evidence
coordinate, and an item digest. The catalog omits transcript bodies, prompts,
private objectives, raw session paths, cwd, usage, work-chain details, actor or
model identity, and process identity. `safe_title_state` explicitly reports
`missing` or `withheld`; a consumer must not reconstruct a title from omitted
objective text.

`state` and `currentness` are explicit: `current` admits a page, while
`missing`, `unknown`, `stale`, `deferred`, and `invalid` are negative states.
The latter states set `ok` to `false`, preserve diagnostics, and do not expose
stale source records as current catalog items. A preserved raw capture ahead
of its last-good session projection is reported through
`source_watermark.live_tail` and makes the catalog `deferred`; the stable
projection watermark is not silently promoted to an exhaustive live claim.
`source.generation_identity`, `source.goal_lifecycle_generation`,
`source_watermark`, `snapshot_digest`, `item_digest`, and `page_digest` let a
non-sovereign dashboard verify that it is rendering one owner publication.
Selection remains dashboard state and is not encoded in this catalog.

The source is the complete available session registry plus every referenced
manifest, `session.index.json`, and observed raw-capture/projection watermark;
no Goal id, task-root path, Codex version, source generation, or fixture is
embedded in the publisher. Generated source is navigation, not reviewed
truth. Follow `evidence_ref` through the owner’s normal evidence route before
making a claim about what happened.
