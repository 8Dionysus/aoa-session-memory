# Epistemic Action event chain

`aoa-session-memory` owns a small source-local event chain for preserving the
relationship between a prediction, an action, an observation, a derived
discrepancy, and a possible model-update candidate. It is an evidence source,
not a model updater or a benefit/evaluation verdict.

## Contract

The implementation is [`scripts/aoa_epistemic_action_event_chain.py`](../scripts/aoa_epistemic_action_event_chain.py), and its machine contract is
[`schemas/epistemic-action-event-chain.schema.json`](../schemas/epistemic-action-event-chain.schema.json).

Each persisted JSONL record contains only bounded identifiers, SHA-256
digests, typed state, timestamps, and event references. Callers can derive a
public identifier with `epistemic_public_id` and a digest with
`epistemic_digest`; neither helper serializes the source value.

The admissible order is:

```text
prediction_commitment -> action_binding -> observation -> discrepancy -> model_update_candidate
```

The prediction commitment is immutable and must exist before action binding.
It carries a request/attempt identity, a pre-action marker, opaque digests for
the hypothesis, expected change, falsifier, bounded plan, and observation
window, plus bounded confidence. A hook-bound action also carries the actual
PreToolUse tool_use_id; action and observation events must repeat the same
attempt and tool identity.
The append path uses a file lock, an optimistic observed-head check, a
predecessor digest, and an event digest. An identical logical append is a
replay-safe no-op. A different record with the same logical identity is
rejected.

Replay also recomputes the prediction commitment, predecessor-derived
discrepancy, and shadow-candidate fields. Logical identities are unique across
the chain, so recomputing the outer hash chain cannot make duplicate or
cross-field-inconsistent records admissible. For an observed result, an exact
expected/observed digest equality derives `match`; a different digest derives
`mismatch`. `partial_match` remains a schema value for compatibility, but an
opaque digest cannot establish it and a caller-supplied conflicting value is
recorded as `ambiguous` and refused.

Missing or interrupted observations are recorded as `unknown`. Conflicting
observations and immutable-identity conflicts are recorded or returned as
`ambiguous`. Invalid ordering and privacy input is `refused` without storing
the unsafe value. A model-update candidate is always `shadow_only`; its
alternative explanation, proposed update, and next distinguishing action are
opaque digests, and it never changes a model or claims semantic benefit.

## Claim boundary

The inspect/replay projection proves only source/storage integrity for the
bounded ledger and the candidate shape derived from it. Hook execution,
transport admission, owner acceptance, live currentness, model fit, semantic
benefit, and promotion remain downstream owner decisions.

Focused adversarial coverage lives in
[`tests/test_session_memory.py`](../tests/test_session_memory.py), alongside
the owner validation lane.
