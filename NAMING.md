# Session and phase naming

Naming makes archives navigable without replacing transcript identity or
promoting generated interpretation into reviewed truth.

## Identity layers

- `session_id` is the stable source identity and remains in the manifest.
- `session_label` is the canonical archive directory label.
- a session name is a semantic navigation label for the whole archive.
- a phase name describes a bounded interval.
- a topic or alias is an additional lookup handle.

These objects are not interchangeable. A late-session topic must not become a
whole-session name merely because it is the strongest visible phrase.

## Directory shape

Canonical archive directories use
`YYYY-MM-DD__NNN__short-title`. The date and sequence provide stable local
ordering; the short title is a readable route. Codex UUIDs never become folder
names.

Directory renaming is a guarded archive operation because registries, indexes,
manifests, generated maps, and evidence refs may depend on the label. Semantic
naming normally updates authored/generated identity views without moving the
archive directory.

## Readiness classes

Naming readiness distinguishes at least these states:

- `blocked` when raw evidence or identity topology is unusable;
- `diagnostic_only` when only failure state can be named safely;
- `needs_reindex` when generated views lag the source;
- `needs_phase_discovery` for large or multi-purpose sessions;
- `phase_discovery_ready` when bounded phase candidates can be built;
- `ready_for_semantic_name` when whole-session evidence is coherent;
- `readable_label` for a useful but still non-semantic route;
- `low_signal` when evidence is insufficient for a durable label;
- `named` when a reviewed semantic name has been applied.

Readiness is navigation. It does not review the candidate or close a naming
queue.

## Evidence requirements

A candidate should retain:

- the covered raw or segment range;
- the user intent and task interval it describes;
- material path, action, verification, error, and decision refs;
- whether it names a session, phase, topic, or alias;
- confidence and visible competing interpretations;
- the next review route.

Weak candidates remain weak. Generic prompts, sparse late fragments, and
classifier-only labels should route to review or remain readable aliases.

## Phase discovery

Long sessions are decomposed into bounded candidate phases before whole-session
naming. Phase discovery writes generated candidate records with evidence refs,
coverage, signal bundles, and a review queue. It does not apply names.

Review assistance may batch several candidates, but the accepted name must
still be supplied through the guarded review route. Empty or unresolved plan
entries are skipped rather than guessed.

## Naming waves

Naming waves group preflight repairs, reviewed session-name candidates, open
phase queues, diagnostic-only archives, and low-signal probes. Applying a wave
changes only reviewed entries. Auditing a wave checks identity agreement and
evidence routing after application.

Waves do not rename archive directories and do not turn generated candidates
into reviewed memory.

## Generated indexes

`SESSION_NAMES.md`, `session-name-index.json`, `sessions/INDEX.md`, and
`sessions/index.json` are generated navigation. They group sessions, expose
readiness queues, and route readers to the per-session manifest and indexes.
They are regenerated after accepted naming changes.

## Command authority

The naming subcommands in `scripts/aoa_session_memory.py` own exact syntax and
mutation guards. Agent procedures live in the naming-related `skills/`
routes. This document owns semantics only and intentionally carries no copied
command catalog.
