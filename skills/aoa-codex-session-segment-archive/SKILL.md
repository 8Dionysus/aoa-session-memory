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
- Codex `PreCompact`, `PostCompact`, or `Stop` has mirrored raw with deferred
  indexing, and the archive now needs a deliberate full rebuild.
- Manual recovery has found a raw session JSONL.
- A segment/index needs to be rebuilt from raw.

## Inputs

- `session_id`
- `transcript_path`
- workspace root
- optional `.aoa` root

## Procedure

1. Preserve the raw transcript under
   `sessions/YYYY-MM-DD__NNN__short-title/raw/`.
2. Parse JSONL line by line without discarding raw lines.
3. Split by detected compaction boundaries. If no boundary exists, write
   segment `000__initial-to-latest`.
4. Write one Markdown segment per interval with raw event bodies intact.
5. Write a sibling `.index.json` for each segment.
6. Update `session.manifest.json`, `SESSION.md`, `session.index.json`, and
   `session-registry.json`.
7. Ensure the session archive directory itself uses the readable label.

## Verification

- Raw copy exists and has a SHA-256 in the manifest.
- Every segment has a sibling index.
- Index records include `event_id`, `type`, `md_anchor`, and `raw_ref`.
- The manifest and registry expose `display.label` for human navigation.
- The Codex UUID remains in `session_id`; do not use it as the normal folder
  name once a readable label is available.
- Re-running the archive command is idempotent for the same raw transcript.

## Stop Line

Do not summarize away raw material. Distillation is a later reviewed act.
