# Evidence-Specific Sparse Anchors in Hybrid Fusion

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0027
- Original date: 2026-07-20
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `READINESS.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: query routing, hybrid retrieval, semantic retrieval, evidence admission
- Projection layers: episode semantic, episode dense
- Guard families: typed relation evidence, raw-ref coordinates, decisive sparse margin, reciprocal-rank fusion, claim abstention
- Posture: accepted

## Context

Reciprocal-rank fusion combines sparse and dense candidate orders without
assuming that their raw scores are comparable. That property is useful for
ordinary semantic retrieval, but a generation-pinned real-session ablation
showed that rank-only fusion demoted sparse rank-one winners whose scores
contained specific typed relations backed by raw coordinates. Sparse was the
strongest baseline for the reviewed replay, fork-local-work, delegated
lifecycle, and failure/resume questions; weak candidates appearing moderately
high in both lists still outranked episodes exposing the requested structural
evidence.

The existing sparse anchor protected highly coherent lexical winners. Short
relational questions can be specific while matching few lexical terms, so
lowering the general coherence thresholds would also anchor semantic noise.

## Options Considered

- Use unmodified reciprocal-rank fusion for every hybrid query. Rejected
  because two weak rank votes can wash out one evidence-specific typed route.
- Increase the weight of every sparse rank. Rejected because it would suppress
  dense value globally and turn hybrid retrieval into a disguised lexical
  route.
- Mix raw lexical, relation, and dense scores directly. Rejected because those
  scores have different scales and generation semantics.
- Give the rank-one sparse candidate one bounded fusion bonus only after a
  narrow typed-relation and line-addressable-ref guard proves a decisive
  winner.

## Decision

Hybrid episode retrieval keeps ordinary reciprocal-rank fusion and advances
its query-time fusion policy version.

The sparse rank-one candidate receives one additional rank-one reciprocal
vote only when all of these conditions hold:

- the candidate has an exact typed replay relation, an exact fork-boundary
  side, a structurally complete delegated-lifecycle candidate, or an ordered
  observed failure and later resume sequence;
- the relation's required raw coordinates are present, line-addressable, and
  structurally ordered where the relation requires an order;
- the evidence-aware sparse score exceeds the runner-up by the declared
  decisive typed margin; and
- the guard reports its relation signals, refs, margin, and policy in the
  explain packet.

For failure/resume, the refs establish only the observed temporal sequence;
they do not prove causality or a successful recovery consequence. Source-kind
alignment by itself is not an anchor. Ordinary mention, cooccurrence,
adjacency, lexical overlap, embedding similarity, and a generic fork scope are
not anchors. Full ordered temporal spans retain their separate typed temporal
anchor policy.

The bonus protects navigation order only. It does not admit replay, lineage,
delegation, causality, ownership, current state, or any other claim. Those
claims still require their bounded source read and answer-admission gate.

## Rationale

This route preserves dense participation for ambiguous or genuinely semantic
queries while preventing an evidence-bearing structural route from being
washed out by two weaker ranks. Requiring both a narrow relation family and
line-addressable raw coordinates ties the exception to provenance rather than
to a magic keyword or an uncalibrated score. The later claim gate, not fusion,
proves that those coordinates resolve and support an answer.

Keeping the exception as one visible reciprocal vote is deterministic and
bounded. It is easier to ablate than a hidden global weight and leaves the
ordinary fusion order unchanged when the evidence guard does not qualify.

## Consequences

- Positive: exact typed replay, fork-boundary, delegated-lifecycle, and
  ordered failure/resume navigation survives weak dense consensus without
  disabling dense retrieval.
- Positive: packets explain why an anchor applied and which raw coordinates
  supported it.
- Positive: missing refs, generic lineage, and small score margins retain
  ordinary fusion behavior.
- Tradeoff: newly supported typed relation families require an explicit guard
  and evaluation before they can receive the same protection.
- Tradeoff: an anchored result remains navigation-only until source reading
  satisfies the relevant claim gate.

## Boundaries

This decision does not make the sparse score, relation projection, dense
sidecar, or fused rank evidence authority. It does not promise that hybrid
retrieval beats every single-lane route on every query. Exact identifiers may
still bypass semantic and graph expansion entirely.

The policy does not lower gold thresholds or permit a source-aware ablation to
compare different ranking functions. A/B evaluation must hold candidate
scope, budgets, generation, and ranking method constant for the factor it
claims to isolate.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `READINESS.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Run the preregistered sparse, dense, hybrid, and reranked-hybrid lanes under
one compatible generation pin. Inspect the affected raw refs manually, then
repeat a semantic-only paraphrase lane where dense retrieval can add recall.
Reopen this decision if the anchor harms exact recall, abstention, provenance,
privacy, or an independently sealed semantic lane.

## Verification

Focused contracts cover a valid exact replay relation, a valid exact local
fork boundary, a structural delegated lifecycle, an ordered failure/resume
sequence, missing or reversed refs, a generic non-boundary lineage signal, an
insufficient score margin, coherent lexical anchoring, and ordered temporal
anchoring. Release proof additionally requires real generation-pinned per-lane
A/B, source-aware ablation with like-for-like ordering, manual raw-ref review,
full source tests, and portable plus access-plane parity.
