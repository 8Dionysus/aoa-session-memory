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
2. `DESIGN.AGENTS.md`
3. `PIPELINE.md`
4. `INSTALL.md` when changing portability, export, or hook installation
5. `READINESS.md`
6. `README.md`
7. `NAMING.md`
8. `sessions/AGENTS.md` if present
9. `sessions/INDEX.md` if present
10. `SESSION_NAMES.md` and `session-registry.json` if present
11. The target session `AGENTS.md`
12. The target session `SESSION.md`
13. The target session `session.manifest.json`
14. The relevant segment index before opening a full segment

When editing a source district, also read that directory's own `AGENTS.md`
first: `config/`, `hooks/`, `maps/`, `schemas/`, `scripts/`, `skills/`,
`tests/`, or `sessions/`. When inspecting live reports, read
`diagnostics/AGENTS.md`; it is a runtime evidence district, not portable source.

## Generated Material

The following paths are generated or runtime-owned:

- `sessions/*/raw/`
- `sessions/*/segments/`
- `sessions/AGENTS.md`
- `sessions/INDEX.md`
- `sessions/index.json`
- `sessions/*/SESSION.md`
- `sessions/*/session.index.json`
- `sessions/*/session.manifest.json`
- `sessions/*/hooks/`
- `sessions/*/incidents/`
- `session-registry.json`
- `session-name-index.json`
- `SESSION_NAMES.md`
- `maps/by-*/entries/*.md`
- `maps/by-*/entries/*.json`
- `maps/by-*/INDEX.md`
- `maps/by-*/index.json`
- `maps/INDEX.md`
- `maps/index.json`
- `search/`
- `diagnostics/`

Agents may regenerate these files from raw session evidence. Do not manually
edit generated session archives unless explicitly repairing a broken archive
with a clear diagnostic note.

The `maps/` root, its `AGENTS.md`, `START.md`, `README.md`, `_templates/`,
axis `README.md` files, and placeholder `.gitkeep` files are source-owned
atlas skeleton. Generated atlas entries belong only in the generated map paths
listed above.

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
