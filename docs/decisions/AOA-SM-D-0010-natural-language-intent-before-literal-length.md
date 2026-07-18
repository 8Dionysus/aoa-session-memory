# Natural-Language Intent Before Literal Length

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0010
- Original date: 2026-07-16
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `DESIGN.AGENTS.md`
- Surface classes: query routing, exact retrieval, semantic retrieval, access contract
- Projection layers: query-intent plan, exact literal, semantic episode, agent event
- Guard families: natural-language intent, explicit literal evidence, agent-event specificity, bounded fallback
- Posture: accepted

## Context

The memory query router must distinguish a literal fragment from a natural-
language request even when both contain only a few words. A length-only rule
classified every unstructured phrase of up to eight whitespace-separated
terms as exact literal input. Short paraphrases and evidence questions could
therefore bypass the episode route and enter literal postings.

The same failure became more specific when a word about completion appeared
inside the question. A broad substring heuristic inferred an assistant final
closeout even when the subject was session state or the result of a search.
The resulting agent-event filter was precise syntactically but unrelated to
the requested evidence.

## Options Considered

- Keep short phrases literal by default. This preserves a cheap route but
  mistakes sentence length for intent and can add an unrelated agent-event
  filter.
- Send every unstructured phrase to semantic episodes. This avoids the false
  literal lane but weakens convenient short literal fragments and explicit
  response-class queries.
- Preserve structured and explicit literal evidence while treating ordinary
  natural-language questions and longer paraphrases as semantic lookups.
  Infer a final closeout only from an explicit closeout marker or from final-
  state language combined with response context.

## Decision

The top-level memory query router chooses exact intent from evidence stronger
than phrase length alone.

Paths, commands, identifiers, raw refs, session identities, hook receipts, and
other structured exact shapes remain exact. An unstructured exact-phrase shape
is exact at the top-level router when it is quoted, carries explicit literal
language, names an explicit agent-event response class, or is a compact non-
question fragment. Longer paraphrases and natural-language question/request
forms enter the semantic episode lane first and retain the bounded raw-text
fallback.

The dedicated literal planner remains available when the caller has already
selected exact intent. Its existence does not authorize the top-level router
to reinterpret an ordinary semantic question as literal.

Final-closeout inference requires an explicit closeout marker or final-state
language together with answer, response, message, or assistant context. A
completion word about sessions, commands, or search results does not by itself
select the assistant final-closeout lane.

## Rationale

Structured anchors and explicit wording are stronger evidence of literal
intent than a small token count. The selected rule keeps cheap exact routes
for their intended lane while preventing an unrelated closeout facet from
silently narrowing semantic evidence recall.

Keeping the direct literal planner separate preserves an explicit escape
route and makes the heuristic reviewable. Keeping episode and raw fallback
routes visible preserves recall and abstention when semantic projections are
stale or insufficient.

## Consequences

- Short natural-language paraphrases and evidence questions no longer become
  exact merely because they fall below a token threshold.
- Explicit closeout queries still use the typed assistant-final route.
- Some ambiguous bare phrases require either explicit literal wording or the
  dedicated literal planner to force exact-first behavior.
- The multilingual prefix and compact-fragment heuristics remain bounded
  routing aids and must be reopened when randomized language cases expose a
  medium or high misclassification.

## Boundaries

This decision governs route selection, not semantic answer correctness. It
does not make an episode candidate true, upgrade a stale projection, define
the embedding model, prove cross-language recall, or authorize a claim without
raw, segment, and session refs. Session-specific queries, coordinates, seeds,
and measured outputs remain in session provenance.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.AGENTS.md`

## Follow-Up Route

Continue independently seeded exact, semantic, multilingual, negative, and
agent-event collision trials. Reopen this decision if they show that the
compact-fragment boundary loses exact recall or that natural-language forms
still acquire unrelated typed filters. Export through the normal portable
builder and verify source, standalone, and configured access-plane parity.

## Verification

Gold-first manual trials reproduced both the short-paraphrase literal
misroute and the unrelated final-closeout filter before the change. The same
queries select semantic episodes afterward, while an explicit final-answer
query retains the closeout route. An owner-neutral regression fails on the
old behavior and passes with the selected rule; the full source test suite and
portable parity remain supporting mechanical checks rather than semantic
proof.
