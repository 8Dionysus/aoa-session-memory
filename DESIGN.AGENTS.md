# AoA Session Memory Agent Surface Design

## Role

`DESIGN.AGENTS.md` describes the desired form of agent-facing guidance inside
the `.aoa` session-memory kernel.

It is not an `AGENTS.md` card, naming table, schema, generated index, or
distillation report.

It answers one question:

What shape should agent-facing surfaces take so an agent can preserve, route,
rehydrate, review, and name sessions without losing raw evidence or layer
boundaries?

## Design Thesis

The session-memory bundle should not give agents one giant instruction wall.

It should give them a layered route mesh:

- root agent law for immediate boundaries;
- design surfaces for system form and agent-facing form;
- pipeline and readiness surfaces for operational gates;
- naming topology for stable labels, semantic names, and evidence anchors;
- generated indexes that guide navigation without becoming authority;
- session-local cards and manifests that narrow the lane;
- skills that turn deliberate recovery and review into repeatable workflows.

Agent guidance is not stronger because it says more. It is stronger when the
right surface appears at the right layer and points back to stronger evidence.

The root names the archive law.
The design names the system form.
The index names the route.
The manifest names the technical identity.
The raw transcript keeps the evidence.
The skill performs the deliberate pass.
The closeout returns the work to future agents.

## Design as Layer Ladder

Every later task is a quality test of the layers beneath it.

Session naming is the clearest example. A fast and accurate naming pass can
only happen when the earlier layers are already coherent:

- raw transcript provenance is preserved;
- compaction intervals and segments are current;
- segment indexes expose decisions, commands, errors, lessons, and final state;
- session-act and work-context indexes expose memory, MCP, goals, hooks, tools,
  and the likely active repository without replacing raw refs;
- route-signal indexes expose scope contracts, authority surfaces, verification
  states, failure modes, memory provenance, freshness, owner routes, runtime
  state, mutation surfaces, access boundaries, and operator preferences as
  route evidence, not reviewed truth;
- the agent atlas exposes a small tree of route axes before agents open heavy
  archive material;
- manifests, registry records, and archive-local TOC agree;
- semantic names can carry raw refs and coverage rather than naked aliases;
- rehydration and review packets can explain why a name is deserved.

If naming feels hard, the answer is usually not to invent a cleverer title. The
answer is to inspect which earlier layer failed to make the session legible.

This is the ladder rule:

```text
preservation -> segmentation -> indexing -> routing -> review -> naming -> promotion
```

No layer should pretend the previous one is complete. A later pass may reveal
weakness below it, but the repair belongs at the weakest responsible layer.

## Agent Surface Anatomy

### Root card

`AGENTS.md` owns the immediate route law: what must be read, what is generated,
what must not be claimed, and which evidence is protected.

It should stay compact. It routes agents into the deeper surfaces instead of
trying to hold the whole design.

### System design

`DESIGN.md` owns the memory system form: raw truth, compaction intervals,
indexes, diagnostics, distillation, hooks, skills, and portability.

It tells agents what kind of archive they are preserving.

### Agent-surface design

This file owns the agent-facing form: how route surfaces, generated companions,
session-local cards, skills, validation, naming gates, and closeout expectations
should cooperate.

It tells agents how to move through the archive without flattening the layers.

### Naming topology

`NAMING.md` owns durable labels, semantic names, scopes, anchors, fallback
words, and generated segment roles.

It should be read before any physical relabel, semantic `name-session`, naming
queue, or naming-readiness pass.

### Pipeline and readiness

`PIPELINE.md` owns operational flow.
`READINESS.md` owns current proof posture and coverage.

They are the surfaces an agent should use before deciding that a layer is ready
for the next pass.

### Generated companions

`sessions/AGENTS.md`, `sessions/INDEX.md`, `sessions/index.json`,
`SESSION_NAMES.md`, `session-name-index.json`, `session-registry.json`,
session indexes, segment indexes, generated atlas entries, reports, and
diagnostics are companions.

They route and compress. They do not author truth. They must stay reproducible
from stronger evidence or explicit review.

### Agent atlas

`maps/` is the source-owned skeleton for the generated atlas.

The root atlas files and axis `README.md` files are authored route shape.
`maps/by-*/entries/`, per-axis indexes, and root atlas indexes are generated
route companions. The axis tree may grow as the archive learns new recurring
route questions, but every entry should keep the same small shape: route key,
session identity, work context, authority surface, confidence, route layer,
signal count, next route, and evidence refs.

### Session-local surfaces

