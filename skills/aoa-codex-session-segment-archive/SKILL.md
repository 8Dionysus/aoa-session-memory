---
name: aoa-codex-session-segment-archive
description: Use when a Codex raw transcript must be archived into `.aoa` compaction-interval segments with raw preservation, segment indexes, manifests, and registry updates.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual-or-hook-route
---

# aoa-codex-session-segment-archive

Use when a Codex raw transcript must be preserved as compaction-interval
segments with indexes.

## Trigger Boundary

- Codex `SessionStart` or manual recovery provides a `transcript_path` for a
  full archive rebuild.
- Codex `PreCompact`, `PostCompact`, or `Stop` has queued lifecycle sync and
  the archive needs automatic interval sealing or a deliberate rebuild.
- Manual recovery has found a raw session JSONL.
- A segment/index needs to be rebuilt from raw.

## Inputs

- `session_id`
- `transcript_path`
- workspace root
- optional `.aoa` root

## Procedure

1. Resolve the source identity and verify that the transcript exists and is
   readable before creating or updating archive output.
2. If source validation or reading fails, stop archive processing and hand a
   typed `raw-read-failure` to `aoa-session-raw-diagnostic`. Do not emit or
   claim an `archived-session-set` for that attempt.
3. Preserve the raw transcript under
   `sessions/YYYY-MM-DD__NNN__short-title/raw/`.
4. Parse JSONL line by line without discarding raw lines.
5. Split by detected compaction boundaries. If no boundary exists, write
   segment `000__initial-to-latest`.
6. Write bounded raw interval blocks under `raw/blocks/` plus
   `raw/blocks.index.json` and `raw/compaction-events.jsonl`.
7. Write one Markdown segment per interval with raw event bodies intact.
8. Write a sibling `.index.json` for each segment.
9. Update `session.manifest.json`, `SESSION.md`, `session.index.json`, and
   `session-registry.json`.
10. Ensure the session archive directory itself uses the readable label.

## Verification

- Raw copy exists and has a SHA-256 in the manifest.
- Every segment has a raw block record and a corresponding
  `raw/blocks/*.raw.jsonl` file.
- Every segment has a sibling index.
- Index records include `event_id`, `type`, `md_anchor`, and `raw_ref`.
- The manifest and registry expose `display.label` for human navigation.
- The Codex UUID remains in `session_id`; do not use it as the normal folder
  name once a readable label is available.
- Re-running the archive command is idempotent for the same raw transcript.
- On source failure, no archive output is claimed and the diagnostic handoff
  preserves the source path, error, event, and session identity.

## Stop Line

Do not summarize away raw material. Distillation is a later reviewed act.
