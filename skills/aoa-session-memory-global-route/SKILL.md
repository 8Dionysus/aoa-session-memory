---
name: aoa-session-memory-global-route
description: Use in any Codex session when the user mentions `.aoa`, session memory, Codex transcripts, compaction, prior session rehydration, hook failures, or AoA session-memory validation.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: global-router
---

# aoa-session-memory-global-route

Use this as the top-level router for the AoA session-memory bundle.

## Source Root

On this machine the live source root is:

```text
/srv/AbyssOS/.aoa
```

The local standalone mirror is:

```text
/srv/AbyssOS/bundles/aoa-session-memory
```

## Trigger Boundary

Use this skill in any Codex session when the task touches:

- `.aoa` session memory
- Codex raw transcript JSONL
- context compaction or compaction intervals
- prior-session resume, rehydration, or session archive lookup
- AoA hooks for `SessionStart`, `UserPromptSubmit`, `PreCompact`,
  `PostCompact`, or `Stop`
- `raw_unavailable` incidents
- `stress-pass`, `audit`, `doctor`, `codex-hooks-status`, or
  `codex-compact-probe`
- historical Codex session import from `~/.codex/sessions`
- preparing or validating the portable `aoa-session-memory` bundle

## Procedure

1. Read `/srv/AbyssOS/.aoa/AGENTS.md`, then `/srv/AbyssOS/.aoa/DESIGN.md`.
2. Choose the narrow bundle skill from `/srv/AbyssOS/.aoa/skills/`.
3. Use `/srv/AbyssOS/.aoa/scripts/aoa_session_memory.py` for commands.
4. Keep historical raw/session material intact unless the user explicitly asks
   for a repair.
5. If the task changes portable behavior, export to
   `/srv/AbyssOS/bundles/aoa-session-memory` and validate both source and
   standalone surfaces.
6. If the user-level router itself is missing or stale, run
   `install-user-skill` from the active install root instead of hand-writing a
   symlink.

## Skill Routing

- New install or incomplete root: `aoa-session-archive-init`
- Raw transcript to archive: `aoa-codex-session-segment-archive`
- Raw missing or hook error: `aoa-session-raw-diagnostic`
- Resume from archive: `aoa-session-rehydrate`
- Provisional lesson extraction: `aoa-session-first-pass-distill`
- Historical Codex JSONL import: `aoa-session-history-import`
- Large archive / compaction stress: `aoa-session-memory-stress-pass`
- Completion readiness: `aoa-session-memory-audit`
- Filesystem and live hook health: `aoa-session-memory-doctor`
- Native Codex hook trust: `aoa-codex-hooks-status`
- Live PreCompact/PostCompact proof: `aoa-codex-compact-probe`

## Stop Line

Do not replace raw evidence with summaries. Use indexes and diagnostics first,
then open raw only for exact verification or repair.
