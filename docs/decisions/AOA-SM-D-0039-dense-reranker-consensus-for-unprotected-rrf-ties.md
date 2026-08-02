# Dense-Reranker Consensus for Unprotected RRF Ties

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0039
- Original date: 2026-07-29
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: hybrid retrieval, reranking, evidence provenance, answer admission
- Projection layers: episode hybrid retrieval, local reranker evidence packet
- Guard families: reciprocal-rank fusion, typed anchors, dense-reranker consensus, bounded promotion, answer abstention, exact noninterference
- Posture: accepted

## Context

Reciprocal-rank fusion can produce an exact tie between a sparse rank-one
episode and a dense rank-one episode. The deterministic fallback previously
kept the sparse-first order. A local reranker could strongly prefer the dense
winner yet remain below the global model-only promotion score, so the
ambiguous policy preserved the tie order even when two independent
navigation signals agreed.

This appeared in a provenance-sensitive forked session: sparse retrieval
ranked replayed pre-child history first, dense retrieval ranked local fork
work first, no typed sparse anchor existed, and the reranker independently
preferred the local-work episode by a wide margin. Lowering the global
reranker score threshold would have broadened model-only authority beyond the
observed pressure.

## Options Considered

- Lower the global reranker promotion score. Rejected because a model-only
  threshold change would affect non-tied and weakly grounded candidates.
- Always prefer dense rank one on an RRF tie. Rejected because it would ignore
  a reranker disagreement and could displace useful sparse evidence.
- Always preserve sparse-first tie order. Rejected because it discards
  independent dense and reranker agreement when no typed sparse anchor is
  present.
- Admit a narrow consensus tie-break while retaining the existing model-only
  score and margin thresholds.

## Decision

The rerank promotion policy adds one bounded consensus route. A non-leading
reranker winner may be promoted below the model-only score threshold only
when all of the following hold:

- the winner is dense rank one;
- its fusion score and the current leader's fusion score are equal within
  `1e-12`;
- the reranker margin meets the existing `0.10` margin floor; and
- the current leader is not protected by a typed or ordered sparse anchor.

The global model-only promotion floor remains `0.80`, and the decisive
model-only path is unchanged. Typed sparse-anchor protection continues to
block a model-only promotion. Non-tied ambiguous candidates preserve fusion
order.

The evidence packet exposes the promotion policy version, whether consensus
was active, the winner identity and dense rank, fusion-tie state, admitted
margin state, and typed-anchor protection state.

## Rationale

An exact RRF tie states that sparse and dense rank evidence are mechanically
balanced. Dense rank one plus an independently computed reranker winner gives
two signals for one side of that tie. Using agreement only to break the tie
is narrower than lowering a global score threshold or changing general RRF
weights.

The typed-anchor guard remains stronger because a structured exact or ordered
source anchor has a different evidence basis from two semantic navigation
signals. Claim admission remains downstream and evidence-gated regardless of
candidate order.

## Consequences

- Positive: a semantic local-work episode can outrank replayed history when
  dense and reranker signals agree on an otherwise exact unprotected tie.
- Positive: the model-only confidence floor and typed-anchor protection do
  not weaken.
- Positive: promotion remains deterministic, bounded, and explainable.
- Tradeoff: the policy depends on both optional local model signals and
  therefore applies only when the reranker route is available and selected.
- Tradeoff: candidate order can change without changing answer admission.

## Boundaries

Consensus is navigation, not truth. It does not prove that a candidate
contains a correct answer, resolve a stale projection, establish a relation,
or authorize a current-state, causal, negative, temporal, quantitative, or
usage claim.

The policy does not apply to non-tied fusion scores, does not override a typed
sparse anchor, and does not alter exact, lexical, dense, graph, or portable
fallback semantics.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Reopen this decision if a larger gold corpus shows tie-break regressions,
model calibration drift, excessive provider cost, or disagreement with
lineage and source-kind evidence. Changing the score or margin floors remains
a separate preregistered decision.

## Verification

Focused tests cover decisive promotion, ambiguous preservation, typed-anchor
blocking, and dense-reranker consensus on an exact fusion tie. Generation-
pinned semantic evaluation must keep reranked hybrid Recall, MRR, and nDCG at
least as strong as the dense lane without unsupported top admission.

A separate raw-first holdout must remain non-regressed, and exact structured
correlation routes must remain byte-equivalent without dense, reranker, or
graph expansion.
