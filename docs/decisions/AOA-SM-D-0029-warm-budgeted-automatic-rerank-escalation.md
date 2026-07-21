# Warm-Budgeted Automatic Rerank Escalation

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0029
- Original date: 2026-07-21
- Owner surfaces: `scripts/aoa_session_memory.py`, `DESIGN.AGENTS.md`, `PIPELINE.md`, `READINESS.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: query routing, hybrid retrieval, semantic retrieval, optional host acceleration, answer admission
- Projection layers: episode semantic, episode dense, local rerank navigation
- Guard families: evidence sufficiency, structural query shape, cold-start budget, provider readiness, claim abstention, privacy-safe health
- Posture: accepted

## Context

Episode retrieval can optionally send a bounded hybrid candidate set to a
local cross-encoder. The reranker is weaker than the evidence sources and can
only change navigation order, but loading it can cost much more than sparse,
dense, and fusion retrieval combined.

Weak lexical coverage is common for multilingual and conceptual paraphrases.
Treating that signal alone as a reason to rerank caused the automatic route to
invoke the optional provider broadly even when dense retrieval already
preserved the relevant candidate. A generation-pinned, gold-first ablation
found material latency cost without a changed candidate order or admission
outcome. The same evaluation separated cold model-load cost from warm
inference cost.

## Options Considered

- Automatically rerank every hybrid query with weak lexical coverage. Rejected
  because semantic and cross-lingual queries naturally have weak lexical
  overlap, and the reviewed ablation did not demonstrate corresponding
  reranker value.
- Keep or preload the host reranker so automatic queries never observe a cold
  start. Rejected because a portable archive organ must not create a hidden
  resident-host requirement or spend host resources before a query proves the
  need.
- Disable automatic reranking and retain only an explicit caller option.
  Rejected because bounded structural queries can still benefit from a warm
  second-stage ordering route, and the route can remain evidence-gated.
- Treat weak lexical coverage as an observation, require a structural query
  shape for automatic escalation, and admit the optional provider only when a
  bounded health check proves it already warm. Preserve explicit opt-in for a
  caller willing to accept cold-start cost.

## Decision

Automatic episode reranking uses a versioned escalation policy separate from
fusion and answer admission.

Weak lexical coverage is recorded in the evidence packet but is not an
automatic rerank trigger. Automatic escalation is considered only on the
`auto` hybrid route when candidates exist and a declared structural query
shape requests causal, recovery, or explicit-sequence ordering.

Before an automatic invocation, a bounded provider-health read must prove that
the optional reranker is already loaded. A missing, unavailable, unknown, or
cold provider returns a visible deferred escalation state and does not wake or
preload the model. The packet reports the policy version, trigger, structural
reasons, observed non-trigger signals, cold-start budget, provider readiness,
applied or deferred state, and reason. Health output is compact and excludes
host-private model or cache paths.

An explicit rerank request may bypass the automatic warmth gate. That is a
visible caller opt-in to bounded local cost, not a default, a freshness claim,
or proof that the reranker improves quality.

Reranker scores and promotions remain navigation only. They cannot admit a
causal, temporal, quantitative, negative, current-state, usage, verification,
or consequence claim. The normal claim-shape gate must still resolve and read
the required evidence refs.

## Rationale

The policy spends optional compute only when both query structure and current
provider state justify the next stage. This preserves a useful cross-encoder
route without converting model residency into a portable dependency or using
poor lexical overlap as a proxy for semantic ambiguity.

Separating the escalation policy from fusion keeps responsibilities
inspectable: fusion combines candidates, escalation controls optional cost,
and answer admission decides whether evidence supports a claim. A cold
deferral is honest budget exhaustion, while an explicit request remains a
deliberate escape hatch for investigation.

## Consequences

- Positive: ordinary semantic and multilingual hybrid queries avoid
  unproven reranker latency.
- Positive: an automatic query cannot silently cold-start an optional host
  model.
- Positive: structural warm reranking remains available and observable.
- Positive: provider health does not leak private host paths through the
  agent-facing packet.
- Tradeoff: a potentially useful cold reranker is skipped automatically until
  another route warms it or a caller explicitly opts in.
- Tradeoff: new automatic trigger families require their own gold-first value,
  latency, and admission review before entering the structural allowlist.

## Boundaries

This decision does not select a reranker model or backend, require a host
provider, prove reranker quality, or establish a universal latency SLO. It
does not make provider health, a reranker score, an embedding, or a fused rank
evidence authority.

The policy does not govern exact-identifier routes, projection generation,
maintenance scheduling, or external owner freshness. Portable sparse
retrieval and bounded raw verification remain available when optional
accelerators are absent.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `DESIGN.AGENTS.md`
- `PIPELINE.md`
- `READINESS.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Keep a sealed sparse, dense, hybrid, explicit-rerank, and production-auto
ablation in the release proof. Reopen this decision if a preregistered corpus
demonstrates repeatable value from weak-lexical automatic reranking, if a
structural trigger causes unsupported admission, or if the warmth check wakes
or leaks details from an optional provider.

## Verification

Focused contracts cover weak lexical non-escalation, cold structural
deferral, warm structural application, explicit opt-in, provider-health
failure, and privacy-safe health fields. Release proof additionally requires
a generation-pinned real-session A/B, cold and warm runtime gates, manual raw
ref and forbidden-claim review, the full source suite, and source, portable,
skill, CLI, and MCP packet parity.
