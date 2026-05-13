# Sessions AGENTS.md

## Purpose

This directory is the archive district for preserved Codex sessions.

It contains generated archive-local navigation plus one directory per
session. Do not treat a raw filesystem listing as the route. Start from
this card, then use the generated indexes and session-local cards.

## Read Order

1. `AGENTS.md`
2. `INDEX.md`
3. `../SESSION_NAMES.md`
4. `../session-registry.json`
5. `<session>/AGENTS.md`
6. `<session>/SESSION.md`
7. `<session>/session.manifest.json`
8. `<session>/session.index.json`
9. `<session>/segments/*.index.json` before opening segment Markdown
10. `<session>/raw/session.raw.jsonl` only for exact verification,
    recovery, or durable evidence anchors

## Authority

- `INDEX.md` and `index.json` are generated
  tables of contents for navigation.
- `../SESSION_NAMES.md`, `../session-name-index.json`, and
  `../session-registry.json` are root-level generated maps.
- `<session>/session.manifest.json` owns technical identity and archive
  status for a single session.
- `<session>/raw/session.raw.jsonl` is preserved evidence.
- Review, distillation, naming, and promotion outputs remain provisional
  until their own reviewed route says otherwise.

## Rules

- Do not manually rename archive directories without following
  `../NAMING.md` and preserving the `session_id` bridge.
- Prefer semantic `name-session` entries before physical relabels when
  the archive already has stable raw provenance.
- Treat `raw_unavailable` and `raw_mirrored_index_deferred` as explicit
  states, not as understood sessions.
- Do not open bulk raw before checking the target session indexes.
- Keep generated indexes reproducible from raw evidence or explicit
  review artifacts.
