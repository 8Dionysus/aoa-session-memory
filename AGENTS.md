# AGENTS.md

## Purpose

This directory stores the portable AoA session-memory kernel for Codex-style
agent sessions.

It preserves raw session material, creates compaction-interval archives,
builds indexes, records diagnostics, and provides skill surfaces for manual
recovery and later distillation.

## Laws

1. Preserve before distilling.
2. Raw session files are local evidence, not reviewed truth.
3. Segment Markdown is generated from raw and remains reviewable evidence.
4. Index every archived segment.
5. Record raw refs for important claims.
6. Diagnose raw/session failures immediately.
7. Do not promote experience, patterns, skills, or automation without reviewed
   distillation.
8. Keep the portable kernel separate from local AoA/Tree of Sophia overlays.

## Required Read Order

When working here, read:

1. `DESIGN.md`
2. `PIPELINE.md`
3. `INSTALL.md` when changing portability, export, or hook installation
4. `READINESS.md`
5. `README.md`
6. `NAMING.md`
7. `session-registry.json` if present
8. The target session `AGENTS.md`
9. The target session `SESSION.md`
10. The target session `session.manifest.json`
11. The relevant segment index before opening a full segment

## Generated Material

The following paths are generated or runtime-owned:

- `sessions/*/raw/`
- `sessions/*/segments/`
- `sessions/*/SESSION.md`
- `sessions/*/session.index.json`
- `sessions/*/session.manifest.json`
- `sessions/*/hooks/`
- `sessions/*/incidents/`
- `session-registry.json`
- `diagnostics/`

Agents may regenerate these files from raw session evidence. Do not manually
edit generated session archives unless explicitly repairing a broken archive
with a clear diagnostic note.

Session archive directory names must follow `NAMING.md`. Keep the Codex UUID as
`session_id` inside the manifest, not as the folder name.

## Stop Lines

- Do not write secrets into portable exports.
- Do not treat summaries as source truth.
- Do not delete raw session evidence as cleanup.
- Do not make this directory the authority for AoA doctrine, Tree of Sophia
  meaning, or repository ownership.
- Do not let hooks block Codex work unless an operator explicitly enables a
  blocking mode.
