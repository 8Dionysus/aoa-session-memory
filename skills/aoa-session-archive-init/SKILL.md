---
name: aoa-session-archive-init
description: Use when a `.aoa` session-memory root must be created, installed, checked, repaired, or prepared for Codex hook-based session archiving.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-archive-init

Use when the `.aoa` session-memory root must be created, checked, or repaired
before Codex session archiving starts.

## Trigger Boundary

- `.aoa` does not exist or is incomplete.
- Hook integration needs a root to write session archives.
- A portable bundle install needs a minimal filesystem contract.

## Inputs

- workspace root
- desired `.aoa` root
- storage policy or local operator constraints

## Procedure

1. Read nearest `AGENTS.md`.
2. Confirm the `.aoa` root is inside the intended workspace or explicit
   storage root.
3. Ensure `AGENTS.md`, `DESIGN.md`, `DESIGN.AGENTS.md`, `PIPELINE.md`,
   `NAMING.md`, `README.md`, `INSTALL.md`, `config/AGENTS.md`,
   `hooks/AGENTS.md`, `schemas/AGENTS.md`, `scripts/AGENTS.md`,
   `skills/AGENTS.md`, `tests/AGENTS.md`, `sessions/`, and
   `sessions/AGENTS.md` exist.
4. For a new workspace, use `install --workspace-root <root>` rather than
   copying hook JSON by hand.
5. Generate hook config with
   `python3 .aoa/scripts/aoa_session_memory.py hooks-config --workspace-root <root> --aoa-root <root>/.aoa`.
6. Run `python3 .aoa/scripts/aoa_session_memory.py codex-grounding --workspace-root <root> --aoa-root <root>/.aoa` on hosts that have Codex installed.
7. Run `python3 .aoa/scripts/aoa_session_memory.py validate --workspace-root <root> --aoa-root <root>/.aoa`.
8. Run `python3 .aoa/scripts/aoa_session_memory.py doctor --workspace-root <root> --aoa-root <root>/.aoa`.
9. Report missing surfaces without inventing memory claims.

## Verification

- `.aoa/AGENTS.md` exists.
- `.aoa/INSTALL.md` exists for portable setup.
- `.aoa/scripts/aoa_session_memory.py` compiles.
- `export-bundle` always creates a public-safe bundle without session archives
  or raw evidence. The legacy `--with-sessions` spelling is retained only to
  fail explicitly and direct private transfers to an owner-to-owner migration
  route.
- `portable-public-safety-audit` reports no credential, host-path, runtime
  database, diagnostics, session-evidence, or incomplete-coverage findings.
- `hooks-config` emits all required Codex lifecycle hooks for the selected
  roots.
- `codex-grounding` passes on a host with Codex installed.
- `validate` passes the temporary light-hook preservation run and explicit
  full-sync archive run.
- `doctor` exits successfully before any session exists.

## Stop Line

Do not import old Downloads material or project-specific doctrine into the
portable kernel.
