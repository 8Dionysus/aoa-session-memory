# Skills AGENTS.md

## Purpose

This directory holds Codex skills for deliberate session-memory workflows.

Skills are route surfaces for agents. They should make recurring work
repeatable without turning hooks into heavy interpretation.

## Authority

- Each skill directory owns one `SKILL.md`.
- `aoa-session-memory-global-route` is the default user-level router target.
- `aoa-session-memory-evidence-route` may also be installed as a user-level
  consumer route when agents need prior-session entity, usage, consequence,
  graph, and raw-ref evidence from other owner contexts.
- Narrow skills own manual routes such as rehydrate, raw diagnostic, reindex,
  naming readiness, naming waves, phase discovery, stress pass, audit,
  doctor, history import, search, and review packets.

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

Run `VALIDATION.md` in this directory on demand.