Each session directory carries its own `AGENTS.md`, `SESSION.md`,
`session.manifest.json`, `session.index.json`, raw source metadata, segment
indexes, diagnostics, and distillation artifacts.

Those surfaces narrow the lane for that archive. The raw transcript remains the
black box.

### Skills

Skills are deliberate routes for work that should not live inside a lifecycle
hook: archive rebuilds, raw diagnostics, rehydration, first-pass distillation,
manual review, promotion review, stress passes, and reindexing.

When a task becomes recurring, prefer a skill route over a long chat-only
procedure.

### Source districts

Portable source districts such as `config/`, `hooks/`, `schemas/`, `scripts/`,
`skills/`, `tests/`, and `sessions/` should carry their own `AGENTS.md` card.

Those cards are not replacements for root law. They narrow the lane at the
point where an agent is likely to edit or inspect that district.

`diagnostics/` is different: it is a live runtime evidence district. Its
`AGENTS.md` should guide inspection and cleanup, but it should not make
diagnostics part of the clean portable export.

## Source Order

Agents should rank evidence by source strength before naming, reviewing,
repairing, or promoting anything:

1. Raw transcript JSONL and raw source metadata.
2. Session manifest technical identity: `session_id`, source path, archive
   path, span, counts, and diagnostic state.
3. Segment Markdown and segment indexes generated from the raw archive.
4. `SESSION.md`, `session.index.json`, `session-registry.json`,
   `sessions/AGENTS.md`, `sessions/INDEX.md`, `sessions/index.json`,
   `SESSION_NAMES.md`, and `session-name-index.json`.
5. Diagnostics, stress-pass reports, rehydrate packets, review packets, and
   provisional distillation outputs.
6. Semantic names and aliases.
7. Promoted skills, automation, policy, or durable doctrine.

Lower layers may guide navigation through stronger layers, but they do not
override them. A semantic name can be useful before review, but it cannot
erase the `session_id`, raw path, or coverage limits that made the name.

## Naming-Readiness Before Naming

Do not start a broad naming pass by applying names.

Start by asking whether the archive can support names:

1. Does the session have readable raw evidence or a visible raw-unavailable
   diagnostic?
2. Do segment counts match current compaction boundaries where raw is present?
3. Do `SESSION.md`, `session.index.json`, `session.manifest.json`, registry,
   `SESSION_NAMES.md`, `sessions/AGENTS.md`, and `sessions/INDEX.md` agree?
4. Can the candidate name cite raw refs, segment refs, or review packet refs?
5. Is the candidate a whole-session name, a phase name, a topic name, or an
   alias?
6. Is coverage clear enough to avoid naming one late phase as the whole
   session?
7. Is the session small enough for direct naming, or large enough to require
   phase/topic discovery first?
8. Is the result still provisional, or has a reviewed distillation accepted it?

If any answer is weak, record the blocker and route to recovery, reindex,
manual review, or a narrower candidate queue. Do not hide the weakness behind a
confident-looking semantic name.

The operational entry for this layer is:

```bash
python3 scripts/aoa_session_memory.py naming-readiness all \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --refresh-indexes \
  --write-report
```

This command refreshes the lightweight naming route in `SESSION_NAMES.md` and
`sessions/INDEX.md`. It does not apply names and does not close review.

For long sessions, the next layer is phase discovery:

```bash
python3 scripts/aoa_session_memory.py phase-discovery <session-label-or-id> \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --write \
  --write-report
```

This writes `naming/phase-discovery.json` and `.md` as open candidates. A later
agent may apply accepted `phase` or `topic` names, but the candidate file itself
is not reviewed truth.

Every candidate should expose its linked signal bundle. A phase name is stronger
when the user intent, touched paths, command/check/error/mutation counts,
coverage range, and raw refs all point in the same direction. Generic prompts
should become low-confidence path/event candidates, not durable names.

Showing weakness is not enough. The phase-discovery artifact must also create a
review queue: each weak candidate needs an action, synthesis inputs, and an
apply template so the next agent can turn diagnosis into a reviewed semantic
name without guessing the route.

The apply route should be procedural, not a copied low-level command. A weak
candidate must pass through `review-phase-name --reviewed-name ... --apply`;
`--use-candidate` is only valid for candidates already marked
`ready_for_raw_check`. Successful application refreshes the name index and the
sessions table of contents, so the route does not depend on the agent holding
the whole chain in active context.

