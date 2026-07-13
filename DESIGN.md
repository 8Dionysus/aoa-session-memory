# AoA Session Memory Design

## Role

`DESIGN.md` is the durable architecture and boundary contract for
`aoa-session-memory`.

It describes what the organ is, which truths it may own, how its layers relate,
and which future growth the current architecture must not close off. It is not
a command reference, runtime status report, experiment journal, naming table,
or claim that every horizon capability is already implemented.

## Design Thesis

`aoa-session-memory` is a portable, evidence-preserving memory organ for agent
sessions.

It exists to make agent experience addressable across compaction, sessions,
runtimes, and, eventually, model generations without making unreviewed
experience authoritative.

A context window is working memory, not a durable memory system. A session can
overflow, compact, terminate, move to another runtime, or survive only as a
lossy summary. The commands, observations, corrections, dead branches,
decisions, outcomes, and exact evidence that shaped the work must be able to
survive those transitions outside active context.

The answer is not to keep everything in the prompt. The answer is to preserve
experience, give it stable coordinates, derive bounded read models, and keep a
reviewable path from every important claim back to evidence.

The deepest purpose is continuity of experience and transformation. Evals,
skills, automation, training corpora, and specialized agents are possible
downstream crystallizations of that experience. They are not the definition of
the organ and they do not become authoritative merely because the memory organ
can propose them.

## Position in the Wider System

`aoa-session-memory` is an organ of an agentic system, not the whole system.

It owns:

- preservation and identity of session-bound evidence;
- temporal and provenance binding across events, spans, episodes, and sessions;
- rebuildable indexes and projections over that evidence;
- evidence-routed retrieval and bounded navigation;
- visibility of freshness, uncertainty, truncation, and failure;
- portable adapter contracts for session-producing runtimes;
- candidate routes from experience toward later review.

It does not own:

- the current truth of another repository or domain;
- AoA doctrine or Tree of Sophia meaning;
- the identity, personality, or consciousness of an agent;
- central eval doctrine or final proof verdicts;
- skill, automation, policy, or model-training authority;
- model execution, tensor storage, or training infrastructure;
- the right to promote observed behavior into a durable rule.

The organ can remember that a decision was made. The owner repository decides
whether that decision still governs. The organ can preserve an eval run. The
eval owner decides what it proves.

## Current Contract and Open Horizon

The current production adapter is Codex. Codex transcripts, lifecycle hooks,
compaction markers, commands, tool calls, and responses are therefore the most
developed evidence stream today.

This is an implementation priority, not an ontological boundary.

The architecture must permit other session producers to attach compatible
evidence without pretending that all producers emit the same kinds of
experience. A dialogue-oriented agent, an action-oriented coding agent, an
instrumented model experiment, and a training/eval run may share identity,
time, provenance, and reference contracts while keeping different event
semantics and projection pipelines.

Future capabilities belong in this design only as extension laws:

- continuity may cross runtimes and model versions;
- selected experience may later support evals, skills, automation, datasets,
  fine-tuning, or specialized agents;
- model instrumentation may be linked to session trajectories;
- narratives may connect projects and long developmental arcs.

None of those statements is a present-tense capability claim. If latent,
activation, or other model-state traces are added later, they are measured
instrumentation. They are not automatically hidden reasoning, intention,
emotion, consciousness, or truth about the model.

## Design as Physiology

The physiological metaphor remains useful when its boundaries stay precise:

- active context is working memory and attention;
- raw session evidence is the flight recorder;
- events and spans are recorded experience;
- episodes are bounded working memories reconstructed over evidence;
- exact indexes are fast recall;
- semantic projections are associative recall;
- typed graphs are relationship and causality views;
- narratives are slow, higher-order consolidation;
- freshness orchestration is circulation and repair;
- review is judgment;
- promoted skills and automation are learned capability;
- training or model adaptation is a later transformation owned elsewhere.

Compaction is a useful capture coordinate, not necessarily a semantic boundary.
A meaningful episode may begin before compaction and finish after it. The raw
boundary must remain visible while episode formation follows intent, action,
result, correction, verification, failure, and recovery.

## Authority Is Typed

There is no single global ranking in which one file is always “more true.”
Authority depends on the question.

