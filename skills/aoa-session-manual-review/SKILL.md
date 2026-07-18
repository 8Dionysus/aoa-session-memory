---
name: aoa-session-manual-review
description: Use when `.aoa` first-wave manual review lanes need bounded review packets, owner-aware evidence samples, or an unpromoted promotion-candidate queue.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-manual-review

Use this after `batch-distill` has shown coherent manual-review lanes.

## Trigger Boundary

Use this only when provisional candidate packets already exist and require
bounded owner-aware human review. Do not use it to promote a raw session,
machine candidate, or plausible pattern directly.

## Procedure

Plan the wave first:

```bash
python3 scripts/aoa_session_memory.py manual-review \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --since-days 21 \
  --priority deep \
  --write-report
```

Apply only when the selected sessions and owner-resolution signals are
coherent:

```bash
python3 scripts/aoa_session_memory.py manual-review \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --since-days 21 \
  --priority deep \
  --apply \
  --write-report
```

Aggregate promotion candidates:

```bash
python3 scripts/aoa_session_memory.py promotion-review \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --since-days 21 \
  --write-report
```

## Rules

- Manual-review packets are review surfaces, not reviewed truth.
- Manual-review applies are append-only waves. Re-run only when another layer
  is intended, and keep prior packets open for future passes.
- Use `--wave-id` when the operator needs a semantic wave name; otherwise let
  the command choose the next `manual-review-waveN`.
- Promotion indexes may queue candidates, but `promoted_claim_count` must stay
  `0` until reviewed distillation accepts a claim.
- A promotion candidate is indexed evidence, not a closed item.
- Use `owner_resolution` before reading project-specific evidence. If it is
  `ambiguous`, `unresolved`, or `fallback_only`, do not promote
  project-specific claims.
- Use packet evidence refs and segment indexes before opening large raw JSONL.

## Verification

- Every packet has a keep, reject, revise, or owner-handoff disposition.
- Each disposition names the owner-resolution posture, evidence refs, and
  remaining uncertainty.
- `promoted_claim_count` remains `0`; promotion is a separate owner action.
- Prior review waves remain preserved.

## Stop Line

Stop after each scoped packet has a reviewed disposition or an explicit
evidence/owner blocker. Do not turn the queue, review packet, or current model
judgment into accepted knowledge.
