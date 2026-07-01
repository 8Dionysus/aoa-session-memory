---
name: aoa-session-memory-doctor
description: Use when the `.aoa` session-memory filesystem contract, registry, generated indexes, naming policy, live hooks, or Codex grounding need health checks.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-memory-doctor

Use this for local health and repair orientation. `doctor` checks consistency;
it does not replace `audit`.

## Trigger Boundary

- A session archive looks inconsistent.
- Required root files, indexes, manifests, or registry entries may be missing.
- Live hook wiring or Codex grounding needs a health check.
- The user-level router skill needs to be checked for the current Codex user.
- A change touched bundle structure, naming, schemas, hooks, or generated
  surfaces.

## Procedure

Run the narrow filesystem and metadata doctor first:

```bash
python3 scripts/aoa_session_memory.py doctor \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa
```

The default route is intentionally fast on large live archives. It checks
required surfaces, manifests, registry and generated-surface presence without
parsing every event in every segment index.

When live hooks and Codex grounding matter, run:

```bash
python3 scripts/aoa_session_memory.py doctor \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --check-live-hooks \
  --check-user-skill \
  --check-codex-grounding
```

When the task is specifically to validate event payloads inside segment index
files, use the explicit deep route:

```bash
python3 scripts/aoa_session_memory.py doctor \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --deep-segment-indexes
```

## Verification

- `ok=true`
- `status=current` or an explicitly deferred live-tail status
- no `problems`
- warnings are reported, not hidden
- if live checks were requested, hook and grounding subreports are green
- if `--check-user-skill` was requested, the global router points at this
  install

## Stop Line

Do not treat a green doctor as completion readiness. Use `audit` for that.