| Question | Strongest authority |
| --- | --- |
| What bytes or events were recorded in the session? | raw transcript and source metadata |
| What interval or episode does a projection describe? | projection plus resolvable raw/segment/session refs |
| Did a command, tool, hook, or runtime action occur? | structured event and runtime receipt evidence |
| What does the repository do now? | current owner source, config, schemas, and live runtime |
| Why is an architectural boundary durable? | owner design/decision surface |
| What did an eval prove? | admitted eval evidence and the eval owner |
| Is a skill or automation authoritative? | its owner source and review/admission route |
| What should an agent read next? | generated route models, qualified by freshness |

Raw evidence is authoritative for what was preserved, but it is not reviewed
truth about the world. A user or assistant may be mistaken. A successful
command may print documentation about failures. A transcript may mention a
skill without using it. A later owner change may supersede an earlier session
decision.

Generated segments, episodes, indexes, embeddings, graph edges, dossiers, and
narratives are evidence-bearing read models. They may improve access and
interpretation; they do not replace their sources.

Owner-local statistics are revision-bound measurements over named source
populations. Their manifest, packet, refs, and authority ceiling define what
they can support; portable fixture coverage is not memory quality or live
readiness.

## Two Durable Records

The system deliberately maintains two different durable records:

1. Session memory preserves evidence of what happened, including uncertainty,
   error, disagreement, and failed work.
2. Owner repositories preserve the selected current truth of the systems they
   own.

A review and promotion gate connects them:

```text
session evidence
  -> evidence-backed candidate
  -> owner review
  -> admitted decision / eval / skill / automation / dataset
```

This gate prevents both forms of corruption:

- losing valuable experience because it was not immediately promoted;
- polluting owner terrain by copying every session insight, hypothesis, or
  construction detail into permanent source.

## Memory Streams

The organ should support heterogeneous streams rather than flattening all
experience into one text field.

### Interaction memory

User intent, questions, corrections, assistant responses, dialogue phases,
handoffs, and unresolved threads.

### Operational memory

Plans, tool calls, commands, mutations, outputs, errors, retries,
verification, closeout, and action-to-consequence chains.

### Evaluation memory

Cases, conditions, versions, seeds, budgets, outcomes, adjudication, and proof
refs. Evaluation memory remains evidence for the eval owner, not the final
verdict by itself.

### Instrumentation memory

Runtime telemetry and, in the future, model-state observations attached to
precise session coordinates. Instrumentation must retain measurement method,
model/runtime version, scope, uncertainty, and privacy boundary.

### Lineage memory

In the future, datasets, model versions, training runs, skills, agents, and
their measured consequences may be linked to the session experience that
produced them. Lineage does not make the session-memory repository the owner of
those artifacts.

All streams should share a minimal envelope where applicable:

- stable identity;
- session/run identity;
- timestamp or interval;
- actor, runtime, model, and owner context;
- source kind;
- raw or external evidence refs;
- schema and producer version;
- confidence and uncertainty;
- validity and supersession state;
- privacy, retention, and access metadata.

Sharing this envelope does not require one universal ingestion pipeline.

## Durable Primitives

The architecture distinguishes the following primitives:

- **session** — one runtime-bounded trajectory with stable identity;
- **event** — an observed atomic record from a producer;
- **span** — a contiguous evidence interval;
- **episode** — a bounded semantic working unit over one or more spans;
- **entity** — a typed identity such as a skill, tool, MCP, repository, goal,
  error, decision, model, or artifact;
- **relation** — a typed, directed, evidence-backed connection;
- **narrative** — a higher-order consolidation over episodes with preserved
  refs;
- **projection** — a rebuildable read model over stronger evidence;
- **evidence ref** — a resolvable coordinate into raw, segment, session, or an
  external owner surface;
- **candidate** — an unpromoted interpretation or downstream possibility;
- **receipt** — structured evidence that a lifecycle or runtime action was
  observed.

Stable IDs must not depend only on a mutable title or rendered summary. Names
improve navigation; they do not replace technical identity.

## Physical Archive Contract

The current portable archive centers on a session directory:

```text
sessions/
  YYYY-MM-DD__NNN__short-title/
    AGENTS.md
    SESSION.md
    session.manifest.json
    session.index.json
    hooks/
    raw/
      session.raw.jsonl
      source.json
      blocks/
      blocks.index.json
      compaction-events.jsonl
    segments/
    incidents/
    distillation/
```

