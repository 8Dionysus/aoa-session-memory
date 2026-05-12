# AoA Session Memory Design

## Role

`DESIGN.md` defines the operating form of the `.aoa` session-memory kernel.

It is not the implementation manual, naming table, schema reference, or
distillation report. It answers one question:

What shape must this memory system preserve as it grows?

Agents should read this file immediately after `AGENTS.md` when working inside
`.aoa`.

## Design Thesis

`.aoa` exists because a Codex session is not true memory.

A long agent session can overflow, compact too early, compact too late, or
survive only as a summary of a summary. In those states, the agent may remember
the mood of the work while losing the evidence, commands, false starts,
decisions, and exact boundaries that made the work real.

The answer is not to force everything into active context.

The answer is to make memory external, addressable, indexed, recoverable, and
reviewable.

The originating idea is simple: a large context window is a cargo bay, not a
memory system. It can carry more for a while, but it still has failure modes:
overflow, premature compaction, late compaction, lossy summaries, and lost
evidence. `.aoa` exists so the work survives those modes without asking active
context to become an archive.

## Design as Physiology

Treat the Codex context window as working memory, not as the archive.

- Context is attention.
- Raw transcript is the black box.
- Compaction boundaries are natural memory intervals.
- Segment Markdown is the readable flight recorder.
- Segment index is the local event map.
- Session index is the atlas.
- Distillation is later reviewed metabolism.
- Skills and automation are mature organs, not raw memory.

The system should not pretend that compaction is a bug to ignore. Compaction is
a physiological boundary. `.aoa` uses that boundary as a memory coordinate.

## Names as Topology

Names are not decoration here. They are the first map an agent sees.

Every durable name should tell the agent what kind of thing it is, when it
belongs, and where it sits in the archive. Date, day-local sequence, short
title, segment role, event type, and status are routing signals. A good agent
will still inspect the evidence, but a good name reduces the chance that the
first move is already wrong.

Avoid vague durable names because they create false topology:

```text
misc
tmp
old
new
unknown
dump
```

Use explicit unresolved names when truth is missing. Do not hide uncertainty
behind a vague label.

## Core Shape

The durable unit is a session archive:

```text
sessions/
  YYYY-MM-DD__NNN__short-title/
    AGENTS.md
    SESSION.md
    session.manifest.json
    session.index.json
    hooks/
    raw/
    segments/
    incidents/
    distillation/
```

The intended segment unit is one Markdown artifact per compaction interval:

```text
initial-to-compaction
compaction-to-compaction
compaction-to-latest
initial-to-latest
```

When no compaction has happened yet, `initial-to-latest` is the correct segment
role. When compaction boundaries exist, they become the archive boundaries.

## Preservation Before Intelligence

The first duty is preservation.

Do not summarize away material by default. Raw mistakes, failed commands,
unhelpful searches, wrong assumptions, repeated attempts, and noisy tool output
are not waste at the archive layer. They are ore for later process improvement.

The archive layer answers:

Did we keep the material?

The index layer answers:

Can we find the material?

The diagnostic layer answers:

Why did preservation fail?

The distillation layer answers:

What became experience?

The skill and automation layers answer:

What matured into repeatable action?

Do not collapse these layers.

## Raw Truth and Reviewed Truth

Raw JSONL is evidence, not final truth.

Generated Markdown segments are readable evidence, not final truth.

Indexes are maps, not final truth.

Distillation notes are provisional until reviewed.

Patterns, skills, and automation may only become durable authority after a
reviewed distillation path.

This distinction is the main safety rail of `.aoa`.

## Indexing Philosophy

Indexing is not decoration. It is the memory system's attention model.

Every archived segment should be navigable by stable event types, tags,
importance, anchors, and raw references. An agent should be able to ask:

- where are the decisions?
- where are the commands?
- where are the failures?
- where are the dead branches?
- where are the process lessons?
- where is the latest final state?
- what should be rehydrated first?

The answer should be in indexes before the agent opens large raw or segment
files.

## Event Metabolism

Every event may become experience.

Every repeated experience may become a pattern.

Every reviewed pattern may become a skill.

Every stable skill may become automation.

Every automation must remain inspectable.

The event taxonomy and distillation routes exist for this reason. A `COMMAND`
may become a safe runner pattern. An `ERROR` may become a preflight check. A
`DEAD_BRANCH` may become a routing rule. A `DECISION` may become an
architecture principle. A `PROCESS_LESSON` may become a skill amendment.