For archive-wide naming, agents should use a naming wave. The wave is a
multi-session review packet that turns the readiness map into explicit
actions: sync, reindex, phase review, semantic session-name review, or skip.
It can synthesize candidate umbrella names, but the apply layer still requires
`reviewed_name` unless the operator deliberately chooses the high-confidence
`--accept-proposed` path. This keeps speed from becoming silent promotion.

Naming waves must keep semantic names separate from physical relabels. A wave
may attach or revise a `session` semantic name with raw refs and bridge
anchors; it may not move archive directories. Directory relabeling is a later
operation after the semantic map has proved itself.

## Post-Change Route Review

Any change to a route surface should end by checking the adjacent surfaces it
now implies.

Use this review after changing:

- root route files: `AGENTS.md`, `DESIGN.md`, this file, `README.md`,
  `PIPELINE.md`, `READINESS.md`, `INSTALL.md`, or `NAMING.md`;
- generator behavior, schemas, config, hook output, diagnostics, indexes, or
  naming logic;
- skills, user-level router behavior, exported bundle contents, or tests;
- session-local cards, manifests, generated indexes, or review packet shape.

Do not update every surface mechanically. Ask which route a future agent will
follow, which file will be read first, and whether the changed meaning is now
visible at the right layer.

The minimum closeout for such a change should state:

- changed route surfaces;
- regenerated or exported companions;
- validation run against source and, when portable behavior changed, the
  standalone bundle;
- skipped checks and why;
- remaining weak layer, if any.

## Decision Review

`.aoa` does not need a decision log for every wording fix.

Use a durable decision artifact only when a change alters archive topology,
source order, portability law, naming policy, promotion rules, hook behavior,
or the expected route for future agents. Until such a decision district exists,
record the decision in the closest design/readiness surface and in the final
closeout.

## Authority Boundaries

Agent-facing surfaces may:

- route work;
- name the next evidence surface;
- require validation;
- expose layer readiness;
- propose names, review packets, and promotion candidates;
- preserve closeout memory for the next agent.

They must not:

- turn generated indexes into source truth;
- treat semantic names as reviewed claims without review;
- replace raw refs with vibes or broad summaries;
- repair physical labels when a semantic name is the safer layer;
- call raw-unavailable sessions understood;
- close review just because a candidate was found;
- promote lessons into skills or automation without the reviewed path.

## Agent Operation Route

A safe agent move in `.aoa` follows the route before touching content:

1. Read nearest `AGENTS.md`.
2. Read `DESIGN.md`.
3. Read this file.
4. Read `README.md`, `PIPELINE.md`, `READINESS.md`, and `NAMING.md` for the
   active kind of work.
5. Use `sessions/AGENTS.md`, `sessions/INDEX.md`, `SESSION_NAMES.md`, and
   `session-registry.json` to choose the target session.
6. Inside the target session, read `AGENTS.md`, `SESSION.md`,
   `session.manifest.json`, and `session.index.json`.
7. Read relevant segment indexes before opening full segment Markdown.
8. Open raw JSONL only to verify, recover, inspect exact evidence, or anchor a
   durable claim.
9. Run the narrowest useful validation before broader gates.
10. Close out with changed surfaces, checks run, checks skipped, remaining
    risk, and the next layer to improve.

## Design Principles

### 1. Layer readiness before layer ambition

Do not perform late-layer work when earlier-layer evidence is missing or stale.
Use the late-layer task to reveal the missing gate, then repair the right layer.

### 2. Source before generated companion

Generated indexes and reports accelerate navigation. They do not become the
source of truth for raw events, reviewed claims, or promoted lessons.

### 3. Semantic names need anchors

A semantic name without raw refs, coverage, and a preserved bridge to
`session_id` is only a label. A durable name is a routed claim.

### 4. Proximity narrows the lane

Root docs set archive law. Session-local files set archive context. Segment
indexes set interval context. Raw transcript verifies exact evidence.

### 5. Hooks preserve, skills refine

Hooks should stay light, schema-valid, and fail-open. Heavy understanding,
repair, review, naming, and promotion belong to deliberate commands and skills.

### 6. Review remains open until reviewed

A candidate found by batch, manual-review, naming-readiness, phase-discovery,
or promotion review remains open. Only a later reviewed path may close or
promote it.

### 7. Portability comes from shape, not local doctrine

The bundle may serve local AoA and Tree of Sophia work, but its portable kernel
should remain useful wherever Codex-like sessions need raw-preserving memory.

### 8. Closeout is future context

A closeout is the next agent's entry surface. It should name what changed, what
was checked, what is still weak, and which layer should be improved next.
