# Evidence-Backed Representation Vectors for Dense Episode Retrieval

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0037
- Original date: 2026-07-29
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: semantic retrieval, dense indexing, evidence provenance, freshness, reproducibility
- Projection layers: episode dense, episode semantic evidence packet, search generation metadata
- Guard families: raw-ref resolution, distinct evidence, generation identity, atomic rebuild, answer abstention, exact noninterference
- Posture: accepted

## Context

The episode dense projection originally embedded one bounded aggregate passage
per task episode. That preserved a compact exact-cosine route, but a sealed
multilingual retrieval evaluation exposed semantic dilution: the correct
episode could rank while the result packet lacked the particular
representation-level raw coordinate that made it relevant. The evaluator
correctly treated episode identity without an independently selected required
raw ref as a miss.

The failure could not be repaired by admitting the nearest episode as an
answer. Dense similarity is navigation, and raw session evidence remains the
authority. The projection also needed to remain incrementally rebuildable,
generation-aware, deterministic, and compatible with episodes that do not
have an admissible evidence-bearing representation.

## Options Considered

- Keep one aggregate vector per episode and lower the required-ref evaluation
  gate. Rejected because it would turn identity similarity into unsupported
  evidence and hide the observed provenance defect.
- Embed the whole episode or session in a larger passage. Rejected because a
  larger monolith increases semantic interference and still cannot attribute
  the match to one resolvable representation.
- Treat every representation vector as an independent result or claim.
  Rejected because that would fragment episode identity and let a generated
  embedding become evidence authority.
- Add a versioned representation-vector sidecar, aggregate its scores by
  episode, hydrate only distinct matching raw refs, and keep the old episode
  vector as an explicit fallback when no current representation vector exists.

## Decision

Dense episode indexing stores two generated surfaces:

- the existing bounded aggregate episode vector; and
- a versioned sidecar of bounded representation vectors for intents, plans,
  actions, outcomes, verification, and failures that already carry a raw ref.

Each representation row binds a stable identity, episode and session identity,
semantic role, raw and derived refs, source lane, admission basis, outcome,
document digest, model, dimension, and dense generation identity. Per-role
tail and text limits bound cardinality and embedding cost.

Query-time scoring takes the maximum exact cosine over current representation
vectors for each episode. It returns at most the declared number of distinct
matching raw refs and resolves them back through the current episode payload
before adding them to supporting evidence. Duplicate representation
identities that point to one raw coordinate do not duplicate the evidence
packet.

The aggregate episode vector participates only when that episode has no
current compatible representation vector. Old, unknown, model-incompatible,
or generation-incompatible rows are ineligible.

Representation similarity remains navigation. It never changes claim
admission, proves a relation, or replaces bounded source reading. Exact
identifier routes continue to bypass dense and graph expansion.

Dense generation metadata is published only after the complete selected owner
scope reports current coverage with no dirty session. A successful worker,
current row subset, or process exit is insufficient. Failure before metadata
publication leaves the projection conservatively stale; per-session state and
source refs remain the coverage proof.

## Rationale

Multiple bounded views preserve the semantic distinctions already present in
an episode instead of forcing one vector to represent every intent, action,
failure, and result at once. Aggregating by stable episode identity keeps the
episode as the retrieval unit, while resolving the winning representations to
raw refs gives the reader an attributable next route.

Requiring a raw ref before a representation is embedded prevents generated
summary text from acquiring stronger provenance through the dense sidecar.
Distinct-ref hydration removes duplicate evidence without discarding useful
representation identities from explain diagnostics.

Keeping the aggregate vector as an explicit fallback preserves bounded
backward behavior for evidence-poor episodes and provides an ablation surface.
Generation-gated publication makes a completed rebuild visible without
claiming freshness for partial coverage.

## Consequences

- Positive: conceptual and cross-lingual episode retrieval can recover the
  specific raw coordinates that justify relevance.
- Positive: episode identity, evidence authority, and answer admission remain
  separate contracts.
- Positive: rebuild, deletion, rollback, and exact-cosine behavior remain
  deterministic and inspectable.
- Tradeoff: vector cardinality and embedding work increase by the number of
  admitted bounded representations.
- Tradeoff: episodes without evidence-bearing representations use the weaker
  aggregate fallback and cannot expose representation matches.
- Tradeoff: a dense policy or representation change invalidates the dense
  generation and requires catch-up before the new rows are eligible.
- Follow-up: measure global latency and storage pressure before considering an
  approximate vector backend or changing the bounded representation policy.

## Boundaries

This decision does not make embeddings, episode projections, generated
summaries, or representation metadata raw truth. It does not prove broad
multilingual quality beyond reviewed corpora, current repository or runtime
state, causality, completion, absence, usage consequence, or relation
correctness.

It does not require graph expansion and does not change exact literal,
lexical, or claim-admission semantics. Backend replacement remains a separate
decision and must preserve stable IDs, refs, generation checks, deterministic
fallback, and provider-neutral portable behavior.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Run the full source suite, deterministic and partial-failure regressions,
generation-pinned per-lane evaluation, manual raw-ref review, portable export
and standalone validation. Reopen the representation policy if measured
storage, latency, false-positive pressure, or an exact, provenance, freshness,
privacy, or abstention regression exceeds the accepted bounds.

## Verification

A preregistered multilingual evaluation selected required raw refs before
retrieval and compared sparse, dense, hybrid, and reranked-hybrid lanes under
one stable generation pin. Manual review opened the required raw coordinates
and rejected forbidden current-state, completion, causal, and quantitative
claims. A separate exact-postings comparison used raw-selected structured
correlation IDs and required unchanged exact recall without dense or graph
expansion.

Focused owner tests cover bounded stable representation construction,
raw-ref admission, distinct-ref hydration, current-generation eligibility,
aggregate fallback, atomic per-session replacement, deletion, deterministic
double rebuild, generation publication after complete coverage, and rollback
after a failed store.
