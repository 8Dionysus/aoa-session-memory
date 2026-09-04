# Scripts AGENTS.md

## Purpose

This directory owns the CLI and hook implementation for the portable
session-memory kernel.

The script is both operator tool and hook entrypoint. Changes here have runtime
blast radius.

## Authority

- `aoa_session_memory.py` implements archive generation, hook handling,
  indexing, naming, distillation, validation, export, install, audit, and
  doctor checks.
- `aoa_epistemic_action_event_chain.py` implements the portable append-only
  prediction/action/observation chain, replay and concurrency guards, typed
  discrepancy states, and shadow-only candidate inspection. It is re-exported
  by `aoa_session_memory.py` but is not wired into the foreground hook.
- `generate_decision_indexes.py` derives portable lookup indexes from canonical
  `docs/decisions/AOA-SM-D-*.md` records and checks their parity.
- `validate_local_stats_port.py` delegates the owner-local measurement packet
  to the pinned central `aoa-stats` protocol validator.

## Rules

- Keep hook paths bounded, schema-valid, and fail-open.
- Prefer structured parsing and JSON writes over ad hoc text mutation.
- Do not delete or rewrite raw session evidence without an explicit repair
  route and diagnostic record.
- Update tests when changing generated file shape, root required files,
  export/install behavior, or hook output.
- When portable behavior changes, export to the standalone mirror and validate
  both source and bundle.

## Checks

Use the applicable root, decisions, and session-memory route from the
corresponding `VALIDATION.md` file on demand.
