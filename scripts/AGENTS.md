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

Run:

```bash
python3 -m py_compile scripts/aoa_session_memory.py
python3 scripts/generate_decision_indexes.py --check
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_session_memory.py
python3 scripts/aoa_session_memory.py validate --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa
python3 scripts/aoa_session_memory.py doctor --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa
```
