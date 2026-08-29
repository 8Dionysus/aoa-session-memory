---
name: aoa-session-experience-metabolism
description: Derive privacy-safe recurring motifs and bounded improvement candidates from closed, reviewed stage profiles, with explicit review, eval, shadow, owner-acceptance, adoption, and rollback gates.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-experience-metabolism

Use this skill only for a bounded set of `stage_profile_v1` reports whose
sessions have closed task episodes and an explicit reviewed status. The
producer reads generated profile data; it does not read raw transcripts or
capture ledgers.

## Trigger boundary

Use this when a reviewed session set needs recurring-motif candidates,
counterevidence, or a shadow/evaluation handoff. Do not use it for live or
provisional sessions, raw transcript summarization, direct skill mutation, or
an evaluation verdict.

## Procedure

```bash
python3 scripts/experience_metabolism.py \
  --profile <stage-profile-report.json> \
  --profile <second-stage-profile-report.json> \
  --minimum-sessions 2 \
  --minimum-occurrences 3 \
  --output <experience-metabolism-report.json>
```

The output is advisory. Same-session repetition is marked `watch`, not
recurrence. Unknown or conflicting outcomes are retained as counterevidence
and cannot become an accepted candidate. Operation shapes and digests are
content-free; provenance uses bounded privacy-hashed logical references.

## Lifecycle and handoffs

Every packet remains in `candidate` state until an explicit, receipted event
advances it. The required order is:

1. independent reviewer disposition;
2. `aoa-evals` verdict with paired, held-out, and ablation comparisons;
3. `abyss-stack` shadow result with a baseline, net-benefit vector, and
   trajectory-cost measurements and a typed, immutable shadow measurement
   binding;
4. named owner acceptance and a live canary reference, producing `accepted`
   but not `adopted` state;
5. a separate named adoption event and receipt from `aoa-session-memory`.

Lifecycle receipts are structured owner evidence, not arbitrary URI strings.
Each event must carry `owner_repo`, `receipt_type`, the exact `candidate_id`,
the immutable candidate `base_digest`, `object_ref`, an external
`verification_ref`, a full `sha256:` digest over those canonical fields, and
`integrity: verified`. `object_ref` and `verification_ref` are
privacy-hashed logical-reference objects, never arbitrary URI strings; the
verification ref marks the mandatory owner/external-verifier boundary and is
not inferred by this skill. The reducer stores a canonical receipt and a
chained transition digest, so a packet cannot resume
from a forged `owner_review_pending` state or mutable gate fields. An accepted
eval event must also carry identity-bound comparison packets for `paired`,
`held_out`, and `ablation`: every packet binds the candidate id, the complete
source-binding digest list, one comparison subject, baseline, shadow, context,
numeric result, source and evidence digests, plus its result ref;
an accepted shadow event must carry a digest-bound typed measurement whose
baseline and shadow include coverage status and trajectory metrics, whose
candidate cohort and comparison cohort bindings are separate, whose
net-benefit claim remains `not_established`, and whose refs are retained in
the lifecycle record. Receipts also bind the event kind, disposition, and
canonical evidence digest; reusing a receipt for another disposition fails
closed. Owner acceptance requires an identity-bound canary packet with a
runtime, execution, treatment, baseline, shadow, rollback, and external
verification reference; that packet is an owner/verifier boundary, not a
claim that this reducer independently inspected the runtime. Owner acceptance
and adoption are separate events; neither may be inferred from frequency,
comparison deltas, or a green check.

Apply one event to one packet only when the receiving owner has produced the
receipt:

```bash
python3 scripts/experience_metabolism.py \
  --profile <one-candidate-packet.json> \
  --packet <one-candidate-packet.json> \
  --event <receipted-lifecycle-event.json> \
  --output <advanced-packet.json>
```

The reducer is pure and reversible. It never installs a skill, changes a
hook, schedules a route, or adopts a candidate. Rejection, supersession, and
rollback preserve the prior packet and require explicit references.

For a shadow-only comparison, typed packets bind baseline and shadow profile
identities plus their source-binding digest union; both profiles must be
complete bounded snapshots:

```bash
python3 scripts/experience_metabolism.py \
  --profile <any-profile.json> \
  --baseline-profile <baseline-stage-profile.json> \
  --shadow-profile <shadow-stage-profile.json> \
  --comparison-mode paired \
  --comparison-packet <paired-comparison-packet.json> \
  --output <shadow-measurement.json>
```

The measurement reports wall-clock trajectory, residual unknown time, and
repeat/rerun rates as separate bounded components. It does not collapse them
into a universal score or call a directional delta a benefit.

For a lifecycle event, use a JSON object shaped like this (with a real
owner-issued digest and reference):

```json
{
  "kind": "review_verdict",
  "status": "accepted",
  "independent_reviewer": true,
  "receipt": {
    "owner_repo": "reviewer-office",
    "receipt_type": "review-verdict-v1",
    "candidate_id": "experience-candidate:<24 lowercase hex characters>",
    "base_digest": "sha256:<64 lowercase hex characters>",
    "object_ref": {
      "scheme": "privacy-hashed-logical-ref-v1",
      "event": "event:sha256:<16 lowercase hex characters>"
    },
    "verification_ref": {
      "scheme": "privacy-hashed-logical-ref-v1",
      "event": "event:sha256:<16 lowercase hex characters>"
    },
    "event_kind": "review_verdict",
    "event_status": "accepted",
    "evidence_digest": "sha256:<64 lowercase hex characters>",
    "digest": "sha256:<64 lowercase hex characters>",
    "integrity": "verified"
  }
}
```

## Verification

- Validate `schemas/experience-metabolism-report.schema.json` and run the
  focused `tests/test_experience_metabolism.py` suite.
- Keep candidate, eval verdict, shadow result, owner acceptance, and adoption
  as separate artifacts, receipts, states, and owner decisions. `accepted`
  means owner-approved for explicit adoption review; only `adopted` permits
  the adoption flag.
- Preserve the source profile and all logical provenance refs.
- Run the downstream `aoa-session-harvest` automation-opportunity route only
  after a reviewed candidate exists; its readiness posture remains separate
  from this candidate packet.

## Stop line

Stop with a candidate, `insufficient_evidence`, or explicit rejection. Never
turn frequency, correlation, a green validator, or a launched actor into
adoption or a benefit claim.
