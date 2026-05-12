---
name: aoa-session-raw-diagnostic
description: Use when a `.aoa` hook or manual archive pass cannot read the raw Codex transcript and must write an incident plus diagnostic record instead of fake memory.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual-or-hook-route
---

# aoa-session-raw-diagnostic

Use when a hook or manual archive pass cannot read the raw Codex transcript.

## Trigger Boundary

- `transcript_path` is missing.
- `transcript_path` does not exist.
- The raw file is not readable.
- A hook exception occurs during archive sync.

## Procedure

1. Record the expected raw source path, `session_id`, hook event, turn id, and
   cwd.
2. Check path existence, readability, parent existence, and parent readability.
3. Write `INCIDENT.md` and `DIAGNOSTIC.json` under the session `incidents/`
   directory.
4. Mark `session.manifest.json` with `archive_status=raw_unavailable`.
5. Do not create a fake recovery summary.

## Verification

- Incident Markdown exists.
- Diagnostic JSON exists.
- Registry points to the session with `raw_unavailable` status.

## Stop Line

Raw unavailability is an infrastructure fault, not a normal memory substitute.
