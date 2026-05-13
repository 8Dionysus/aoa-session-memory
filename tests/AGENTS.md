# Tests AGENTS.md

## Purpose

This directory holds regression tests for archive behavior, hook behavior,
portable export/install, route surfaces, naming, distillation, and validation.

Tests protect the route mesh from silent drift.

## Rules

- Use temporary workspaces and generated fixtures.
- Do not depend on live user transcripts unless a test explicitly marks a
  host-grounding behavior and remains bounded.
- Add or update tests when changing required root files, generated indexes,
  hook output, naming, export/install, or readiness gates.
- Keep tests focused on contracts rather than incidental timestamps or local
  archive counts.

## Checks

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_session_memory.py
```
