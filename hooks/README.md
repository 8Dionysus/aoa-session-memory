# AoA Session Memory Hooks

This directory documents Codex hook wiring for the `.aoa` session-memory
kernel.

For host-wide capture, install a user-level Codex hooks file at:

```text
~/.codex/hooks.json
```

The static example is:

```text
.aoa/hooks/codex-hooks.user.example.json
```

It uses placeholder paths and is not the source of truth for a live machine.
Do not hand-edit paths when installing on another machine or under another
workspace root. Generate the live config from the selected roots:

```bash
python3 .aoa/scripts/aoa_session_memory.py hooks-config \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

To install it for the current user:

```bash
python3 .aoa/scripts/aoa_session_memory.py hooks-config \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --write ~/.codex/hooks.json
```

User-level hooks may run in addition to project-level hooks. The archive script
is idempotent for the same raw transcript, but duplicate hook event receipts can
appear in `hooks/events.jsonl`.

Recent Codex builds require unmanaged hooks to be trusted before they run.
After writing `~/.codex/hooks.json`, inspect the native hook state:

```bash
python3 .aoa/scripts/aoa_session_memory.py codex-hooks-status \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

If the AoA hooks are present but untrusted, trust the current matching hashes:

```bash
python3 .aoa/scripts/aoa_session_memory.py codex-hooks-status \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --trust-current
```

For a live compaction check, use:

```bash
python3 .aoa/scripts/aoa_session_memory.py codex-compact-probe \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --trust-hooks
```

## Hook Contract

- Hooks are fail-open.
- Raw transcript unavailability writes `INCIDENT.md` and `DIAGNOSTIC.json`.
- SessionStart may refresh the raw transcript and indexes when
  `transcript_path` is available.
- PreCompact and PostCompact preserve the hook receipt and mirror raw
  transcript state by default, then defer segment/index regeneration.
- Stop may full-sync small transcripts, but mirrors raw and defers indexing
  once the transcript is over `AOA_SESSION_MEMORY_STOP_SYNC_MAX_BYTES`.
- UserPromptSubmit records the hook event by default, but does not run the full
  transcript sync unless `AOA_SESSION_MEMORY_FULL_PROMPT_SYNC=1` is set.
- PreCompact, PostCompact, and large Stop hooks return only schema-valid Codex
  protocol fields and must not block the active lifecycle by default.
- Indexed sessions are stored directly under
  `sessions/YYYY-MM-DD__NNN__short-title`.
- Distillation is not performed in hooks.
