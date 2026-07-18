---
name: aoa-session-phase-discovery
description: Use for long `.aoa` Codex session archives that need phase/topic candidate extraction before applying semantic session names.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-phase-discovery

Use this after `naming-readiness` routes a session to
`phase_topic_discovery_before_session_name`, or when a long session needs a
continuation name but its internal phases are not yet clear.

This skill generates open candidates. It does not apply semantic names and does
not close review.

## Trigger Boundary

Use this when naming readiness identifies a long or multi-topic session that
needs phase candidates. Do not use it for a short session with one reviewed
name, or when the target/index cannot be resolved uniquely.

## Procedure

Generate the candidate layer:

```bash
python3 scripts/aoa_session_memory.py phase-discovery <session-label-or-id> \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --write \
  --write-report
```

Then refresh the indexes:

```bash
python3 scripts/aoa_session_memory.py naming-readiness all \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --refresh-indexes \
  --write-report
```

## Reading The Artifact

- `naming/phase-discovery.json`: machine-readable candidate list.
- `naming/phase-discovery.md`: human-readable review table.
- `candidate.status=candidate_unreviewed`: still open evidence.
- `candidate.coverage.raw_ranges`: raw-line interval covered by the candidate.
- `candidate.evidence`: raw refs to inspect before applying a name.
- `candidate.confidence`: routing confidence, not truth confidence.
- `candidate.name_basis`: whether the name came from a specific user intent or
  from linked path/event signals.
- `candidate.quality_flags`: why the candidate needs caution, such as
  `generic_user_intent_present`, `no_specific_user_intent`, or
  `path_or_event_based_name`.
- `candidate.linked_signals`: the signal bundle used for naming, including
  primary intent, supporting paths, and event-type counts.
- `candidate.review`: the next action for the candidate. Weak candidates use
  `status=needs_semantic_synthesis` and include an `apply_template` for the
  `review-phase-name` route after synthesis.
- root `review_queue`: candidates that need semantic synthesis before they can
  be raw-checked and applied.

Generic prompts such as "Давай, действуй" or "Разложи план" should not become
durable phase names by themselves. They should route to linked path/event
signals and remain low-confidence until reviewed.

Do not stop after seeing `quality_flags`. Use `review_queue` as the next work
surface: inspect the linked signals, synthesize a stronger reviewed name, then
apply it with the provided command template.

## Applying Names

For faster long-session work, build batch review packets before synthesizing
names in chat:

```bash
python3 scripts/aoa_session_memory.py phase-review-assist <session-label-or-id> \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --from-segment <segment-id> \
  --limit 8 \
  --write \
  --write-report
```

This writes `naming/phase-review-assist.json`, `.md`, and a
`phase-review-plan.template.json`. It does not apply names. Use the packets to
review several segments at once: user requests, progress markers, decisions,
checks, errors, mutations, commands, top paths, and raw refs are already
collected from source raw.

After reviewed names are filled into a plan JSON, preview or apply the batch
through the guarded plan route:

```bash
python3 scripts/aoa_session_memory.py apply-phase-review-plan <session-label-or-id> \
  --plan sessions/<session>/naming/phase-review-plan.json \
  --apply \
  --write-report
```

This still calls `review-phase-name` per segment under the hood. Empty
`reviewed_name` entries are skipped, and machine candidates are not accepted as
reviewed truth by the plan route.

Preview one candidate before applying it:

```bash
python3 scripts/aoa_session_memory.py review-phase-name <session-label-or-id> \
  --segment <segment-id>
```

Apply only after the name has been reviewed. For weak candidates, pass the
reviewed name explicitly:

```bash
python3 scripts/aoa_session_memory.py review-phase-name <session-label-or-id> \
  --segment <segment-id> \
  --reviewed-name "<reviewed phase name>" \
  --apply \
  --write-report
```

For candidates marked `ready_for_raw_check`, `--use-candidate` is accepted only
after raw samples are checked. It is rejected for
`needs_semantic_synthesis`.

## Verification

- Every phase candidate carries bounded raw ranges and evidence refs.
- Generic prompts alone do not become durable names.
- Candidate confidence remains routing confidence, not truth confidence.
- No phase or session name changes during discovery.

## Stop Line

Do not rename archive directories from phase-discovery output. Use semantic
`review-phase-name` entries first, and keep the raw archive as source truth.
