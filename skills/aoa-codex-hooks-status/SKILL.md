---
name: aoa-codex-hooks-status
description: Use when AoA Codex hooks must be inspected, trusted, or compared against expected `.aoa` commands in the native Codex hook registry.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-codex-hooks-status

Use this when Codex reports hook failures, hooks do not run, or hook commands
may be untrusted or stale.

## Trigger Boundary

- The user says hooks failed, are untrusted, or are not firing.
- the logical `<codex-hook-registry>` changed.
- `.aoa/scripts/aoa_session_memory.py` or hook command paths changed.
- A Codex update may have changed hook trust behavior.

## Procedure

Inspect without changing trust first:

```bash
python3 scripts/aoa_session_memory.py codex-hooks-status \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root>
```

If matching AoA hooks are present but untrusted, and the user has approved
trusting the current commands, run:

```bash
python3 scripts/aoa_session_memory.py codex-hooks-status \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --trust-current
```

## Verification

- `ok=true`
- required hooks are present
- required hooks are trusted
- required hook commands match the selected workspace and `.aoa` root

## Stop Line

Do not trust arbitrary hooks. Only trust current hashes for commands that match
the generated AoA commands.
