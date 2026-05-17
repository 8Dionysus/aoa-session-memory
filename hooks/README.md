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
- SessionStart records the hook receipt by default and defers raw sync/indexing
  unless `AOA_SESSION_MEMORY_FULL_START_SYNC=1` is set.
- PreCompact and PostCompact preserve the hook receipt and mirror raw
  transcript state only while the transcript is below
  `AOA_SESSION_MEMORY_HOOK_MIRROR_MAX_BYTES`, then defer segment/index
  regeneration. Larger transcripts record a receipt and defer raw mirroring.
- PostCompact must queue automatic interval sealing for `hook-worker`: the
  worker writes `raw/blocks/*.raw.jsonl`, `raw/blocks.index.json`,
  `raw/compaction-events.jsonl`, compaction-segment Markdown, and sibling
  segment indexes outside the Codex hook timeout.
- Stop may full-sync small transcripts, but mirrors raw and defers indexing
  once the transcript is over `AOA_SESSION_MEMORY_STOP_SYNC_MAX_BYTES`.
- UserPromptSubmit records the hook event by default, but does not run the full
  transcript sync unless `AOA_SESSION_MEMORY_FULL_PROMPT_SYNC=1` is set.
- PreCompact, PostCompact, and large Stop hooks return only schema-valid Codex
  protocol fields and must not block the active lifecycle by default.
- Deferred lifecycle work is automatically queued under
  `diagnostics/hook-jobs/pending/` and processed by `hook-worker` outside the
  Codex hook timeout window. Set `AOA_SESSION_MEMORY_HOOK_BACKGROUND_SYNC=0`
  to disable worker launch, or `AOA_SESSION_MEMORY_HOOK_SYNC_QUEUE=0` to
  disable queueing.
- Manual sync/import/reindex are recovery and rebuild paths. They must not be
  the normal route for closing a compaction interval after `PostCompact`.
- Hook registry writes use a short non-blocking lock window. If another
  `.aoa` operation owns the registry lock, the hook keeps the local receipt or
  manifest and marks the registry update as deferred.
- Indexed sessions are stored directly under
  `sessions/YYYY-MM-DD__NNN__short-title`.
- Distillation is not performed in hooks.
