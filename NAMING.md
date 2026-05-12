# Naming Topology

Names are routing surfaces. Agents should be able to understand the archive
shape before opening raw files.

## Canonical Paths

- `sessions/` stores physical session archives.
- `sessions/YYYY-MM-DD__NNN__short-title/` is the canonical session directory.
- `SESSION.md` is the human and agent entry file inside a session directory.
- `session.index.json` is the machine-readable companion index.
- `session.manifest.json` stores technical identity such as Codex `session_id`.
- `raw/source.json` stores the raw transcript provenance.
- `session-registry.json` is the root lookup table for all sessions.
- `codex-sessions/` is legacy-only and should be empty after migration.

## Session Labels

Session labels use:

```text
YYYY-MM-DD__NNN__short-title
```

- `YYYY-MM-DD` is the first trustworthy session date from raw evidence.
- `NNN` is the day-local sequence.
- `short-title` is derived from the first real user intent, not AGENTS,
  environment, or hook envelope text.

## Fallback Words

Use explicit unresolved names instead of vague placeholders:

- `unresolved-session-<stamp>` when no session id is available.
- `untitled-session` when no meaningful title is available.
- `unresolved-source` for malformed raw event sources.

Do not introduce `unknown`, `misc`, `tmp`, `new`, `old`, `stuff`, or
`placeholder` into durable archive names.

## Generated Segment Roles

Segment file roles describe the evidence interval:

- `initial-to-compaction`
- `compaction-to-compaction`
- `initial-to-latest`
- `compaction-to-latest`

Do not use ambiguous interval names such as `current` in durable generated
file names.
