---
name: aoa-session-memory-stress-pass
description: Use for `.aoa` large-session checks, logical compaction boundary validation, bounded archive inspection, and `stress-pass` diagnostics.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-memory-stress-pass

Use when a large session archive needs bounded validation without flooding the
active context.

## Trigger Boundary

- The user asks for a large archive check.
- Segment counts, compaction counts, or marker counts look suspicious.
- `show --full` would be too large.
- A prior `raw_unavailable` or rebuild may have damaged confidence in an
  archive.

## Procedure

1. Read `AGENTS.md`, `DESIGN.md`, `DESIGN.AGENTS.md`, and `PIPELINE.md`.
2. Resolve the target session from `session-registry.json`; default to
   `latest` only when the user did not name a session.
3. Inspect `session.manifest.json` and segment indexes before opening bulk
   Markdown or raw JSONL.
4. Run:

```bash
python3 scripts/aoa_session_memory.py stress-pass <session> \
  --aoa-root <aoa-root> \
  --compactions 100 \
  --write
```

5. Use `--write` only when a durable diagnostic was explicitly requested.
   That write is limited to generated diagnostics and never authorizes archive
   or raw-evidence mutation. Keep stdout bounded and read the written
   JSON/Markdown artifact when detail is needed.
6. Distinguish logical `compaction_boundary_count` from raw marker count.

## Verification

- `ok=true` in the stress-pass payload.
- The selected segment span is coherent.
- No marker-only microsegments were introduced.
- Written diagnostics exist under the session `diagnostics/` directory.

## Stop Line

Do not use `--full` unless the user explicitly needs complete JSON on stdout.