Nothing should jump directly from raw event to automation without review.

## Diagnostics, Not Panic Memory

If raw session material is unavailable, do not normalize the failure by writing
a vague panic packet and moving on.

Raw-unavailable is an infrastructure incident.

The correct response is diagnostic:

- where was the raw transcript expected?
- did the path exist?
- was it readable?
- which `session_id` was active?
- which hook fired?
- which working directory invoked it?
- are there alternative transcript candidates?
- was the session rotated, moved, compacted, or deleted?
- what recovery action is safe?

Write the incident. Write the diagnostic JSON. Keep the failure visible so the
capture system improves.

## Hooks and Skills

Hooks are the capture reflex. Skills are the conscious recovery and refinement
route.

Hooks should be minimal, schema-valid, fail-open, and biased toward preserving
or refreshing evidence. They must not perform heavy interpretation inside the
active Codex lifecycle unless the operator deliberately enables that mode.

Skills should handle the work that benefits from deliberate attention:

- manually rebuilding an archive from raw JSONL
- rehydrating a session from indexes
- diagnosing raw-unavailable failures
- running first-pass distillation
- promoting reviewed lessons toward patterns, skills, or automation

The design uses both because neither is enough alone. A hook catches the
moment. A skill lets an agent return, inspect, repair, and improve the system
without pretending the hook already understood the work.

## Agent Entry Route

When an agent enters `.aoa`, it should proceed in this order:

1. Read nearest `AGENTS.md`.
2. Read this `DESIGN.md`.
3. Read `README.md` for current implementation shape.
4. Read `NAMING.md` before touching paths or generated names.
5. Read `session-registry.json` before choosing a session.
6. Inside a session, read `AGENTS.md`, then `SESSION.md`, then
   `session.manifest.json`.
7. Read the relevant segment index before opening a full segment.
8. Use raw JSONL only to verify, recover, or inspect exact evidence.

This route keeps the agent from eating the whole archive when it only needs a
map.

## Design as Portability

`.aoa` must remain a portable kernel.

Local Agents of Abyss, Tree of Sophia, AbyssOS, and operator-specific meaning
may overlay it, but the kernel should not require those meanings to function.

The portable kernel owns:

- capture shape
- archive structure
- naming law
- event taxonomy
- indexes
- diagnostics
- rehydration route
- distillation hooks and statuses

Local overlays own:

- project doctrine
- repository-specific meanings
- local quest, checkpoint, role, and runtime state
- local organ relationships
- private operator context

Keep this boundary clean so the bundle can later move to its own repository.

## Design as AoA Organ

In AoA terms, `.aoa` is not the city center and not the whole operating system.

It is a memory organ.

It helps the wider system survive long work, return to evidence, metabolize
experience, and grow better processes. It should cooperate with skills, hooks,
playbooks, evals, routing, and runtime layers without stealing their authority.

The organ is healthy when it preserves, indexes, diagnoses, and routes.

It is unhealthy when it claims to know, judge, promote, or automate without the
review path that belongs to another layer.

## Good Design Feels Like

A new agent can find the archive.

A tired agent can rehydrate without rereading everything.

A human can inspect why a claim exists.

A session can survive compaction without losing its raw trail.

A failure becomes a diagnostic artifact, not a silent gap.

A repeated lesson has a path toward a skill.

A future repository can adopt the bundle without inheriting local doctrine.

## Bad Design Smells Like

- raw deletion as cleanup
- giant unindexed Markdown dumps
- summaries replacing evidence
- vague names such as `misc`, `tmp`, `old`, or `unknown`
- hooks that block normal work by accident
- generated artifacts treated as reviewed authority
- incidents hidden as normal resume notes
- distillation mixed into preservation
- local AoA doctrine hardcoded into the portable kernel
- automation born directly from unreviewed raw events

## Stop Lines

Do not make `.aoa` clever before it is reliable.

Do not make it authoritative before it is reviewed.

Do not make it local-only before it is portable.

Do not let agents confuse memory with judgment.

Do not let compaction erase process history.

The enduring law is:

```text
Preserve first.
Index aggressively.
Diagnose failures.
Distill later.
Promote only through review.
Automate only when inspectable.
```