The full raw transcript remains the preserved black box. Raw blocks provide
bounded interval access. Segment Markdown is a readable projection. Segment
and session indexes provide navigation. Naming rules and exact generated
shapes belong to `NAMING.md`, schemas, and `PIPELINE.md`.

Physical topology may evolve, but migrations must preserve stable identity,
evidence refs, source provenance, rebuildability, and rollback.

## Memory Lifecycle

The durable lifecycle is:

```text
capture
  -> preserve
  -> normalize
  -> project
  -> retrieve
  -> read and compare evidence
  -> review
  -> retain / supersede / promote / explicitly forget
```

### Capture

Capture records the producer event and enough source identity to recover it.
The capture path should be lightweight, loss-aware, and fail-open for the
active agent runtime.

### Preserve

Preservation is the first non-negotiable duty. Failure, repetition, wrong
assumptions, dead branches, and noisy outputs remain valuable evidence at this
layer.

### Normalize

Normalization adds typed structure without erasing source form. It must retain
producer/schema versions and permit reprocessing when taxonomy improves.

### Project

Projection creates exact, semantic, graph, episode, narrative, registry, and
diagnostic read models. Every projection is disposable in principle and
rebuildable from stronger evidence.

### Retrieve and read

Retrieval finds candidate evidence. A reading stage establishes support,
temporal order, contradiction, supersession, and insufficiency before making a
claim.

### Review and promote

Review decides whether an observation becomes a durable owner-controlled
artifact. Promotion is a cross-boundary act and must follow the target owner's
admission route.

### Retain, supersede, forget, and roll back

Changing facts need validity and supersession rather than silent overwrite.
Forgetting or retention changes require explicit policy, auditability, and
rollback appropriate to the evidence class. The current protected raw archive
must not be rewritten or deleted as ordinary cleanup.

## Episode Projection

Events are preservation units. Episodes are primary semantic retrieval units.

Episode boundaries should follow the work:

- user intent and correction;
- goal or task lifecycle;
- owner or repository transition;
- action, result, and verification;
- decision and supersession;
- failure, abandoned branch, recovery, and rerun;
- coherent quiescence or closeout.

Compaction, turn, and segment boundaries are evidence coordinates and useful
hints. They are not mandatory semantic cuts.

An episode should carry:

- stable ID and session binding;
- raw, segment, and session refs;
- time span and work context;
- intent, actions, outcome, and verification;
- entities and exact lexical anchors;
- facts, decisions, failures, and open questions;
- confidence, validity, and supersession;
- a concise narrative;
- multiple search representations rather than one monolithic embedding.

Episodes never replace raw events. An episode that cannot resolve its evidence
refs is an invalid projection.

## Projection Architecture

No single read model should answer every query.

### Exact lexical projection

Optimized for paths, UUIDs, commands, flags, error text, dates, names, and
literal phrases. Exact recall must remain available even when a cheaper typed
route is preferred first.

### Typed registry and posting projections

Optimized for entity identity, existence, usage candidates, route signals,
facets, and compact rollups. Registration, mention, selection, invocation,
behavior, verification, and consequence are separate states.

### Semantic and hybrid projections

Optimized for paraphrase and related episodes across languages. Source kind is
part of semantics: user intent, assistant answer, reasoning boundary,
structured tool call, command output, system instruction, loaded skill
payload, documentation, and generated summary must not receive equal
evidentiary weight.

### Typed graph views

Optimized for temporal, causal, entity, owner, dependency, and bridge
questions. The graph is topology, not a second transcript store.

### Narrative and global projections

Optimized for themes, phases, recurring failures, changing decisions, and
long developmental arcs. They are consolidated lazily over episodes and keep
their evidence chain.

### Diagnostic and freshness projections

Optimized for deciding whether another projection is current, stale-readable,
deferred, blocked, failed, truncated, or unavailable.

The same physical store may host several logical projections. Physical
separation is an implementation choice, not a design goal.

## Query and Evidence-Reading Contract

A query route should:

1. classify intent without overstating certainty;
2. choose the cheapest sufficiently specific typed route;
3. carry an explicit evidence, node, edge, token, time, and fallback budget;
4. escalate only when the first route is insufficient;
5. expose selected route, projection version, freshness, truncation, and
   fallback state;
