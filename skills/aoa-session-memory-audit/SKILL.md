---
name: aoa-session-memory-audit
description: Use when the `.aoa` session-memory bundle needs a completion-readiness audit across raw preservation, compaction topology, hooks, tests, and standalone GitHub readiness.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-memory-audit

Use this for the end-to-end readiness gate. `audit` is stricter than local
health checks and may fail honestly when the kernel still has remaining gates.

## Trigger Boundary

- The user asks whether the `.aoa` mechanism is complete.
- A code, hook, topology, export, or install behavior changed.
- The standalone bundle or GitHub mirror needs readiness proof.

## Procedure

Run from the source root unless validating a standalone checkout:

```bash
python3 scripts/aoa_session_memory.py audit \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa
```

If Codex grounding is temporarily unavailable and the user only needs a
filesystem audit, use `--skip-codex-grounding` and say that live Codex proof was
skipped.

## Verification

- `completion_ready=true`
- `remaining=[]`
- standalone repo points at `/srv/AbyssOS/bundles/aoa-session-memory`
- origin is `git@github.com:8Dionysus/aoa-session-memory.git` on this host

## Stop Line

Do not mark the mechanism complete from tests alone. Report any `remaining`
items exactly.
