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
window, plus explicit UTC window boundaries, optional public-safe expected
facet IDs, and bounded confidence. A hook-bound action also carries the actual
PreToolUse tool_use_id; action and observation events must repeat the same
attempt and tool identity. The action binding carries the prediction sequence
and requires a strictly later timestamp than the commitment; the append
sequence remains the authoritative causal fence.
The append path uses a file lock, no-follow regular-file opens, an optimistic
observed-head check, a predecessor digest, and an event digest. An identical
logical append is a storage-layer replay-safe no-op; the skill ABI maps that
to its exact-replay `refused`/no-new-record case. A different record with the
same logical identity is rejected as ambiguous. A stale writer is refused as
a concurrency conflict, while two active records that claim one logical
action are ambiguous.

The same-action fence rejects a losing cross-instance prediction or observation
attempt before it can append a record. The owner ABI does not retain that losing
attempt as a durable refusal or ambiguity event: the losing caller receives
`duplicate_logical_identity` with `ambiguous` state, while a later reload of the
winner-only chain can remain `ready`. This is a fail-closed storage disposition,
not a causal winner/loser verdict or evidence that both attempts occurred.

Replay also recomputes the prediction commitment, predecessor-derived
discrepancy, and shadow-candidate fields. Logical identities are unique across
the chain, so recomputing the outer hash chain cannot make duplicate or
cross-field-inconsistent records admissible. Observed evidence must carry a
public-safe evidence ref and an observation timestamp inside the committed
window. An exact expected/observed digest equality derives `match`; a
different digest derives `mismatch` unless committed and observed facet IDs
show a non-empty proper overlap, which derives `partial_match`. Opaque
digests alone cannot establish `partial_match`, and a caller-supplied
conflicting value is recorded as `ambiguous` and refused.

Missing or interrupted observations are recorded as `unknown`. Conflicting
observations and immutable-identity conflicts are recorded or returned as
`ambiguous`. Invalid ordering and privacy input is `refused` without storing
the unsafe value. Required persisted timestamps are non-null, bounded UTC
strings; replay reports `timestamp_invalid` for missing, null, non-string, or
malformed values before comparing event times. A creation call may omit its
local event timestamp, but an explicit null never falls back to the current
time. A model-update candidate is always `shadow_only`; its
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
