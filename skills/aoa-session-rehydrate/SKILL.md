---
name: aoa-session-rehydrate
description: Use when an agent needs to resume, inspect, or continue from an archived `.aoa` session without loading the full raw transcript.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-rehydrate

Use when an agent needs to resume work from an archived session without loading
the full raw transcript.

## Trigger Boundary

- A user asks to resume, inspect, or continue a prior session.
- Compaction has made current context unreliable.
- A session archive exists under `.aoa/sessions/`.

## Procedure

1. Prefer the readable `.aoa/sessions/YYYY-MM-DD__NNN__short-title` directory,
   or read `.aoa/session-registry.json` when the target is ambiguous.
2. Open the target session `SESSION.md`.
3. Open `session.manifest.json`.
4. Open the relevant segment `.index.json`.
5. Load only the relevant segment events by `md_anchor` or `raw_ref`.
6. Mark claims as provisional unless reviewed distillation exists.

## Verification

- The rehydration path names the exact session id.
- The answer cites segment event ids or raw refs for important claims.
- The agent does not rely on a summary when raw/index evidence is available.

## Stop Line

Do not read every raw event by default. Use the index as navigation.
