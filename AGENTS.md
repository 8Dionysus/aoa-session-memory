# AGENTS.md

## Repository Identity

This repository owns the portable source of `aoa-session-memory`: an
evidence-preserving memory organ for agent sessions.

The current production adapter is Codex, and most live evidence currently comes
from Codex sessions. Codex is an adapter and evidence source, not the boundary
of the organ.

## Authority Map

Use one owner for each concern:

| Concern | Authoritative surface |
| --- | --- |
| System identity, boundaries, and durable architecture | `DESIGN.md` |
| Immediate agent laws and task routing | `AGENTS.md` |
| Agent query, evidence-packet, and escalation contract | `DESIGN.AGENTS.md` |
| Runtime behavior | source code, config, and schemas |
| Operational lifecycle, maintenance, and recovery | `PIPELINE.md` |
| Installation and portable export | `INSTALL.md` |
| Naming contracts | `NAMING.md` and naming policy |
| Readiness semantics and proof requirements | `READINESS.md` |
| Durable rationale for non-trivial owner choices | `docs/decisions/README.md` and source decision records |
| Revision-bound portable measurements | `stats/port.manifest.json` and its referenced packet |
| Current health, freshness, versions, and watermarks | live commands and generated diagnostics |
| What happened in a session | raw transcript plus resolvable session/segment refs |
| Current repository or domain truth | the owning repository's source surfaces |
| Evaluation truth | the owning eval surface and its admitted evidence |

`README.md` is an entrypoint. Generated search, graph, atlas, registry,
summary, and diagnostic surfaces are read models. Neither may override its
owner.

## Non-Negotiable Laws

1. Preserve evidence before interpreting it.
2. Raw transcript is evidence of what was recorded, not reviewed truth about
   the world, the operator, or another repository.
3. Keep resolvable raw, segment, and session refs for important claims.
4. Never replace raw evidence with segments, episodes, indexes, graphs,
   narratives, or summaries.
5. Treat every projection as versioned, freshness-bearing, rebuildable, and
   weaker than its source.
6. Keep mention, selection, invocation, behavior, verification, and consequence
   distinct.
7. Do not promote session experience into doctrine, memory, evals, skills,
   automation, training data, or model changes without the owning review and
   admission route.
8. Keep hooks lightweight, idempotent, observable, and fail-open. Heavy
   interpretation belongs to workers, commands, skills, or evals.
9. Keep the portable organ independent of local AoA, Tree of Sophia, host,
   operator, and repository-specific doctrine.
10. Observe current state from runtime evidence. Do not copy changing counts,
    versions, or health claims into durable design text.

## Route by Task

Read only the surfaces needed for the task:

- architecture, scope, evidence semantics, or future compatibility:
  `DESIGN.md`;
- query routing, MCP access, evidence packets, or agent navigation:
  `DESIGN.AGENTS.md`;
- hooks, capture, indexing, maintenance, orchestration, storage, or recovery:
  the relevant section of `PIPELINE.md`;
- installation, export, or hook generation: `INSTALL.md`;
- archive labels or semantic names: `NAMING.md`;
- completion or proof posture: `READINESS.md`, then run the applicable live
  gate;
- durable rationale, alternatives, or supersession: `docs/decisions/AGENTS.md`,
  then the generated index and source decision record;
- a portable measurement: `stats/AGENTS.md`, then the manifest, packet, and
  source corpus named by the measurement;
- a historical session: generated archive indexes first, then the narrowest
  segment/raw evidence required;
- a source district: its nearest `AGENTS.md`.

Do not read every root document by default.

## Source and Generated Boundaries

Source-owned portable surfaces include the root contracts, `docs/decisions/`,
config, hook templates, atlas skeleton, schemas, scripts, skills, tests,
`stats/`, and portable manifests.

Generated or runtime-owned material includes:

- session raw mirrors, raw blocks, segments, manifests, and indexes;
- session registries, name indexes, archive tables of contents, and generated
  session-local cards;
- generated atlas entries and indexes;
- search stores, graph stores, projection state, queues, and caches;
- diagnostics, receipts, reports, and maintenance state.

Regenerate derived material through the owning command. Do not hand-edit it
except during an explicit evidence-preserving repair with a diagnostic record.
Do not commit or export live private session material unless the operator
explicitly requests that scope.

## Change and Export Route

Before editing, identify the active authored source and preserve unrelated
user changes. A live `.aoa` install and a standalone Git checkout may have
different roles even when their portable files are identical.

When the active source feeds a portable bundle:

1. edit the authored source;
2. export with `export-bundle`;
3. verify source and standalone surfaces;
4. review that no sessions, raw text, host paths, secrets, runtime databases,
   or diagnostics leaked into the clean bundle.

Never update a generated or portable consumer by manual copy when the owner
builder/export route exists.

## Verification

Use the smallest proof that matches the changed surface:

- docs-only authority changes: inspect the rendered route, check referenced
  files, export parity, and portable audit;
- source/config/schema changes: focused tests plus `validate`;
- hooks or Codex adapter changes: grounding, hook status, and the applicable
  live lifecycle probe;
- projections or retrieval changes: freshness plus manual evidence-ref checks
  and the owning regression/eval route;
- portability changes: source validation, clean export, and standalone audit.

Tests and validators prove only their declared invariants. They do not replace
manual semantic or provenance review.

## Stop Lines

- Do not delete or rewrite historical raw/session evidence as cleanup.
- Do not treat summaries, names, embeddings, graph edges, or generated
  classifications as source truth.
- Do not expose secrets or private transcript content through portable
  artifacts, diagnostics, token accounting, or examples.
- Do not let MCP or another access plane become proof or mutation authority.
- Do not make Codex-specific behavior the permanent identity of the organ.
- Do not add session-local hypotheses, experiment journals, temporary metrics,
  or construction debris to owner docs.
- Do not claim freshness, readiness, causality, usage, or completion without
  the evidence route that proves it.
