# AoA Session Memory Readiness

## Snapshot

Date: 2026-05-12

This file maps the current `.aoa` session-memory goal to concrete evidence.
It is a readiness snapshot for agents, not a substitute for running the gates.

## Objective

Build the `.aoa` session-memory mechanism end to end:

- preserve full raw Codex session material
- preserve compaction intervals before and after context compression
- index raw material so agents can navigate without loading everything
- keep hook output schema-valid and fail-open
- provide skills and docs that route agents through the same pipeline
- keep the kernel portable and separable from local AoA overlays
- test the pieces alone and together

## Implemented Surfaces

- Design: `DESIGN.md`
- Operation route: `PIPELINE.md`
- Install/export route: `INSTALL.md`
- Naming policy: `NAMING.md` and `config/naming-policy.json`
- Event taxonomy: `config/event-taxonomy.json`
- Distillation routes: `config/event-distillation-routes.json`
- Hook docs and generated example: `hooks/`
- Schemas: `schemas/`
- Skills: `skills/`
- CLI and hooks: `scripts/aoa_session_memory.py`
- Tests: `tests/test_session_memory.py`
- Standalone repository: `https://github.com/8Dionysus/aoa-session-memory`

## Current Green Gates

Run from the bundle root, replacing `/path/to/workspace` and
`/path/to/workspace/.aoa` with the active install roots:

```bash
python3 -m py_compile scripts/aoa_session_memory.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_session_memory.py
python3 scripts/aoa_session_memory.py codex-grounding --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py validate --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py doctor --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa --check-live-hooks --check-codex-grounding
python3 scripts/aoa_session_memory.py audit --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
```

Last observed result:

- `.aoa` tests: `16 passed`
- `codex-grounding`: `ok=true`, `codex-cli 0.130.0`, compact ratio `0.8`
- `validate`: `ok=true`
- `doctor --check-live-hooks --check-codex-grounding`: `ok=true`, no problems, no warnings
- `audit`: `completion_ready=false`, with real compaction boundaries covered,
  standalone local repository and GitHub repository covered, and live
  `PreCompact`/`PostCompact` receipt observation still remaining
- local workspace doctor: `ready=True`
- local workspace hooks doctor: `ready=True`

Current real compaction segmentation:

- `2026-05-01__001__в-прошлой-сессии-мы-на-протяжении-почти-недели`:
  `242` compaction boundaries -> `243` segments.
- `2026-05-06__001__files-mentioned-by-the-user-design.md`:
  `100` compaction boundaries -> `101` segments.
- `2026-05-12__001__aoa-session-dist-exp-идея`:
  `6` compaction boundaries -> `7` segments.

## Coverage Map

| Requirement | Evidence |
| --- | --- |
| Full raw transcript mirror when `transcript_path` is readable | `handle_hook_event`, `sync_session_from_transcript`, tests for raw mirror |
| Raw unavailable is diagnostic, not fake memory | `write_raw_unavailable_incident`, raw-unavailable test |
| PreCompact/PostCompact route compaction intervals | `validate`, compaction hook tests |
| Real Codex `compacted` and `context_compacted` raw events define segment boundaries | rebuilt live archives, `audit`, real compact marker regression test |
| Hook stdout is schema-limited | `codex_hook_output`, protocol-field tests |
| UserPromptSubmit stays light by default | prompt-hook test |
| Real Codex CLI hooks run in standalone sessions | live `codex exec` smoke sessions under `sessions/2026-05-12__002__...` and `__003__...` |
| Session names are readable date/sequence/title labels | naming policy, relabel test |
| Segment Markdown has sibling indexes | segment generation, doctor, tests |
| Rehydration uses indexes before bulk files | `rehydrate`, tests |
| First-pass distillation is provisional | `distill`, tests |
| User-level hooks can be generated from selected roots | `hooks-config`, tests |
| Live hooks match expected commands | `doctor --check-live-hooks` |
| Local Codex compact/hook contract is grounded | `codex-grounding`, local `codex-cli 0.130.0`, project config |
| Clean bundle export excludes sessions by default | `export-bundle`, install/export CLI check |
| Workspace install regenerates hook example for target roots | `install`, install test |
| Install repair does not clear existing sessions by default | preservation test |
| Standalone GitHub repository exists | private repo `8Dionysus/aoa-session-memory`, local `origin` on `main` |
| Completion readiness is explicit rather than inferred from green tests | `audit` command |

## Remaining Gates

These are intentionally not marked complete:

- Observe a real Codex-driven compaction event in a live long session and verify
  that actual `PreCompact` and `PostCompact` payloads match the simulated gate.
- Re-run `codex-grounding` when the local Codex CLI version changes.
- Static `hooks/codex-hooks.user.example.json` uses neutral placeholder paths;
  live hooks must still be generated by `hooks-config` or `install`.

## Probe Notes

Two live `codex exec` probes confirmed that `SessionStart`, `UserPromptSubmit`,
and `Stop` hooks are captured by the installed user-level hooks.

A separate low-threshold compaction probe using a deliberately tiny
`model_auto_compact_token_limit` did not produce `PreCompact`/`PostCompact`.
Instead, the agent repeated the harmless tool call until the probe was stopped.
Do not treat low-threshold `codex exec` as a reliable live compaction trigger.
The remaining gate should be closed by observing a real long-session compaction
or by a Codex-supported compaction trigger, not by counting this probe as
success.

## Rule

Do not mark the whole objective complete until the remaining gates are either
finished or explicitly descoped by the operator.
