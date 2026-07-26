# Task-Episode Interval Membership for Search Events

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0032
- Original date: 2026-07-26
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: episode formation, semantic retrieval, exact retrieval, evidence granularity
- Projection layers: task episodes, search event documents, episode joins, evidence packets
- Guard families: semantic boundary, evidence refs, exact recall, projection reproducibility
- Posture: accepted

## Context

Task episodes carry a semantic event interval and a smaller set of curated
intent, action, result, failure, decision, and verification refs. Search event
documents originally received a `task_episode_id` only when their event ID was
one of those curated refs.

That confused evidence selection with episode membership. A large structured
tool result or reviewed receipt could lie inside the confirmed episode
interval, remain resolvable and important for evaluation, yet disappear when a
consumer scoped exact search to the episode because it was not selected as a
curated summary ref.

## Options Considered

- Treat only curated refs as episode members. Rejected because curated refs are
  bounded highlights and do not exhaust the episode's evidence.
- Add every event as a curated episode ref. Rejected because it would inflate
  episode payloads and erase the distinction between semantic highlights and
  interval evidence.
- Ignore episode scope for exact search. Rejected because it would restore
  recall by widening into unrelated session evidence.
- Keep curated refs as highlights while assigning search-event membership from
  the confirmed task-episode interval when no explicit curated mapping exists.

## Decision

Task-episode event intervals define membership for search joins. Curated
episode refs remain the higher-specificity semantic highlights.

When building a search event document, an explicit curated event-to-episode
mapping is used first. Otherwise, an event with a resolvable raw line inside a
valid task-episode interval receives that episode ID. Events outside every
valid interval remain unassigned rather than being attached by lexical or
semantic similarity.

The interval mapping is a generated join over the current task-episode source
generation. It does not change raw evidence, copy the event into the episode
payload, or make the event an admitted result, verification, consequence, or
causal relation.

## Rationale

An episode boundary describes the span of work, while curated refs describe
the most useful evidence within it. Preserving both roles lets exact and
structured retrieval stay episode-scoped without losing important
non-highlight events.

Using raw-line membership is deterministic and evidence-addressable. It avoids
the semantic noise of widening a missing episode hit into session-wide fuzzy
search.

## Consequences

- Positive: episode-scoped exact search can recover all indexed events in the
  episode interval, including large structured results omitted from curated
  highlights.
- Positive: episode payloads remain bounded and meaningful.
- Positive: the search join is reproducible from task-episode ranges and raw
  coordinates.
- Tradeoff: a task-episode boundary correction changes the join and requires
  search catch-up.
- Tradeoff: interval overlap or missing raw coordinates must remain an
  integrity problem rather than being guessed through semantic similarity.
- Follow-up: retain positive and negative tests for uncurated in-range events,
  out-of-range events, and evidence-ref resolution.

## Boundaries

Interval membership does not prove procedure compliance, invocation, success,
causality, ownership, verification, or consequence. A returned event remains a
candidate until its raw ref, source kind, correlation, freshness, and relevant
claim gate are checked.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Rebuild the affected search projection, run episode-scoped exact and semantic
queries, open the returned raw refs, and compare the result with an
independently selected sealed evidence case.

## Verification

A regression fixture places a large reviewed output inside a task episode while
excluding it from curated refs, rebuilds search, and requires the event to
remain discoverable under the episode filter with its original raw ref.
Runtime evaluation repeats the same route on independently selected owner
evidence and checks that claim admission remains conservative.
