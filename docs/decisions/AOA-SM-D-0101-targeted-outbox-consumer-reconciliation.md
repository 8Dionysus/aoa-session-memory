# Targeted Projection Outbox Consumers Reconcile One Exact Obligation

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0101
- Original date: 2026-08-23
- Owner surfaces: scripts/aoa_session_memory.py, tests/, docs/decisions/
- Surface classes: projection, freshness, orchestration, evidence boundary
- Projection layers: component-delta outbox, exact consumer state, retirement
- Guard families: immutable identity, allowlisted route, dependency order, resource admission, bounded retry
- Posture: accepted

## Context

The component-delta outbox records changed-component work intent, but the
existing compatibility helpers can route several consumers together or
acknowledge work from broader maintenance and ledger paths. A superseded
publication must not receive a completion receipt, and a green process or
queued state must not retire an obligation. The accepted targeted audit also
showed that the named old record had no safe exact consumer route. The audit
also found that a bare or unresolvable commit reference, a generic handler
return, a lock without an admission receipt, and an incomplete record schema
could all be mistaken for semantic consumer completion.

The replacement review reproduced seven additional faults: a missing
consumer-owned artifact admitted from handler output alone; a committed
receipt followed by a handler exception that replayed the same operation;
publication advancing at the semantic write boundary; an expired lease;
mutation of `created_at` without changing `record_id`; a caller widening a
record retry policy of one; and an entity axis remaining current after search
was demoted. Those cases are contract regressions, not documentation-only
claims.

## Options Considered

- Reuse global or multi-consumer maintenance and infer completion from its
  process result. Rejected because it can search, graph, or rebuild outside
  the exact session and cannot bind one consumer receipt to one publication.
- Mark the outbox record retired after one consumer or one progress receipt.
  Rejected because downstream consumers and their dependencies remain
  independently incomplete.
- Add one source-owned reconcile contract with exact identity, one target
  consumer, bounded dependency checks, targeted-route proof, a typed resource
  admission and lease receipt, an operation journal for crash recovery,
  consumer-specific semantic evidence resolved from owner artifacts,
  completion receipts, a shared publication/completion fence, and a terminal
  all-consumers recheck.

## Decision

reconcile_projection_outbox_consumer() and the
projection-outbox-consumer-reconcile command accept exact session_id,
record_id, expected_publish_id, and one allowlisted consumer. They read the
content-addressed record directly and refuse a missing, mismatched, or
superseded identity.

The contract uses the fixed dependency order
exact_and_lexical_search, episode_semantic, entity_registry, graph.
The selected consumer can run only after its exact predecessor receipts are
complete. Attempts are finite and bounded by the outbox policy. A dry run
never calls a handler, takes the resource lock, or writes a state.

An apply requires an exact resource-admission artifact with a content-bound
lease receipt and concurrency one; the non-blocking owner lock is only an
additional serialization guard. The injected route must match the immutable
source-owned route registry, be available, targeted to the exact session, and
free of global, atlas, narrative, full rebuild, or all child-command markers.
The returned handler result must repeat the exact consumer aliases,
publication aliases, operation, route, attempt, and admission identities.
Its typed commit reference must resolve to the immutable operation receipt;
the receipt is then checked against the consumer-specific evidence contract
grounded in DESIGN.md and PIPELINE.md. The semantic check independently
resolves the actual search DB generation, episode state, entity registry
snapshot, or graph mutation plus source-state ledger. It verifies typed
contents, exact record/publish/change set, and fixed owner provenance; handler
output is never an authority substitute. A committed operation journal is
persisted before semantic state, and the same logical operation is re-resolved
after a handler exception before any attempt increment or redispatch.
Conflicting evidence fails closed. Publication, completion, and retirement
share one owner-versioned session fence; a publication drift at the write
boundary removes the stale complete state and does not retire the record. The
source writes one typed completion receipt for that consumer; it writes a
separate retirement receipt only after an exact current record/manifest/publish
recheck proves every required consumer receipt.

## Rationale

The outbox record and current session manifest are the smallest authoritative
identity pair available for this repair. Direct content-addressed lookup
avoids a global record search. One consumer per invocation keeps the effect
and receipt attributable, while explicit dependencies preserve the owner
pipeline order. The record validator requires the complete immutable shape,
including artifact type, creation time, retry policy, publication receipt, and
truth status, then recomputes the content-addressed record id. Separate owner
artifact resolvers preserve the semantic distinctions already established by
the owner pipeline: committed changed-component search, current/no-episode
semantic state, current entity registry with exact search and route
dependencies, and committed graph mutation with the source-ledger publication
identity. Each resolver checks the live owner artifact again, so a later search
demotion invalidates dependent entity freshness. A second currentness recheck
prevents a partial consumer set from being promoted to terminal retirement.
Requiring an owner resource-authority artifact, a typed admission/lease
receipt with `now < expires_at`, and a concurrency-one lock keeps the route
compatible with bounded host capacity without treating caller JSON or the
lock as authority.

## Consequences

- Positive: superseded records, unavailable routes, missing dependencies,
  resource denials, and global-child attempts fail closed without completion.
- Positive: completion and retirement are durable, independently inspectable,
  and bound to exact session and publication identities.
- Positive: crashes after a committed handler side effect recover from the
  operation journal or same-operation receipt without re-executing the
  handler, even when the handler raises after commit; receipt or journal
  conflicts remain non-semantic and fail closed before retry accounting.
- Positive: publication and semantic completion cannot cross the same
  owner-versioned fence; a drift probe leaves no stale complete state or
  retirement artifact.
- Positive: record-id coverage and the record retry policy are immutable, and
  typed nested evidence plus owner provenance are checked recursively.
- Positive: legacy/manual/global/full-rebuild paths can leave only explicit
  progress state, never an authoritative completion receipt or freshness
  admission.
- Tradeoff: the source CLI intentionally has no default targeted handler until
  an owner route supplies one with the required proof; the contract therefore
  reports an unavailable route rather than falling back to broad maintenance.
- Follow-up: the owning integration route must register a real targeted
  handler and supply independently verified consumer commit references.

## Boundaries

This decision does not activate the live .aoa root, edit live outbox state,
install a portable bundle, merge a branch, or prove search, graph, Atlas,
narrative, or global freshness. A completion receipt is not global freshness,
and retirement covers only the named outbox record's required consumers.

## Source Surfaces

- scripts/aoa_session_memory.py
- tests/test_projection_outbox_consumer_reconcile.py
- DESIGN.md
- PIPELINE.md
- docs/decisions/

## Follow-Up Route

The goal master should request a fresh independent semantic and lineage review
of this replacement commit, then bind a real source-owned targeted consumer
handler in a separate owner lane. Any installed or live activation must pass
the normal portable export, admission, deployment, runtime proof, and
acceptance lanes. No live activation is part of this source repair.

## Verification

The focused integration suite covers exact identity binding, supersession,
allowlist and dependency order, dry-run no-effect behavior, resource and
attempt gates, route-registry and owner lease admission, no-global-child
behavior, independently resolved consumer artifacts, all seven reviewed fault
probes (missing artifact, receipt-then-exception, write-boundary publication
advance, expired lease, created-at mutation, retry-policy-one, and
entity-after-search-demotion), wrong-holder/forged-source/route/alias/attempt
mismatches, crash recovery and conflicting replay, post-handler currentness
rechecks, complete receipt shape, legacy progress, and terminal retirement
replay. Source compilation, decision-index regeneration/check, public-tree
audit, and the owner narrow validation are required before handoff. The live
root and remote state remain read-only and are not presented as verified here.
