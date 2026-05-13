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
- `sessions/INDEX.md` is the local table of contents for the archive directory.
- `sessions/index.json` is the machine-readable companion for that table of contents.
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

## Semantic Names And Name Index

Canonical labels are stable archive coordinates. They are not the only useful
name for a session.

A long session may have several true names at different scopes:

- `session`: the current umbrella essence of the whole session.
- `phase`: a bounded process inside the session.
- `topic`: a useful local subject that may not dominate the whole session.
- `alias`: an operator-facing alternate route.

When the real subject of a long session becomes clearer, attach a semantic
name instead of renaming the archive blindly. Use `session` for the mutable
umbrella name and `phase` for late-process names:

```text
aoa-session-memory.py name-session <session> \
  --name "aoa-techniques repo ordering and canonization" \
  --scope session \
  --kind session_essence \
  --evidence raw:line:123 \
  --apply
```

Semantic names live in `session.manifest.json` under `semantic_names`, mirror
into `session-registry.json` and `session.index.json`, and are accepted by
`show`, `rehydrate`, and other session resolvers.

The active `session` name is the preferred working title. `phase` and `topic`
names remain linked and searchable, but they must not replace the whole-session
name unless their scope is deliberately promoted after review.

Every applied semantic name must carry a bridge anchor:

- `session_id`
- current canonical label and archive path
- source transcript path
- raw archive path
- raw byte count, line count, and sha256 when available
- raw evidence refs such as `raw:line:123`
- optional coverage ranges such as `from_line..to_line`

This lets a custom name speak clearly while the raw transcript remains the
source of truth. If a later relabel moves the physical archive, the anchor is
refreshed to the current path while preserving the session id and raw hash
identity.

The root `session-name-index.json` and `SESSION_NAMES.md` are lightweight name
maps. They are not source truth. They exist so an agent can compare current
session essence names, phase names, evidence refs, and coverage hints before
choosing or revising a final working title.

The `sessions/INDEX.md` and `sessions/index.json` pair is the archive-local
table of contents. It should be the first stop after root design and naming
surfaces when an agent needs to choose a historical session. It groups archives
by date, highlights named sessions, and lists the largest sessions without
making the root directory carry every navigation concern.

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
