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

Start with a planning report:

```bash
python3 scripts/aoa_session_memory.py batch-distill \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --since-days 21 \
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

Repair weak imported titles before a broad manual review wave:

```bash
python3 scripts/aoa_session_memory.py repair-session-titles all \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --since-days 21 \
  --write-report
```

Add `--apply` only after checking the plan.

Apply only after the queue shape is coherent:

```bash
python3 scripts/aoa_session_memory.py batch-distill \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --since-days 21 \
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
`AGENTS.md`, `DESIGN.md`, or README. The operator should review promoted
claims and samples, not carry the entire archive in active attention.

## Adaptive Rule

After each batch, inspect `improvement_candidates` in the report. If the queue
shows recurring parser misses, noisy names, missing indexes, hook gaps, or
repeatable command patterns, improve the bundle itself with a narrow patch and
rerun `doctor`, `audit`, and tests.

## Stop Line

Do not open every raw transcript in context. Use the batch report, registry,
manifests, distillation indexes, and segment indexes first.
