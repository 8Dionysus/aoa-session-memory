---
name: aoa-session-naming-wave
description: Use when many `.aoa` session archives need fast, reviewable semantic naming across readiness, sync/reindex preflight, review plans, guarded apply, and quality audit.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-naming-wave

Use this after `naming-readiness` exists but the operator needs to name many
sessions without opening every archive manually.

This skill creates a mass review surface. It does not physically rename
archive directories and it does not treat machine candidates as reviewed truth.

## Build A Wave

```bash
python3 scripts/aoa_session_memory.py naming-wave build \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --write \
  --write-report
```

The build step writes a `naming-wave-plan.json` under
`diagnostics/naming-waves/<wave-id>/`. Each item has:

- the current readiness route;
- the proposed semantic session name, when available;
- raw evidence refs and coverage;
- sync/reindex preflight actions, when needed;
- `reviewed_name`, initially empty;
- `physical_relabel_allowed=false`.

## Review The Plan

Edit only the plan JSON. For each session that is ready, fill
`reviewed_name` with the accepted umbrella session name. Leave it empty to
skip. For preflight items, either set `approved=true` on the item or pass
`--apply-preflight` deliberately.

Do not use the wave to create aliases. Superseded names should not accumulate
as routing noise.

## Apply Reviewed Work

```bash
python3 scripts/aoa_session_memory.py naming-wave apply \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --plan diagnostics/naming-waves/<wave-id>/naming-wave-plan.json \
  --apply \
  --write-report
```

`apply` writes semantic `session` names only for non-empty `reviewed_name`
items. It refreshes `SESSION_NAMES.md`, `session-name-index.json`,
`sessions/INDEX.md`, and `sessions/index.json`.

For a deliberately fast high-confidence pass, `--accept-proposed` can accept
only proposed names whose candidate quality is `ok`. Use it after sampling the
plan, not as the default route.

## Audit Quality

```bash
python3 scripts/aoa_session_memory.py naming-wave audit \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --plan diagnostics/naming-waves/<wave-id>/naming-wave-plan.json \
  --sample-size 18 \
  --sample-seed wave-quality-1 \
  --write-report
```

The audit reports missing active session names, stale coverage, open phase
queues, duplicate slugs, missing anchors, banned placeholder terms, and
candidate quality flags. With `--sample-size`, it also writes a deterministic
stratified sample with raw evidence previews. Treat each sampled defect as a
class: add a small golden case or classifier rule, rebuild the wave, and sample
again with a new seed.

## Stop Line

Mass naming is still a review layer. Use it to compress and route human/agent
attention, not to replace raw evidence or to move archive directories.
