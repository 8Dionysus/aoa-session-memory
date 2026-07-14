# AoA Session Memory Agent Access Contract

## Role

`DESIGN.AGENTS.md` defines how an agent should enter, query, inspect, and
leave the session-memory organ without flattening evidence layers or spending
unbounded context.

The filename is retained as a portable compatibility surface. It is not a
second root instruction file and it does not duplicate `AGENTS.md`.

This file owns:

- context-loading and progressive-disclosure law;
- query-intent routing;
- evidence-packet shape;
- bounded escalation and abstention;
- freshness and fallback presentation;
- the boundary between read access and mutation.

Architecture belongs to `DESIGN.md`. Commands and recovery procedures belong
to `PIPELINE.md`. Naming belongs to `NAMING.md`. Current status belongs to
live diagnostics.

## Agent Access Thesis

An agent should receive the smallest evidence-bearing packet that can answer
the question or name the next honest expansion.

More context is not automatically better. A useful access surface:

- begins from the user's actual intent;
- selects the cheapest sufficiently specific route;
- keeps provenance and freshness visible;
- distinguishes navigation from proof;
- expands only when the current packet is insufficient;
- stops rather than filling the gap with a plausible neighbor.

The organ should give the agent a map and resolvable coordinates, not an
instruction wall or copied archive.

## Context Loading Law

Always-loaded guidance should remain small. Deeper surfaces are loaded
just-in-time.

Use this order:

1. Read the nearest `AGENTS.md`.
2. Classify the task.
3. Open only the owning design, operation, naming, install, or readiness
   surface.
4. Use generated indexes or a typed query route to choose evidence.
5. Open bounded segment/raw material only when the packet cannot establish the
   required claim.

Do not read all root docs, all session indexes, or a whole transcript as a
default orientation ritual.

## Route by Question

| Question shape | First route |
| --- | --- |
| Exact path, UUID, command, flag, error, phrase, date, or identifier | exact/literal planner and bounded lexical route |
| Does an entity exist and where is it registered? | typed entity registry |
| Was an entity mentioned, selected, invoked, used, or consequential? | typed usage chain with state distinctions |
| What did the agent answer or report? | agent-event response/closeout route |
| What happened during one task? | task episode |
| What happened before or after an event? | bounded neighborhood or timeline |
| What was true then or is valid now? | temporal/validity route with supersession |
| What caused, resolved, or verified an outcome? | action-result episode, then causal graph if needed |
| How are two specific entities connected? | exact anchors, then bounded graph bridge |
| What pattern recurred across sessions or projects? | lazy narrative/global route over episodes |
| Is a projection current or why is it delayed? | projection or maintenance status |
| What does a committed portable statistic measure? | `stats/` manifest, revision packet, and referenced source corpus |
| Is there enough evidence to answer? | evidence-reading and abstention route |

If the query is ambiguous, expose the competing interpretations or ask for a
narrower anchor. Do not silently choose the broadest and most expensive route.

## Typed Authority Route

The correct next surface depends on the claim:

- session occurrence: raw/segment/session evidence;
- current repository behavior: the repository owner;
- evaluation verdict: the eval owner;
- skill meaning: the skill source;
- runtime health: live runtime evidence;
- revision-bound portable fixture coverage: the owner-local stats packet and
  its source refs, never a live-readiness inference;
- architecture: the current owner design/decision surface;
- navigation: generated session-memory projections.

Session memory may locate an owner surface. It must not answer an owner-truth
question from historical session evidence alone.

## Evidence Packet Contract

Every agent-facing packet should expose, when applicable:

- normalized query intent;
- selected route and why it was selected;
- projection, schema, model, and classifier versions;
- source epoch, watermark, or fingerprint;
- freshness state;
- result and expansion budgets;
- candidate evidence with stable IDs;
- raw, segment, session, receipt, or external owner refs;
- confidence and uncertainty;
- truncation, omission, fallback, and timeout state;
- conflicts, supersession, and rejected correlations;
- exact next expansion command or route;
- an explicit insufficiency reason when no supported answer exists.

A preview without a resolvable ref is orientation only. A packet without
freshness cannot claim to represent current state.

## Bounded Escalation

Escalation should be monotonic in cost and explicit in purpose:

```text
typed identity or exact anchor
  -> typed postings / exact lexical
  -> episode or bounded neighborhood
  -> semantic/hybrid candidates
  -> typed graph expansion
  -> lazy narrative/global consolidation
  -> bounded raw verification
```

This is a routing shape, not a mandatory pipeline. A query may enter at a later
stage when its intent requires it, but it should not pay for unrelated stages.

Each escalation must say what evidence was missing from the previous packet.
Stop escalation when:

- the supported claim is already established;
- the budget is exhausted;
- additional candidates add only duplicates or generic neighbors;
- freshness is too weak;
- the required owner or raw evidence is unavailable.

## Entity Usage Semantics

Agents must keep the following states distinct:

```text
registered
mentioned
prompt-visible
selected
loaded
read
procedure-observed
invoked
completed
verified
consequence-producing
failed
deflected
```

