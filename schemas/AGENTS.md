# Schemas AGENTS.md

## Purpose

This directory holds JSON schema contracts for portable archive artifacts.

Schemas define machine shape. They do not decide runtime truth, review status,
or naming semantics by themselves.

## Authority

- `hook-receipt.schema.json` describes persisted hook receipts.
- `incident.schema.json` describes diagnostic incidents.
- `segment.index.schema.json` describes generated segment event indexes.
- `session.manifest.schema.json` describes session archive manifests.

## Rules

- Keep schema changes backward-aware. Existing archives may outlive the code
  version that created them.
- Do not relax required evidence fields just to make bad data pass.
- If a schema changes, update writer code and regression tests together.
- Generated archives should be repairable from raw evidence or explicit
  diagnostics, not by silently weakening schemas.

## Checks

Run:

```bash
python3 -m py_compile scripts/aoa_session_memory.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_session_memory.py
```