6. stop when evidence is sufficient;
7. return unknown or insufficient evidence when it is not.

Exact identifiers should not pay for broad graph or semantic expansion.
Local questions should not trigger global narrative search. Graph traversal
should begin from exact or hybrid anchors. Broad raw-text fallback should be
bounded but remain available until a replacement proves equal or better
recall.

The evidence-reading stage should:

- identify the supporting refs for every important claim;
- separate fact, observation, interpretation, opinion, and uncertainty;
- order temporal evidence;
- detect conflict and supersession;
- keep rejected or foreign-correlation context auditable but outside the
  accepted chain;
- abstain when support is incomplete.

## Relationship Semantics

Mention is not a durable relationship.

Durable graph relations should be typed, directed, and evidence-backed, for
example:

- `used_in`;
- `produced`;
- `caused`;
- `resolved_by`;
- `verified_by`;
- `supersedes`;
- `valid_during`;
- `owned_by`;
- `depends_on`;
- `decided_in`;
- `failed_with`;
- `recovered_by`.

Logical graph views should distinguish at least:

- entity and usage topology;
- temporal validity and supersession;
- causal action-result-verification chains;
- authority, owner, and dependency boundaries.

Ordinary sequence belongs in an event or episode timeline when that is cheaper
and clearer than materializing it as graph topology. Generic high-degree nodes
must not drive expansion without a specificity gate. A graph route is justified
only when it improves its intended causal, multi-hop, temporal, or topology
lane over hybrid retrieval without graph.

## Narrative Consolidation

The intended hierarchy is:

```text
event or fact
  -> episode
  -> topic or phase
  -> session / project / quest narrative
```

Narrative consolidation should occur after quiescence or another proved
trigger, not after every raw event. Global queries should use lazy, bounded,
iterative deepening. Full community expansion is not the default route.

A narrative may compress many episodes, but it must retain episode and raw
refs, conflicts, exclusions, and validity limits. It must not promote
unreviewed experience into doctrine.

## Freshness and Orchestration

Automatic update is part of the architecture, not a collection of timers.

Each projection should expose:

- schema and producer version;
- source epoch or fingerprint;
- processed watermark;
- dependency state;
- last successful semantic update;
- current freshness state;
- deferred, blocked, failed, and retry information.

Projection dependencies should propagate dirty state from capture through
segmentation, indexes, episodes, search, graph, and narrative layers.
Incremental workers should be idempotent, bounded, restartable, and safe under
concurrent readers.

Active sessions need quiet-window/debounce behavior. Resource-heavy work needs
backpressure, bounded retry, priority, and starvation visibility. A timer or
systemd success proves only that a launcher ran; it does not prove semantic
freshness.

The query plane must distinguish:

- `current`;
- `stale-readable`;
- `deferred`;
- `blocked`;
- `failed`;
- `truncated`;
- `fallback`;
- `unresolved`.

Manual maintenance is a recovery and operator route, not the intended hidden
happy path.

## Access Plane

CLI commands, skills, indexes, and MCP expose access to the organ. They do not
become evidence or proof authorities.

The current MCP contract is read-only and plan-only. It may return typed route
packets, freshness, refs, budgets, and next commands. Mutating maintenance,
repair, promotion, and owner decisions remain behind explicit owner commands
and review gates.

Agent-facing packets should be small enough for active context and should
prefer refs and expansion routes over copied transcript bodies. The detailed
agent access contract lives in `DESIGN.AGENTS.md`.

## Portability and Adapters

The portable core should not require a particular workspace, operator, model
provider, host cache, or AoA deployment.

An adapter may provide:

- session/run identity;
- event and actor mapping;
- transcript or evidence source;
- lifecycle and compaction markers;
- tool/correlation metadata;
- model/runtime metadata;
- capture and recovery hooks.

The adapter must not weaken the common evidence, provenance, freshness, and
privacy contract.

Codex-specific hooks and grounding belong to the Codex adapter and operational
docs. Other runtimes may have no compaction hooks or may produce different
evidence streams.

Portable source and installed runtime state are distinct. Generated bundles
must be produced through the owner export route and must exclude private raw
sessions, runtime databases, diagnostics, secrets, and host-only state by
default.

## Experience Metabolism

