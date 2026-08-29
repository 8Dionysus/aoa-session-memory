# Primary-Preserving Role-Diverse Dense Evidence Hydration

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0038
- Original date: 2026-07-29
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: semantic retrieval, evidence provenance, dense indexing, evaluation
- Projection layers: episode dense, episode semantic evidence packet, search generation metadata
- Guard families: raw-ref resolution, distinct evidence, bounded hydration, generation identity, answer abstention, exact noninterference
- Posture: accepted

## Context

Representation-level dense retrieval initially hydrated only the two
highest-cosine raw coordinates per episode. A return pass over the sealed
semantic evaluation showed two different phenomena that the original
first-relevant-episode metric had combined:

- some required evidence correctly crossed a fork boundary and therefore
  belonged to two provenance-distinct episodes already present in the result
  packet; and
- one returned local-work episode contained the required final finding as a
  current `failures` representation, but two higher-scoring `actions` or
  `outcomes` representations consumed the hydration limit.

Merging the fork-history and local-work episodes would have destroyed
lineage semantics. Hydrating the whole episode payload would have increased
semantic noise and context cost. Lowering the required-ref gate would have
hidden the evidence omission.

## Options Considered

- Keep score-only top-two hydration and treat episode identity as sufficient.
  Rejected because a returned episode without the independently required raw
  coordinate is navigation, not proof of relevance.
- Merge evidence across fork boundaries. Rejected because replayed parent
  history and local fork work are different provenance scopes.
- Increase the score-only limit. Rejected because adjacent same-role
  operational events can consume the larger limit without exposing a
  materially different intent, result, failure, or verification coordinate.
- Preserve the score-only top two and add a small number of highest-scoring
  matches from roles not already represented.

## Decision

Dense episode matching preserves the two highest-cosine distinct raw refs as
primary matches. It then traverses remaining representation matches in exact
descending cosine order and adds at most two refs whose semantic roles are
not already represented by an admitted match. Total dense representation
hydration is capped at four refs per episode.

Every returned match exposes whether it was admitted by
`primary_similarity` or `role_diversity`. Its original similarity rank is
preserved; a diversity supplement is not rewritten as a top-scoring match.

Episode scoring remains the maximum exact cosine over all current compatible
representation vectors. Role diversity changes only bounded evidence
selection, not episode identity, dense ranking, relation semantics, or claim
admission.

The dense generation identity declares the primary limit, diversity
supplement limit, total limit, and selection policy. Rows from an older
generation remain ineligible until catch-up completes.

## Rationale

The primary pair preserves the behavior already demonstrated by the dense
retriever. The two supplements add bounded semantic coverage for a different
kind of evidence without replacing the strongest matches or expanding the
whole episode.

Selecting supplements in the existing exact-cosine order keeps the result
deterministic and explainable. Requiring a new role makes the extra context
pay for a distinct episode function instead of another nearby action or tool
result.

## Consequences

- Positive: a returned episode can expose a relevant failure, verification,
  outcome, or intent even when same-role operational records score higher.
- Positive: fork and replay boundaries remain intact; packet-level evidence
  can span episodes without pretending they are one lifecycle.
- Positive: existing top-two matches are monotonic and never removed.
- Tradeoff: up to two additional raw-backed evidence cards may be passed to a
  bounded reranker or reader.
- Tradeoff: the changed evidence policy invalidates the dense generation and
  requires catch-up before query admission.
- Follow-up: keep packet-level required-ref completeness separate from the
  compatibility metric that scores only the first relevant episode.

## Boundaries

Role diversity does not assert that every semantic role is required for every
query. It does not admit a claim, infer causality, merge episode identities,
or make representation labels raw truth.

The policy does not change exact literal, lexical, graph, current-state, or
owner-runtime routes. Four matches are a hard evidence-hydration cap, not an
invitation to return an episode payload.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Reopen this decision if independent evaluation shows false-positive context
pressure, reranker regressions, unresolved raw refs, generation drift, or a
need for claim-shape-specific evidence selection. Any larger limit requires a
new preregistered cost and precision comparison.

## Verification

The selection contract is covered by focused tests for primary preservation,
distinct-role supplements, original rank visibility, bounded output, and raw
ref hydration. A raw-first sealed holdout checks multilingual semantic,
failure, review, and source-kind cases.

The original semantic gold is evaluated separately for first-episode
compatibility and packet-level union completeness. Exact structured
correlation queries must remain byte-equivalent after normalization and must
not invoke dense or graph expansion.
