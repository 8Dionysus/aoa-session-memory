# AGENTS.md

## Applies to

This card applies to `capabilities/` and its descendants.

## Role

`capabilities/families/*.yaml` is the authored owner-local semantic map for
session-memory capabilities. `capabilities/port.manifest.json` joins that map
to the shared `aoa-skills` contract without transferring procedure truth.

## Boundaries

- `skills/**/SKILL.md` owns callable procedure; the capability source points
  to it and owns applicability, ABI, effects, lifecycle, and relations.
- `generated/capability_graph.*` and the generated router card are read models.
- One `primary_parent` supplies navigation. Typed relations carry every other
  dependency or compatibility claim.
- Session evidence may propose a change, but cannot edit capability truth or
  promote lifecycle state by itself.
- `aoa-skills` owns shared grammar and runtime representation; `aoa-evals`
  owns proof doctrine and verdict; `aoa-playbooks` owns admitted repeatable
  workflows.

## Validation

Use `python3 scripts/validate_local_capability_port.py --check-generated`.
Rebuild only through `python3 scripts/build_capability_projection.py`.

