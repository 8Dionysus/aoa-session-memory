# Sessions AGENTS.md

## Purpose

This directory is the archive district for preserved Codex sessions.

It contains generated navigation plus one directory per session. Do not use a
raw filesystem listing as the route.

## Task Routes

- Orientation: `INDEX.md` or `../SESSION_NAMES.md`.
- Known session: its `AGENTS.md`, then `session.index.json`.
- Identity/status: `session.manifest.json`; reviewed brief: `SESSION.md`.
- Exact expansion: the relevant segment index before Markdown; raw JSONL only
  for exact verification, recovery, or durable evidence anchors.

Do not bulk-open archive maps or raw evidence.

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
