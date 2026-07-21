# Session-Scoped Archived Raw Exact Fallback

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0003
- Original date: 2026-07-15
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `README.md`
- Surface classes: query routing, exact retrieval, raw evidence, portable source
- Projection layers: exact literal postings, archived raw fallback
- Guard families: session scope, bounded scan, digest verification, filter-before-bound, query echo suppression, no persistent index
- Posture: accepted

## Context

Gold-first archived-session trials exposed an exact-recall gap in long
structured events. Compact literal postings intentionally retain only bounded
text, so a literal beyond that bound can be absent from the posting even when
the immutable raw event contains it. The broader FTS route can also exhaust a
bounded query budget before reaching the one requested session.

Increasing a preview or posting bound changes where the gap appears but does
not remove it. Treating the projected miss as exhaustive would therefore
confuse an index optimization with evidence absence.

## Options Considered

- Increase the compact posting text bound. This would enlarge a global
  projection, still leave a finite suffix boundary, and charge every indexed
  event for a session-scoped failure mode.
- Put complete tool output into the default FTS or another persistent exact
  index. This improves repeated broad scans but increases storage and rebuild
  pressure before that cost is justified.
- Keep raw inspection as an undocumented manual operator step. This preserves
  storage but leaves normal query routing unable to recover automatically or
  report whether absence was actually proven.
- Add a bounded, read-only, session-scoped archived raw exact fallback that
  computes the archive digest during the same streaming pass.

## Decision

Use a bounded archived raw scan as the final exact-recall authority route for
one resolved session.

Cheaper typed and compact exact routes remain first. When a supported
session-scoped exact query returns insufficient projected evidence or the
indexed FTS route times out, the search route may automatically scan that
session's archived raw JSONL. The scan writes no persistent index, preserves
raw, segment, and session refs, and reports its byte, line, and time budgets.
The query planner exposes the same route before a broader shard or monolith
raw-text fallback.

Only a complete scan whose digest matches the session manifest may prove that
the literal is absent. A budget-limited, changed, missing-digest, or
digest-mismatched scan remains truncated or unverifiable and cannot support an
exhaustive negative result. Retrieval commands and their correlated result
payloads are suppressed as query echoes rather than admitted as matching
evidence.

The automatic branch has an explicit disable flag for cheapest-route probes,
A/B comparison, and rollback. Global archived raw scans remain forbidden.

## Rationale

The chosen route spends work only when the caller has already provided the
strongest useful partition key: a session. It closes the bounded-projection
recall gap without copying complete raw output into another permanent store.
Computing the digest during the search pass makes the positive refs auditable
and makes negative claims conditional on the actual archived authority rather
than on a generated index.

Keeping typed/posting routes first preserves low-cost common queries. Keeping
the broader FTS route after the session scan preserves an expansion path for
cross-session or unsupported filters without pretending the session scan is a
global lexical engine.

## Consequences

- Session-scoped exact misses gain an automatic recovery route with resolvable
  evidence refs and no new persistent index.
- A complete negative answer costs one bounded sequential read and digest of
  the selected archive.
- Large archives may return a useful positive candidate before the bound, but
  an incomplete pass cannot claim exhaustive absence.
- The timeout packet remains visible when raw evidence recovers the query; the
  result records which route recovered it instead of silently presenting the
  index as healthy.
- Repeated exact queries over the same broad scope may still justify a
  materialized full-text shard; this decision does not remove that route.

## Boundaries

This decision governs exact literal retrieval from one archived session. It
does not define semantic relevance, review raw evidence into doctrine, replace
the append-only live-tail route, prove automatic projection freshness, change
MCP ownership, or authorize global transcript scans. Runtime budgets and
result schemas remain owned by the executable source. Session-specific gold,
latency observations, and experiment history remain in session provenance.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `README.md`

## Follow-Up Route

Keep the raw fallback behind typed/posting routes, export it through the normal
portable builder, and validate source and standalone behavior. Revisit the
choice if repeated-query evidence justifies a narrower persistent projection
or if randomized trials show unacceptable scan truncation, latency, or query
echo leakage.

## Verification

Two independently selected archived-session cases reproduced the same suffix
loss before implementation and recovered the expected raw and segment refs
afterward under the same bounded query budget. A separate negative query
proved absence only after a complete digest-verified pass. Owner-neutral
regressions reproduce a literal beyond the compact posting bound, index
timeout recovery, bounded-scan abstention, and retrieval-query echo
suppression. Exact values and private session coordinates remain in session
provenance.

## Review Amendment — 2026-07-20

An absent published search store is another form of insufficient projected
evidence; it is not a reason to skip the already accepted exact-recall route.
When the query and filters satisfy the same bounded session-scoped guards, the
ordinary search reader attempts the digest-verified archived raw fallback even
while no compatible store is published. It keeps the missing projection as
the visible first-route state, reports the recovery separately, writes no
index, and leaves global projection freshness unresolved.

This clarification does not expose an in-progress replacement to concurrent
readers and does not turn a raw candidate into an admitted claim. Unsupported
filters, unbounded scope, a disabled fallback, truncation, source drift, and
digest failure still abstain. The regression arose from a manual concurrent
reader/writer trial; private coordinates and timings remain in session
provenance rather than this owner record.

## Review Amendment — Filter Scope Before Candidate Bounds

A complete raw scan and a complete filtered result are different invariants.
Every event-local filter supported by the raw route — event ID bound, event
type, family, outcome, and duplicate event-stream exclusion — constrains raw
candidate collection before the candidate heap, ranking, and return limit.
Applying such a filter only to an already bounded top-k may hide a compatible
lower-ranked event and must never produce a complete-negative verdict.

Archive and freshness predicates remain explicit source-wide checks because
all candidates from one captured raw snapshot share those states. The packet
names requested filters, their pre-bound placement, rejection counts, and
result truncation. A complete digest-verified scan with no candidate in the
requested filter scope may prove only that scoped absence; it must not say the
literal was absent from the raw archive when out-of-scope occurrences were
observed.

This amendment was derived from a preregistered adversarial trial. The old
reader returned an empty typed top-1 result while also reporting a complete
verified scan, ignored a requested before-event bound, and returned an
explicitly excluded event-stream copy. The regression preserves those three
failures as negative controls and also exercises ordinary archived fallback
and live-tail filtering.
