---
name: aoa-codex-compact-probe
description: Use when the live Codex PreCompact and PostCompact hook path must be proven through `.aoa` using the Codex app-server compact probe.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: explicit-live-check
---

# aoa-codex-compact-probe

Use this for live proof that Codex compaction hooks reach the archive.

## Trigger Boundary

- Hook commands changed.
- Codex was upgraded.
- The user asks for live compaction hook proof.
- `audit` or `doctor` needs live PreCompact/PostCompact confidence.

## Procedure

Run only after `codex-hooks-status` is green or after the user approved
`--trust-hooks`:

```bash
python3 scripts/aoa_session_memory.py codex-compact-probe \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --trust-hooks
```

This uses Codex app-server `thread/compact/start`; do not replace it with a
low-threshold `codex exec` loop.

## Verification

- `ok=true`
- probe reports live `PreCompact` and `PostCompact`
- hook receipts appear in archived session hook events
- audit hook counts increase or remain coherently present

## Stop Line

This is a live Codex integration check, not a unit test. Report if it was
skipped or if trust was not changed.
