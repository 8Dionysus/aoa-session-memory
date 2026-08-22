# Transactional Component Outbox and Vector Freshness

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0051
- Original date: 2026-08-10
- Owner surfaces: `scripts/aoa_session_memory.py`, `schemas/projection-outbox.schema.json`, `DESIGN.md`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: publication, incremental maintenance, freshness, search, graph, recovery
- Projection layers: session components, search, episode semantic, entity registry, graph
- Guard families: atomic publish, transactional outbox, idempotent replay, component delta, tombstone, last-good preservation, honest freshness
- Posture: accepted

## Context

Atomic session publication previously called downstream dirty propagation only
after the publish journal had been removed. A process crash in that gap could
make a new session generation visible without durable downstream work intent.
Dirty graph propagation also enumerated every segment in the session even when
only the open tail changed.

Freshness was often summarized as one state. That made a current captured tail
look blocked by a stale graph, or risked the inverse mistake of treating fresh
raw evidence as proof that every derived recall surface was complete.

## Options Considered

- Keep post-publication best-effort dirty marking. Rejected because work intent
  can be lost in a crash window.
- Put mutable consumer retry state inside session indexes. Rejected because it
  would change semantic session artifacts for operational bookkeeping.
- Queue whole sessions for every consumer. Rejected because ordinary append
  cost remains proportional to historical session topology.
- Commit an immutable changed-component outbox record inside the publication
  journal boundary, keep mutable consumer states separately, and expose
  freshness as independent axes.

## Decision

Before atomic replacement, the publisher compares the last-good and staged
component snapshots. It records publish, replace, and tombstone operations for
raw blocks, segment indexes, task episodes, the session component manifest,
and session manifest. Segment comparison uses its semantic input digest and
generation rather than the restamped umbrella publish identity.

After every session component has been replaced and the loaded producer guard
still validates, the publisher writes one deterministic immutable outbox record
under `projection-outbox/records/`. Only then does it mark the publish journal
committed. A crash before that mark rolls back session files and removes a newly
created outbox record. Recovery of an already committed journal finalizes
cleanup without rolling the publication back. Repeating the same transition
reuses the exact record and rejects an identity collision.

Outbox records and consumer completion states use temp-file fsync, atomic
rename, and parent-directory fsync. A crash before completion publication
leaves the consumer pending. Replaying the identical completion receipt is a
no-op and does not increment attempts; a different receipt for an already
completed record is a fail-closed collision.

Each change names its required downstream consumers. Mutable per-consumer
states are stored separately and cannot claim completion without a completion
receipt. Initial propagation records `queued` or `deferred`, never semantic
completion. Graph dirty propagation selects only changed segment component IDs
plus the session contribution; sealed unchanged segments are not requeued.

Exact and lexical search acknowledge a record only after the changed component
has been applied to the committed search generation. The same committed search
transaction acknowledges episode semantic only when its per-session result is
`current`, `no_task_episodes`, or `no_admitted_episode_text`; the result is
joined by explicit session ID so a successful projection cannot remain
silently deferred. Entity-registry
acknowledgement additionally requires that exact search receipt and a current
route dependency. Graph acknowledgement is emitted only after a successful
mutation whose source ledger entry carries the same session publish identity
as the outbox record. These are consumer-specific proofs; success in one
consumer never completes another.
If an orchestration retry encounters an already complete state for the same
record, consumer, and source publish identity, it returns that durable state
without attempting to replace its original completion receipt. A direct
conflicting receipt for the same completion key still fails closed.

`freshness-vector` reports raw capture, persistent live overlay, stable session
projection, search, episode semantic, entity registry, graph, returned evidence,
and global recall independently. One current axis never promotes another. A
positive overlay result may be current for returned evidence while global
negative claims remain disallowed until the relevant recall axes carry exact
completion receipts.

## Rationale

The outbox closes the publication-to-maintenance loss window while keeping
operational retry state outside semantic artifacts. Component deltas are the
right downstream unit because they preserve replacement and tombstone meaning
without forcing a full session rescan. A freshness vector makes availability
and incompleteness simultaneously visible instead of choosing one misleading
boolean.

## Consequences

- Positive: a committed session generation has durable downstream work intent.
- Positive: rollback cannot leave a newly written valid-looking outbox record
  for an unpublished generation.
- Positive: unchanged sealed segments are omitted from graph dirty work.
- Positive: consumer replay is idempotently addressable by record and component
  digest.
- Positive: current raw/live evidence remains usable while graph or semantic
  projections lag.
- Tradeoff: outbox and consumer-state retention need bounded compaction after
  every consumer has exact completion receipts.
- Tradeoff: bounded retry/lag policy and safe outbox compaction still require
  end-to-end proof; queued/deferred state is intentionally not treated as
  completion.

## Boundaries

An outbox record is work intent, not proof that a downstream projection is
current. A queued graph source is not a completed graph update. Global recall
and exhaustive negative claims remain false until the relevant scope proves
completion. Outbox records contain component identities and digests, not raw
bodies, sensitive literals, or reversible secret digests. This decision does
not authorize live `.aoa` deployment.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `schemas/projection-outbox.schema.json`
- `tests/test_session_memory.py`
- `DESIGN.md`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Make timer maintenance finish all ready consumer states directly, add bounded
retries and lag SLOs, then
compact only records complete for every required consumer.

## Verification

Focused tests cover schema validation, atomic rollback, deterministic outbox
publication, append delta selection, sealed-segment omission, exact search,
entity-registry and graph completion gates, consumer routing states, and
independent freshness axes. Exact episode-semantic acknowledgement and
missed-hook hot-timer recovery are covered. Crash injection proves pending
state before completion, durable replay after restart, identical-receipt
idempotence, conflicting-receipt refusal, atomic session rollback, and
committed-journal recovery. Portable export and live-equivalent lag receipts
remain required before the rollout is declared complete.
