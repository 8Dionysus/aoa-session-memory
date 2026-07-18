# Owner Capability Home And Skill Evidence Lifecycle

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0018
- Original date: 2026-07-18
- Owner surfaces: `capabilities/`, `skills/`, `evals/`, `scripts/`, `generated/`, `docs/decisions/`
- Surface classes: capability source, skill routing, portability, attribution, lifecycle
- Projection layers: semantic tree, typed relation graph, deep retrieval, task-local DAG, runtime receipt
- Guard families: owner boundary, progressive disclosure, ABI compatibility, package provenance, evidence attribution, promotion gate
- Posture: accepted owner capability home

## Context

The repository had twenty focused `SKILL.md` packages and two globally
installed routers, but no owner-local machine-readable map connected their
triggers, ABI, effects, lifecycle, compatibility, package revision, or
evidence posture. Prompt selection and skill reads were correctly weaker than
invocation proof, yet no reviewed positive receipt could represent observed
procedure, verification, and consequence. Several procedures also embedded
one host layout directly in portable instructions.

The shared `aoa-skills` capability system already owns the general tree, graph,
retrieval, package-port, and task-DAG grammar. Copying that standard here would
create a second authority. Moving session-memory procedure truth into
`aoa-skills` would violate the opposite boundary.

## Options Considered

- Keep the flat package set and strengthen prose only. Rejected because
  composition, drift, lifecycle, provenance, and negative applicability would
  remain uncheckable.
- Copy the global `aoa-skills` tree into this repository. Rejected because a
  generated or duplicated map would become competing truth.
- Register every leaf as a globally visible bundle. Rejected because no
  routing evidence justifies a larger prompt-visible catalog.
- Add an owner-local capability home validated by the shared contract, retain
  only the two current advertised routers, and keep unproven visibility or
  benefit claims experimental.

## Decision

`capabilities/families/*.yaml` is the authored session-memory capability
source. It has one owner-local root, one navigation parent per node, typed
relations, full executable contracts, and source bindings back to the current
skill packages. `capabilities/port.manifest.json` federates the root under the
shared `aoa-skills:sessions` capability without copying the parent.

The shared contract, validator, discovery algorithm, and task-local DAG remain
owned by `aoa-skills`. Generated graph and router surfaces record the exact
owner sources, shared schema and validator fingerprints, and package
fingerprints. They are read models.

Only `aoa-session-memory-global-route` and
`aoa-session-memory-evidence-route` remain advertised. All other current
packages remain owner-local and deferred. Their skill-effect lifecycle stays
experimental until controlled comparison supports promotion. A CLI command
does not by itself justify a new visible bundle.

Portable procedures use logical workspace and session-memory roots.
Codex-specific behavior remains under the adapter branch. Installed host
state and execution receipts record concrete paths and fingerprints at
runtime; authored portable skills do not.

Positive skill evidence enters through a reviewed receipt linked to one task
episode, exact package version and fingerprint, observed procedure
checkpoints, tools, verifier result, consequence, and alternative
explanations. The receipt is candidate evidence. `aoa-session-memory`
classifies and routes it; `aoa-evals` retains verdict and promotion authority.

A task-local DAG is transient execution state. Only a repeatedly demonstrated
and separately admitted sequence may be proposed to `aoa-playbooks`.

## Rationale

This route preserves procedure ownership while making discovery and
composition reproducible. Compact descriptions remain first-pass routing
signals; the full contract and shallow references supply deep retrieval.
Versioned package closure distinguishes prompt visibility, selection,
procedure observation, verification, and effect without pretending that an
identical Markdown file behaves identically in every runtime.

Experimental lifecycle is deliberate: structural validity proves neither
selection quality nor outcome lift. It allows the repository to improve the
system without laundering current session mentions into proof.

## Consequences

- Positive: all current packages have stable identity, trigger, ABI, effects,
  trust, provenance, lifecycle, and relation records.
- Positive: router and graph drift are deterministic failures rather than
  manual comparison.
- Positive: mutating routes expose preview/apply, recovery, permission, and
  postcondition contracts.
- Positive: package and runtime fingerprints make stale prompt or installed
  state detectable.
- Tradeoff: source validation depends on a pinned `aoa-skills` contract
  checkout in CI or an explicitly selected sibling checkout.
- Tradeoff: most leaf skills remain deferred until behavioral evidence
  supports stronger visibility or lifecycle.
- Follow-up: route reusable controlled results to the owner-local eval port
  and central `aoa-evals`; propose a playbook only after repeated evidence.

## Boundaries

This decision does not make the generated graph authoritative, prove that any
skill improves outcomes, accept a local eval verdict, promote session
experience automatically, expose every leaf globally, or turn a task DAG into
a playbook. It does not make skills a security-policy layer; runtime tools,
permissions, and sandbox controls remain stronger.

## Source Surfaces

- `capabilities/port.manifest.json`
- `capabilities/families/session-memory.yaml`
- `skills/port.manifest.json`
- `evals/PORT.yaml`
- `scripts/validate_local_capability_port.py`
- `scripts/build_capability_projection.py`
- `scripts/aoa_session_memory.py`

## Follow-Up Route

Apply the owner-local routing suite through the `aoa-evals` local-port
execution contract, preserve execution receipts below proof authority, and
revisit visibility or lifecycle only through an independently reviewed
promotion decision.

## Verification

Use shared capability-home validation, generated parity, source and standalone
tests, package security scan, routing and composition cases, portable audit,
live read-only MCP scenarios, doctor, and manually reviewed no-skill/current/
candidate comparisons. Green structural checks preserve invariants only; the
central eval route owns any benefit verdict.

