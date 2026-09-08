---
name: aoa-session-batch-distill
description: Use when many indexed `.aoa` sessions need a first-wave distillation conveyor that separates safe automatic first-pass artifacts from manual review and mechanics-improvement queues.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-batch-distill

Use this when a group of archived sessions needs to be laid out for first-wave
distillation without pretending that automatic classification is reviewed
truth.

## Trigger Boundary

- The user asks to process many historical sessions.
- A rolling window has already been imported into `.aoa`.
- The agent needs a queue that separates automatic first-pass work from manual
  reading, mechanics candidates, and diagnostics.
- The session-memory mechanism itself may improve while the queue is processed.

## Procedure

Batch distillation is set-oriented and has no positional session argument.
Declare a bounded set with `--since`, `--since-days`, `--until`, and/or
`--limit`, then carry the same predicate through any separately authorized
follow-on route. The current batch and title-repair implementations use the
same chronological registry selector, but a report is the binding set: before
any follow-on apply, compare its selected session IDs with the prior report.
Stop on any mismatch and re-plan that changed set under explicit scope
authorization. An archive-wide `all` selector in a maintenance command is a
new scope decision; it is never implied by processing one session or one
bounded batch.

Start with a planning report:

```bash
python3 scripts/aoa_session_memory.py batch-distill \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --since-days 21 \
  --limit 10 \
  --write-report
```

Review the report lanes:

- `auto_first_pass`: safe to write provisional first-pass artifacts from
  indexes.
- `manual_review`: requires a responsible review layer before promotion; this
  can be agent-assisted and evidence-sampled, not raw rereading by the operator.
- `mechanics_candidate`: may imply tests, skills, hooks, docs, or CLI
  improvements.
- `diagnostic`: repair raw/index health before distillation.

Inspect owner quality before applying a broad pass. Each profile contains
`project_grounding` and `owner_resolution`; fallback grounding is not the same
as a resolved owner.

If title repair is separately authorized for this same bounded set, repair
weak imported titles before a broad manual review wave:

```bash
python3 scripts/aoa_session_memory.py repair-session-titles all \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --since-days 21 \
  --limit 10 \
  --write-report
```

Add `--apply` only after checking the plan.

Apply only after the queue shape is coherent:

```bash
python3 scripts/aoa_session_memory.py batch-distill \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --since-days 21 \
  --limit 10 \
  --apply \
  --write-report
```

Use `--limit` for the first smoke batch. Use `--force` only when an existing
first-pass artifact must be rebuilt.

After the automatic first-pass layer is coherent, use
`aoa-session-manual-review` for packetizing manual-review lanes and aggregating
promotion candidates without promoting them.

## Review Rule

Automatic work may write only provisional first-pass distillation artifacts.
It may not promote a pattern, amend a skill, add automation, or mark a claim as
reviewed.

Manual review means project-grounded review. Before promoting a claim, inspect
the session's `project_grounding` entry and read the nearest relevant
`AGENTS.md`, `DESIGN.md`, agent-facing design surface such as
`DESIGN.AGENTS.md` when present, or README. The operator should review
promoted claims and samples, not carry the entire archive in active attention.

## Adaptive Rule

After each batch, inspect `improvement_candidates` in the report. If the queue
shows recurring parser misses, noisy names, missing indexes, hook gaps, or
repeatable command patterns, emit the candidate as a provisional owner-routed
handoff. Do not patch, retrain, change hooks or CLI behavior, or rerun a repair
inside the data-processing batch. A separately authorized owner task may
inspect the candidate, make a narrow source change, run its owner checks, and
start a new bounded batch after review.

## Verification

- Every scoped session has an automatic, manual-review, mechanics-candidate,
  diagnostic, skip, or failure terminal receipt.
- All produced artifacts remain explicitly provisional.
- Owner resolution and evidence refs are present before project-specific
  interpretation.
- Mechanics candidates remain owner-routed handoffs; the batch does not change
  the bundle or its processing mechanism.
- No claim, skill change, automation, or durable lesson was promoted.

## Stop Line

Do not open every raw transcript in context. Use the batch report, registry,
manifests, distillation indexes, and segment indexes first.
