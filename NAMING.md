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
python3 scripts/aoa_session_memory.py name-session <session> \
  --name "aoa-techniques repo ordering and canonization" \
  --scope session \
  --kind session_essence \
  --evidence raw:line:123 \
  --apply
```

For phase-discovery candidates, use the guarded review route instead of
copying low-level `name-session` arguments by hand:

```text
python3 scripts/aoa_session_memory.py review-phase-name <session> \
  --segment 003 \
  --reviewed-name "reviewed phase name" \
  --apply \
  --write-report
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

## Naming Readiness

Before a broad naming pass, run the readiness layer:

```bash
python3 scripts/aoa_session_memory.py naming-readiness all \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --refresh-indexes \
  --write-report
```

Readiness is a routing index, not a judgment. It classifies each session into
the next honest action:

- `blocked`: repair missing or unrecoverable raw/index state before naming.
- `diagnostic_only`: keep raw-unavailable hook-only diagnostics visible without
  putting them ahead of recoverable naming work.
- `needs_reindex`: refresh generated segments/indexes from preserved raw before
  choosing a semantic name.
- `needs_phase_discovery`: inspect segment indexes and create phase/topic
  candidates before assigning a whole-session name.
- `phase_discovery_ready`: review generated phase/topic candidates before
  applying a whole-session name.
- `ready_for_semantic_name`: apply a semantic session name with raw evidence
  refs and bridge anchors.
- `readable_label`: the canonical label is good enough unless a later review
  finds a better semantic name.
- `low_signal`: tiny probes can stay as canonical labels unless they become
  operationally important.
- `named`: verify or refine the existing semantic name instead of starting
  over.

The readiness queue is mirrored into `SESSION_NAMES.md`,
`session-name-index.json`, `sessions/INDEX.md`, and `sessions/index.json`.
Use it to choose the next pass. Do not use it to close review or promote a name
as truth.

For `needs_phase_discovery`, generate the open candidate layer:

```bash
python3 scripts/aoa_session_memory.py phase-discovery <session-label-or-id> \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --write \
  --write-report
```

The generated `naming/phase-discovery.json` and `.md` files contain unreviewed
phase candidates with raw-line coverage. They make the next naming pass faster,
but they do not apply or close any semantic name.

Each phase candidate should be read as a signal bundle, not a title string:

- `name_basis=specific_user_intent` means a usable user request anchored the
  candidate.
- `name_basis=linked_path_event_signals` means the user text was missing or too
  generic, so the candidate is synthesized from touched paths, event counts,
  commands, checks, errors, and mutations.
- `quality_flags` expose weak naming inputs instead of hiding them behind a
  confident-looking phrase.

This linked-signal layer is expected everywhere, including strong candidates.
It lets weak candidates diagnose the process and lets strong candidates show
why their names are deserved.

Diagnostics are only half of the pass. The other half is `review_queue`: weak
or path/event-based candidates must route to semantic synthesis with an
explicit next action and an apply template. A candidate is not ready to become a
semantic name merely because it was detected.

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
