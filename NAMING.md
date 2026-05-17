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

Replacing the active `session` name removes the prior active session name from
navigation by default. Do not keep superseded wording as an alias unless it is
a deliberately useful operator route. Create aliases explicitly with
`--scope alias`; do not let old incomplete names accumulate as routing noise.

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

When a lightweight hook mirrors a growing transcript without reindexing it,
the semantic name must keep its last verified raw identity instead of replacing
`raw_sha256` or `raw_line_count` with empty deferred metadata. Treat
`raw_anchor_status: deferred_refresh_preserved_verified_anchor` as a signal to
reindex before final review, not as a broken name.

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
- `needs_sync`: source transcript is newer than the archived raw copy; sync the
  source before reindexing or naming.
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

`named` is not a closed state. If meaningful raw content appears beyond the
active session-name coverage range, readiness should keep the session in the
queue with `active_session_name_coverage_stale` so a later pass can either
widen the coverage or revise the umbrella name. Pure technical tails such as
`token_count` or `task_complete` are not enough to make a name stale.

A named session may still have unfinished inner naming work. If
`phase-discovery.json` contains a non-empty `review_queue`, readiness keeps the
named session visible with `phase_discovery_review_queue_open` and routes it to
`review_open_phase_discovery_for_named_session`. The active session name can be
usable while phase/topic synthesis remains open; do not treat that as final
settlement.

When `review-phase-name --apply` accepts a reviewed name for a weak phase
candidate, it must also mark the phase-discovery candidate as
`applied_reviewed_name` and refresh the artifact's `review_queue`. Otherwise
the archive will carry a correct semantic phase name while still routing future
agents to the old machine-generated weak title.

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

For long sessions, use the assist layer before manually opening raw again:

```bash
python3 scripts/aoa_session_memory.py phase-review-assist <session-label-or-id> \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --from-segment <segment-id> \
  --limit 8 \
  --write \
  --write-report
```

`phase-review-assist` creates a batch packet from preserved raw: user requests,
progress markers, decisions, closeout notes, validations, errors, mutations,
commands, and top paths. This is an acceleration layer for semantic synthesis,
not permission to apply weak machine candidates.

After a reviewer fills `reviewed_name` values into a plan JSON, apply the
reviewed batch through the plan route:

```bash
python3 scripts/aoa_session_memory.py apply-phase-review-plan <session-label-or-id> \
  --plan sessions/<session>/naming/phase-review-plan.json \
  --apply \
  --write-report
```

The plan route skips empty `reviewed_name` entries and applies each non-empty
item through the same guarded phase-name writer used by `review-phase-name`.
It does not treat machine candidates or `--use-candidate` as reviewed truth.

For many sessions, use a naming wave instead of repeating one-session commands:

```bash
python3 scripts/aoa_session_memory.py naming-wave build \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --write \
  --write-report
```

`naming-wave build` creates a multi-session review plan. It routes `needs_sync`
and `needs_reindex` entries as preflight work, proposes semantic session names
for ready/readable sessions, carries raw evidence refs and coverage where
available, and marks every item with `physical_relabel_allowed=false`.

After reviewing the plan, fill `reviewed_name` for accepted session-level
names and apply only reviewed items:

```bash
python3 scripts/aoa_session_memory.py naming-wave apply \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --plan diagnostics/naming-waves/<wave-id>/naming-wave-plan.json \
  --apply \
  --write-report
```

Run a quality pass before and after mass application:

```bash
python3 scripts/aoa_session_memory.py naming-wave audit \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --plan diagnostics/naming-waves/<wave-id>/naming-wave-plan.json \
  --sample-size 18 \
  --sample-seed wave-quality-1 \
  --write-report
```

The sample is deterministic and stratified by quality bucket: preflight work,
flagged names, unflagged instruction residue, fallback names, short names, and
ordinary `ok` candidates. Each sampled item includes raw evidence preview text
from the candidate's first raw refs. This makes the long polishing loop
repeatable: sample, inspect raw preview, add a narrow golden case for any
defect class, rebuild, and sample again with a new seed.

Naming waves are semantic-name waves. They do not physically relabel archive
directories. Physical relabel remains a later, narrower operation after the
semantic map and anchors are trusted.

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