Not every producer can prove every state. A loaded skill payload proves that
the payload was present, not that the model read or followed it. A tool name in
system instructions proves visibility, not use. An adjacent result with a
different correlation ID is context, not consequence.

Packets may expose candidate states and blocked claims. They must not collapse
those states into one generic “used” count.

## Source-Aware Reading

Text source is part of meaning.

Agents should distinguish:

- user intent and correction;
- assistant final answer;
- assistant progress or analysis boundary;
- structured tool call;
- command and command output;
- structured result, error, or status;
- raw tool dump;
- system/developer instruction;
- loaded skill payload;
- repository documentation;
- generated summary or index text.

System instructions, skill bodies, and documentation can contain many
operational words without providing operational evidence. Structured identity,
correlation, status, action, and receipt evidence should outrank broad text
association.

## Episode Route

Use episodes when the question concerns a coherent piece of work rather than a
single token match.

A task episode should expose:

- initiating intent or correction;
- actions and tool/command refs;
- outcomes and errors;
- verification and closeout;
- unresolved branches;
- owner/work context;
- time span and evidence refs.

Episode packets are generated navigation. Open their refs before promoting a
decision, causal claim, lesson, or current-state statement.

## Graph Route

Start graph work from specific anchors obtained through exact or hybrid
retrieval. Prefer:

- a bridge between two known anchors;
- a bounded neighborhood;
- a temporal or causal path;
- a typed owner/dependency relation.

Every graph packet needs node, edge, time, evidence, and context budgets.
Generic high-degree nodes should not expand without a specificity gate.

Cooccurrence and mention edges are discovery hints. They are not causality,
usage, ownership, or consequence.

## Narrative and Global Route

Global questions should not broaden every local query.

Use a narrative route only for questions about recurring patterns, changing
decisions, phases, long arcs, or cross-session/project themes. Begin from
episodes or typed anchors, consolidate lazily, and retain exceptions and
evidence refs.

A narrative answer is incomplete if it cannot identify the episodes and
evidence that support its important claims.

## Freshness Presentation

Agents must preserve the difference between:

- `current`;
- `stale-readable`;
- `deferred`;
- `blocked`;
- `failed`;
- `truncated`;
- `fallback`;
- `unresolved`.

A stale-readable packet may still be useful for older evidence, but it cannot
answer “current” without a stronger fallback or an explicit caveat. A timer
success is not semantic freshness. A quiet-window defer is not corruption.

When a packet is stale, return the stable evidence that remains usable and the
narrowest catch-up or fallback route.

## MCP and Other Access Planes

MCP is an access plane, not proof authority.

The current session-memory MCP should remain read-only and plan-only. It may:

- expose typed searches and route packets;
- report projection freshness and maintenance needs;
- return bounded refs and expansion commands;
- compact payloads for agent context.

It must not:

- repair or rewrite session archives;
- run heavy maintenance as a hidden side effect;
- promote memory;
- decide another owner's truth;
- hide stale, truncated, or fallback state.

CLI, skill, and MCP routes should converge on the same underlying contracts even
when their presentation differs.

## Session-Local Navigation

After a session has been selected:

1. read the session-local route card and technical identity;
2. use the session index to select an episode, segment, or event class;
3. read the relevant segment index;
4. open bounded segment or raw evidence for exact verification.

Semantic names and generated summaries may orient the agent, but stable session
identity and evidence refs control the route.

## Read and Mutation Separation

Finding evidence does not authorize changing it.

Read routes may identify:

- stale projections;
- missing refs;
- candidate repairs;
- promotion candidates;
- possible owner surfaces.

Mutation requires the explicit owner command and its guards. Repair should
preserve historical evidence and produce a diagnostic. Promotion requires the
target owner's review. Generated/exported surfaces must be rebuilt from their
source owner.

## Agent Closeout

Closeout is a navigation handoff, not a permanent project diary.

Report:

- the real outcome;
- changed owner surfaces;
- checks and manual evidence inspected;
- generated/exported companions refreshed;
- skipped checks and remaining risk;
- the next owner route when work remains.

Detailed hypotheses, failed experiments, seeds, transient metrics, and
session-only reasoning remain in session provenance unless a reviewed durable
need justifies promotion.

## Design Principles

1. **Route before load.** Choose the lane before opening large context.
2. **Specific before broad.** Exact and typed anchors precede semantic or graph
   expansion.
3. **Evidence before synthesis.** Retrieval candidates are not claims.
4. **Source kind matters.** Boilerplate and tool dumps are not equivalent to
   intent, action, or verified result.
5. **Freshness is part of the answer.** Current, stale, deferred, and fallback
   cannot be presentation details.
6. **Refs survive compression.** Every useful higher layer keeps a path back
   down.
7. **Unknown is a valid result.** Nearest embedding is not always an answer.
8. **Access does not confer authority.** MCP, indexes, graphs, and narratives
   help agents navigate; owners decide truth and mutation.
