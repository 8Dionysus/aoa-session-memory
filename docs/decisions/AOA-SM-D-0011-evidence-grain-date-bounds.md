# Evidence-Grain Date Bounds

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0011
- Original date: 2026-07-17
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `DESIGN.AGENTS.md`
- Surface classes: query routing, exact retrieval, temporal filtering, access contract
- Projection layers: exact literal postings, live-tail exact fallback, archived raw exact fallback, session document search, episode search
- Guard families: event timestamp, session-date fallback, evidence-grain routing, bounded abstention
- Posture: accepted

## Context

A date bound can refer to different temporal coordinates at different evidence
grains. General archive documents are organized by session date, episodes
represent a time span, and exact event evidence has its own recorded timestamp.
Applying the session-start date to every route causes exact events later in a
multi-day session to disappear from a query for the day on which they actually
occurred.

The exact-literal projection already stores the source event timestamp, and
live or archived raw events expose the same coordinate. The recall failure was
therefore a query-law mismatch rather than missing evidence or a schema
capacity problem.

## Options Considered

- Keep session date as the universal date filter. This preserves one simple
  interpretation but loses exact event recall in multi-day sessions.
- Use event date for every search document. Session summaries and other
  aggregate documents do not necessarily represent one event, while episodes
  represent spans; forcing an event coordinate onto them changes their meaning.
- Add another persistent event-date projection and reindex the archive. This
  duplicates a timestamp already present in exact posting metadata and raw
  evidence without solving the different semantics of session and episode
  rows.
- Interpret date bounds by evidence grain, expose the chosen basis, and use
  session date only as a fallback when an exact event lacks a usable timestamp.

## Decision

Interpret date bounds according to the temporal grain of the selected route.

Exact literal postings, the append-only live-tail exact fallback, and the
session-scoped archived raw exact fallback compare the recorded event date.
When an exact event has no usable timestamp, those routes fall back to the
session date. General search documents continue to use session date. Episode
routes continue to use time-span overlap, with session date only as their
fallback.

The literal and top-level query planners expose a compact
`date_filter_contract` naming these bases. Executed exact routes expose the
event timestamp or date-filter basis and rejection counts. A bounded archived
scan still cannot prove absence unless its existing completeness and integrity
requirements pass.

No search schema transition or full reindex is required for this choice:
existing exact-literal posting metadata already carries the source timestamp.

## Rationale

The selected rule follows the evidence being queried instead of an incidental
archive partition. It restores exact recall without weakening session-oriented
filters, misrepresenting episode spans, or creating another persistent copy of
event time.

Making the basis visible prevents two routes from accepting the same date
arguments while silently answering different questions. Preserving the
session-date fallback keeps legacy or incomplete events navigable without
pretending that the fallback is an observed event timestamp.

## Consequences

- Exact events in multi-day sessions are retrievable by the day on which the
  event was recorded.
- General session/document and episode behavior retains its existing temporal
  meaning.
- Consumers must read the reported basis instead of assuming every
  `date_from` or `date_to` means session start.
- The change is additive and query-time only; existing exact indexes remain
  usable.
- Timestamp timezone interpretation remains the recorded ISO timestamp's
  responsibility; this decision does not introduce locale conversion.

## Boundaries

This decision defines date-filter coordinates for query routes. It does not
prove semantic relevance, current-state validity, supersession, causal
ordering, archive freshness, or complete negative recall. It does not change
raw evidence, session labels, shard partitioning, episode formation, or MCP
ownership. Session-specific gold, private coordinates, latency observations,
and experiment history remain in session provenance.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.AGENTS.md`

## Follow-Up Route

Continue independently seeded temporal, multi-day, missing-timestamp, wrong-day,
live-tail, and archived-fallback trials. Reopen the decision if a route cannot
state its temporal grain, if timezone handling becomes an owner requirement,
or if randomized cases show that session-date fallback creates an unsupported
claim.

## Verification

A gold-first archived-session trial reproduced the multi-day exact miss under
the old session-start filter. With the selected rule, the event-day query
returns the expected resolvable exact refs, an adjacent wrong-day query rejects
those candidates, and an incomplete bounded raw scan remains non-exhaustive.
An owner-neutral regression covers indexed exact postings, automatic archived
fallback, direct archived raw, and live-tail positive and negative dates. The
planner regression also proves that the temporal basis is visible before
execution.
