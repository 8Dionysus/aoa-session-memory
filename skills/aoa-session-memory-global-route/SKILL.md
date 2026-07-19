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

Resolve three logical roots before acting:

- `<workspace-root>`: the selected project workspace;
- `<aoa-root>`: the active installed session-memory root;
- `<portable-source-root>`: the standalone owner source when source/export
  work is required.

Concrete paths are runtime bindings, not portable skill identity.

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
- event taxonomy, classifier, generated segment indexes, or `reindex-sessions`
- portable SQLite search, `search-index`, `aoa-search`,
  `search-provider-status`, optional host provider gates, or retrieval
  freshness
- retrieval packets, `retrieve`, `retrieval-packet`, or long-session
  continuation recipes
- live route-quality checks, `live-scenario-audit`, or
  `live-scenario-corpus`
- naming readiness, `SESSION_NAMES.md`, `sessions/INDEX.md`, or
  `naming-readiness`
- mass session naming, `naming-wave`, semantic session-name review plans, or
  naming quality audit
- phase discovery, `phase-discovery`, `review-phase-name`, or session naming
  candidate layers
- historical Codex session import from `<codex-history-root>`
- first-wave batch distillation or historical session review queues
- preparing or validating the portable `aoa-session-memory` bundle

## Procedure

1. Read `<aoa-root>/AGENTS.md` and classify the task before loading
   deeper context.
2. Read only the owning surface: `DESIGN.md` for architecture or boundaries,
   `DESIGN.AGENTS.md` for query/access behavior, the relevant `PIPELINE.md`
   section for operations, `INSTALL.md` for portability, `NAMING.md` for names,
   or `READINESS.md` for proof posture.
3. Read
   [references/capability-router.md](references/capability-router.md), verify
   its source hash against the generated graph when composition matters, and
   choose the smallest applicable bundle.
4. Use `<aoa-root>/scripts/aoa_session_memory.py` for commands.
5. Keep historical raw/session material intact unless the user explicitly asks
   for a repair.
6. If the task changes portable behavior, export to
   `<portable-source-root>` and validate both source and
   standalone surfaces.
7. If the user-level router itself is missing or stale, run
   `install-user-skill` from the active install root instead of hand-writing a
   symlink.

## Skill Routing

Use the generated router card for exact package names, positive and negative
applicability, visibility, version, and fingerprint. Its stable branches are:

- `use.route` for top-level selection;
- `use.query` for evidence, search, and rehydration;
- `stewardship.capture`, `.project`, `.curate`, `.name`, and `.assure`;
- `adapters.codex` for Codex hooks, transcripts, and compaction.

For more than one capability, use the full generated graph and task-local DAG
planner. Do not select a set from topical similarity alone.

## Verification

- The chosen capability's positive trigger matches and its negative trigger
  does not.
- The selected package version/fingerprint matches the current generated
  router and installed runtime receipt when available.
- Required inputs, permissions, effects, and verifier are known before action.
- The prompt-visible set remains the two admitted routers unless a separate
  routing eval and owner decision changes it.

## Stop Line

Do not replace raw evidence with summaries. Use indexes and diagnostics first,
then open raw only for exact verification or repair.
