# Skills AGENTS.md

## Purpose

This directory holds Codex skills for deliberate session-memory workflows.

Skills are route surfaces for agents. They should make recurring work
repeatable without turning hooks into heavy interpretation.

## Authority

- Each skill directory owns one `SKILL.md`.
- `aoa-session-memory-global-route` is the user-level router target.
- Narrow skills own manual routes such as rehydrate, raw diagnostic, reindex,
  stress pass, audit, doctor, history import, and review packets.

## Rules

- Keep trigger boundaries explicit and narrow.
- Do not promote provisional findings into truth inside a skill.
- Route agents back to source docs and CLI commands instead of duplicating
  large implementation logic.
- If a skill changes portable behavior, update README/readiness where needed,
  export the bundle, and validate source plus standalone mirror.
- Keep global router wording synchronized with live source root and standalone
  mirror expectations.

## Checks

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_session_memory.py
python3 scripts/aoa_session_memory.py doctor --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa --check-user-skill
```
