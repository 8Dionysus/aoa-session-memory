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

## Procedure

Generate the candidate layer:

```bash
python3 scripts/aoa_session_memory.py phase-discovery <session-label-or-id> \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --write \
  --write-report
```

Then refresh the indexes:

```bash
python3 scripts/aoa_session_memory.py naming-readiness all \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
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

## Stop Line

Do not rename archive directories from phase-discovery output. Use semantic
`review-phase-name` entries first, and keep the raw archive as source truth.
