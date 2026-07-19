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
- The user-level router skill must be proven as part of portability.

## Procedure

Run from the source root unless validating a standalone checkout:

```bash
python3 scripts/aoa_session_memory.py audit \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root>
```

For the clean standalone bundle, use portable-bundle mode. It checks source,
install, hook-example, search-provider config, and GitHub readiness without
requiring live raw sessions, hook receipts, or a generated SQLite cache inside
the repo:

```bash
python3 scripts/aoa_session_memory.py audit \
  --workspace-root <workspace-root> \
  --aoa-root <portable-source-root> \
  --portable-bundle
```

If Codex grounding is temporarily unavailable and the user only needs a
filesystem audit, use `--skip-codex-grounding` and say that live Codex proof was
skipped.

## Verification

- `completion_ready=true`
- `remaining=[]`
- user-level router skill is installed for the current Codex user
- standalone repo points at `<portable-source-root>`
- when the selected release or install profile declares an owner remote, the
  observed standalone origin matches that runtime binding
- an offline or remote-free portable bundle reports the origin check as
  explicitly not applicable instead of inventing a host-specific remote
- clean standalone bundle audit uses `audit_mode=portable_bundle`

## Stop Line

Do not mark the mechanism complete from tests alone. Report any `remaining`
items exactly.