The organ should make this path possible without shortcutting it:

```text
thought or intent
  -> task
  -> action
  -> artifact or observation
  -> evaluation
  -> revised understanding
  -> skill / automation / dataset / training candidate
  -> changed agent
  -> new experience
```

Each arrow is a typed, evidence-bearing transformation, not a loose semantic
association.

Raw experience may produce candidates. Repeated experience may justify an
eval. An eval may justify a skill or automation change. A reviewed corpus and
model-development owner may justify training. None of those transitions is
automatic.

Training-oriented exports, when they exist, must preserve provenance,
selection criteria, privacy and licensing posture, model/runtime lineage,
negative examples, rejected hypotheses, and eval results. The memory organ may
prepare evidence-backed datasets; it is not the trainer or the authority that a
model became better.

Cross-model continuity should come from portable, inspectable memory and
lineage, not from pretending successive models are the same process.

## Quality and Proof

Quality is multi-dimensional:

- retrieval: exact recall, semantic coverage, ranking, omissions, duplicates,
  and false neighbors;
- relationships: edge/path precision, temporal order, causality, and
  supersession;
- reading: evidence completeness, contradiction handling, abstention, and
  unsupported claims;
- system: freshness, idempotency, recovery, version coherence, and parity;
- resources: latency, context cost, storage, cardinality, update cost, and
  headroom.

Formal tests are necessary for mechanical invariants such as schema validity,
ref resolution, deterministic serialization, idempotency, bounded budgets, and
portable parity.

Semantic correctness requires manual evidence review on real sessions,
including negative, collision, temporal, causal, multilingual, randomized, and
insufficient-evidence cases. Stable failures discovered manually may become
minimal regression tests or eval cases afterward. One aggregate score or one
LLM judge is not sufficient proof.

An architectural change should be compared against the same evidence corpus,
versions, freshness, and budgets. A mean improvement must not hide a critical
exact-recall, provenance, freshness, or abstention regression.

The organ should eventually be able to recover the meaningful trajectory of
its own development through independent exact, episode, temporal, entity, and
causal routes. Failure of self-provenance is a system defect, not merely a
documentation gap.

## Resource and Storage Law

Preservation and projection have different storage obligations.

Protected raw evidence may be expensive. Generated projections should earn
their weight through measured query value. Cardinality, duplicate payloads,
WAL growth, latency, and context cost must stay observable.

Do not prune a projection merely because it is large. First prove a replacement
with:

- equal or better quality in its intended lanes;
- resolvable evidence refs;
- freshness and fallback;
- bounded cost;
- rebuild and rollback;
- before/after cardinality and storage;
- repeated manual verification after cleanup.

An “aggregate” that increases rows or duplicates another complete
representation is not a successful aggregation.

## Privacy, Security, and Retention

Raw sessions may contain private prompts, paths, outputs, identities, or
secrets. Access and export must follow least exposure:

- portable bundles exclude private session material by default;
- diagnostics and accounting avoid raw prompt/text leakage;
- packet previews are bounded and purpose-specific;
- derived training or sharing requires explicit review and sanitization;
- deletion, redaction, and retention operations are typed and auditable;
- a redacted projection must not silently pretend the protected raw source was
  rewritten.

## Healthy Design

The organ is healthy when:

- sessions survive compaction and runtime boundaries;
- agents find exact evidence without loading the archive;
- semantic retrieval resists boilerplate and false correlation;
- episodes reconstruct intent, action, result, and verification;
- graph relations improve the lanes they serve;
- stale state is visible and automatically catches up;
- every important claim resolves to evidence;
- owner terrain receives only reviewed durable truth;
- the portable core remains useful beyond one runtime.

The organ is unhealthy when:

- summaries replace evidence;
- Codex-specific mechanics define the whole identity;
- generated projections masquerade as truth;
- mention becomes usage or causality;
- freshness depends on an undocumented manual command;
- graph or search weight grows without measured value;
- session experiments become permanent repository clutter;
- experience jumps directly into skills, automation, or training;
- current owners are overridden by historical memory.

## Enduring Laws

```text
Preserve evidence.
Keep identity stable.
Project without replacing.
Retrieve by intent.
Read before claiming.
Expose freshness and uncertainty.
Review before promotion.
Let experience grow capability only through proof.
```
