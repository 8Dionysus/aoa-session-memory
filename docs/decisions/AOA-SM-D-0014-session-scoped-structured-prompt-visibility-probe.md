# Session-Scoped Structured Prompt-Visibility Probe

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0014
- Original date: 2026-07-17
- Owner surfaces: `scripts/aoa_session_memory.py`, `DESIGN.AGENTS.md`, `PIPELINE.md`, `skills/aoa-session-memory-evidence-route/SKILL.md`
- Surface classes: query routing, source-aware admission, skill evidence, raw evidence
- Projection layers: entity usage chain, skill candidate evidence, archived raw fallback
- Guard families: session scope, structured prompt entry, context-only admission, bounded raw read, no persistent index
- Posture: accepted

## Context

Skill usage packets already rejected developer instructions and skill catalogues
as invocation evidence. That prevented false usage, but it also meant a
consumer could not positively distinguish “this skill was visible in the
prompt” from “no evidence about this skill was found.”

The missing state matters for hard negatives and adoption analysis. Treating
every prompt catalogue entry as a normal route posting would restore the state
by copying high-cardinality developer boilerplate into the operational index.
Broad text search would have similar noise and cost while still requiring a
reader to infer the source role.

## Options Considered

- Index every prompt-visible skill as a global entity or usage posting. This
  makes visibility cheap to query but recreates the semantic noise and
  cardinality pressure that source-aware admission is meant to remove.
- Run broad FTS or raw search for every skill miss. This keeps storage stable
  but widens a typed query into unrelated prompt, documentation, and tool
  output text.
- Leave prompt visibility as a manual raw-inspection step. This preserves
  boundaries but prevents the normal evidence packet from representing the
  state and its claim limits.
- Add a bounded query-time probe over the initial structured context of one
  explicitly selected session.

## Decision

For a skill usage query scoped to one resolved session, when the structured
dispatch route has no candidate, inspect only a bounded set of initial
`CONTEXT_STATE` raw refs from that session.

Admit `prompt-visible` only when a developer or system message contains an
exact named entry under `### Available skills` with a structured
`(file: .../SKILL.md)` source. Emit one context event with raw, segment index,
segment Markdown, raw-block, and session-manifest refs.

The event never enters usage, selection, skill-read, invocation, behavior,
verification, or consequence counts. The probe writes no index or graph edge
and is not used for global queries. A positive exact match may be returned from
the bounded window; absence is claimable only when the entire declared window
was readable and untruncated.

## Rationale

The chosen route uses the session partition already supplied by the caller and
opens only raw refs identified by the initial segment index. Structural
matching uses the catalogue entry name rather than arbitrary occurrences in a
skill description, so nearby names do not become candidates.

This preserves a meaningful source-aware state without charging all sessions,
skills, and graph consumers for prompt boilerplate. Exact evidence refs keep
the result auditable, while explicit probe status prevents a partial read from
becoming a false absence claim.

## Consequences

- Session-scoped hard negatives can distinguish prompt visibility from no
  observed skill evidence.
- The first such query pays a small bounded raw-read cost.
- Global skill usage remains free of prompt-catalogue postings.
- Actual selection, reading, behavior, verification, and consequence still
  require their stronger structured or reviewed evidence routes.
- A prompt format that lacks the structured available-skills entry remains
  unrecognized rather than being guessed from prose.

## Boundaries

This decision does not prove that a model read, selected, followed, invoked, or
benefited from a skill. It does not authorize global prompt scans, promote
session evidence into skill truth, or replace owner review. It does not make an
active transcript tail current; the packet separately reports provider and
live-tail freshness.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.AGENTS.md`
- `PIPELINE.md`
- `skills/aoa-session-memory-evidence-route/SKILL.md`

## Follow-Up Route

Keep the probe behind structured dispatch, preserve its session scope and raw
budget, export it through the normal portable builder, and revisit the choice
only if manual evidence shows that another structured prompt format needs a
separate bounded parser.

## Verification

A manually reviewed archived hard-negative contained an exact available-skill
entry but no structured skill call or read. Before the change, the usage packet
correctly denied invocation yet could not represent prompt visibility. After
the change, the same packet returned one `prompt-visible` context event with
resolvable evidence refs and zero usage or consequence events. An owner-neutral
synthetic regression proves the positive entry, a name appearing only inside a
description, context-only action semantics, and bounded absence behavior.
