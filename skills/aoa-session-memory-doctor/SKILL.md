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
- A change touched bundle structure, naming, schemas, hooks, or generated
  surfaces.

## Procedure

Run the narrow filesystem doctor first:

```bash
python3 scripts/aoa_session_memory.py doctor \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa
```

When live hooks and Codex grounding matter, run:

```bash
python3 scripts/aoa_session_memory.py doctor \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --check-live-hooks \
  --check-codex-grounding
```

## Verification

- `ready=true`
- no `problems`
- warnings are reported, not hidden
- if live checks were requested, hook and grounding subreports are green

## Stop Line

Do not treat a green doctor as completion readiness. Use `audit` for that.
