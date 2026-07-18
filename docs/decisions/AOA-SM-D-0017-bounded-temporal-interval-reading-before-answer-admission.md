# Bounded Temporal Interval Reading Before Answer Admission

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0017
- Original date: 2026-07-18
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `DESIGN.AGENTS.md`, `docs/decisions/`
- Surface classes: query routing, temporal retrieval, evidence reading, answer admission
- Projection layers: semantic episode, query-time raw hydration, temporal interval
- Guard families: typed anchors, bounded interval read, source-aware event retention, time scope, truncation, privacy, abstention
- Posture: accepted

## Context

A temporal relationship question and an interval-contents question have
different evidence shapes. An ordered pair of anchors can prove that one
observed event preceded another, but it does not show what happened between
them. Treating the endpoint pair as the answer can omit the very actions,
results, status changes, and closeout that the query asks for.

Episode representations are intentionally compact and do not retain every
interior event from a long task. Strong lexical, dense, or fusion scores can
therefore find the correct episode and endpoints without carrying sufficient
answer evidence. Archived candidate blocks also require an explicit
hash-verification boundary; they must not be labelled as if they were a direct
read of the live transcript.

## Options Considered

- Admit the best ordered endpoint pair and expect the consumer to infer or
  separately discover the interior. Rejected because endpoint evidence cannot
  support an interval-contents claim.
- Return endpoints only and always require the consumer to open raw evidence
  manually. This is safe navigation, but it leaves a common bounded query lane
  unable to answer even when the necessary evidence is already available.
- Persist a full event-level interval projection or add more vectors and graph
  edges for every raw event. Rejected because it duplicates raw evidence and
  adds cardinality, storage, and freshness dependencies before repeated demand
  proves them necessary.
- After typed endpoint discovery, perform one bounded source-aware read of the
  selected direct transcript or hash-verified archived blocks and admit only
  complete, auditable interior evidence.

## Decision

Distinguish `interval_contents` from `ordered_relation` at query time.

For an interval-contents query, typed ordered endpoints remain navigation until
the bounded reader inspects the events strictly between them. The reader may
retain chronological canonical user or assistant messages, structured tool
actions and results, and structured operational status events. It excludes
hidden reasoning, token accounting, runtime message mirrors, and private
collaboration-message bodies.

Answer admission requires:

- one unambiguous competitive endpoint span;
- a successful direct raw read or hash-verified archived-block read;
- at least one readable interior event;
- raw refs for every admitted interior event and both endpoints;
- compatible requested time scope;
- no source, retention, or output truncation; and
- an explicit privacy policy showing that private message bodies were not
  read.

Lower-quality alternative spans may remain visible as bounded diagnostics, but
they do not make a unique competitive span ambiguous. If any admission guard
fails, the route exposes the endpoint refs and interval status as navigation
and abstains. Lexical, dense, fusion, reranking, or endpoint strength cannot
bypass the interval gate.

Packets label direct transcript evidence and hash-verified archived-block
evidence separately. Both preserve raw, segment, and session handoff refs; the
raw transcript remains the underlying evidence authority.

## Rationale

The selected route makes the evidence shape match the question while keeping
the escalation bounded. It recovers operational detail that compact episodes
can omit without creating another persistent event index or graph layer.

Source-aware retention prevents internal bookkeeping, duplicated runtime
messages, or private collaboration content from being promoted into answer
evidence. Truncation and time-scope gates prevent a partial read from being
presented as a complete interval. Distinct provenance labels keep an archived
copy auditable without overstating how it was read.

## Consequences

- Interval queries can answer from a compact chronological event list with
  resolvable evidence refs.
- A route that finds the correct endpoints can still abstain when the interior
  is empty, truncated, ambiguous, outside the requested time scope, or not
  integrity-verified.
- This lane pays bounded raw-reading latency only after typed endpoint
  discovery; ordinary episode and ordered-relation queries do not inherit that
  cost.
- New retained event classes require manual evidence and a return review of
  privacy, duplication, truncation, and claim semantics.

## Boundaries

This decision governs interval-content evidence reading and answer admission.
It does not make session evidence reviewed repository truth, prove causality
from chronology, define current-state or supersession semantics, authorize
unbounded transcript reads, or replace raw evidence with episodes. It does not
make hidden reasoning or private message bodies searchable interval content.
Session-specific spans, seeds, queries, coordinates, outputs, and performance
observations remain in session provenance.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.AGENTS.md`

## Follow-Up Route

Continue independently seeded direct-transcript and archived-block trials,
including wrong endpoint, wrong date, mention-only terminal text, duplicate
observations, multiple competitive spans, empty interior, output truncation,
source-integrity failure, cross-episode intervals, and multilingual phrasing.
Reopen the decision if a supported event class is consistently omitted or if
the bounded query-time read no longer meets latency and storage tradeoffs.

## Verification

Gold-first archived-session trials exposed both an endpoint-only answer and an
incorrect archived-source authority label. The corrected route returned the
manually adjudicated interior chain with raw, segment, and session refs while
excluding private and internal-only content. Adjacent wrong-target,
wrong-date, mention-only, and forced-truncation cases abstained. Owner-neutral
regressions were first shown to fail on the broken behavior and then pass after
the correction; complete source and standalone suites remain supporting
mechanical checks rather than semantic proof.
