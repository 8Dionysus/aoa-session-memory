# AoA Session Memory

`aoa-session-memory` is the portable kernel that preserves agent-session
evidence and builds bounded navigation over it. A checkout can be used as a
standalone source bundle or installed as a workspace-local `.aoa/` root.

The kernel preserves before it interprets. Raw transcripts remain local
evidence; generated segments, indexes, search stores, graph stores, reports,
and statistics are weaker projections. Reviewed distillation is the only path
from session evidence toward durable memory, skills, automation, or doctrine.

## Evidence chain

```text
raw transcript
  -> raw compaction blocks and hook receipts
  -> readable compaction-interval segments
  -> segment and session indexes
  -> bounded search, atlas, entity, and graph projections
  -> evidence packets with raw and segment refs
  -> later reviewed distillation
```

The canonical archive directory is
`sessions/<date>__<sequence>__<short-title>/`. Stable transcript identity stays
in `session.manifest.json`; a readable directory label is navigation, not a
replacement identity.

## Source and runtime split

The repository contains the portable kernel:

- authored contracts under `config/`, `schemas/`, and `maps/`;
- hook and CLI implementation under `scripts/`;
- focused agent routes under `skills/`;
- portable hook examples under `hooks/`;
- package and trust metadata under `manifests/`;
- the owner-local statistical handoff under `stats/`;
- regression coverage under `tests/`.

A live `.aoa` installation additionally owns raw session archives, generated
indexes, search and graph databases, diagnostics, maintenance coordination,
and local hook receipts. Those runtime surfaces are not portable source and
must not be committed as owner truth.

## Capture and archive lifecycle

The supported Codex lifecycle events are `SessionStart`, `UserPromptSubmit`,
`PreCompact`, `PostCompact`, and `Stop`. Foreground hooks are fail-open and
bounded. They retain receipts and cheap transcript state, while expensive
archive, indexing, and graph work is queued for the worker path.

`PostCompact` is the ordinary interval-sealing route. `Stop` may finish a small
archive, but large transcripts defer heavy work. Import, sweep, sync, and
reindex operations are recovery routes for missed hooks, historical sessions,
or changed generated contracts; they are not competing authorities.

Each archived interval keeps both readable Markdown and a machine index. The
index classifies events, relationships, route signals, task episodes, agent
events, goal observations, and evidence refs without treating those
classifications as reviewed truth.

## Token accounting

Token accounting is count-only generated evidence. Provider-reported usage,
exact tokenizer counts, estimates, and unknown observations remain distinct.
Estimates never become exact usage facts, and accounting projections do not
carry prompt text, raw text, session titles, transcript paths, or token ids.

Host consumers may read generated summaries. They must not open raw
transcripts merely to obtain counts or write their own meaning back into the
archive.

## Navigation surfaces

The kernel offers several progressively more expensive navigation layers:

1. session and segment indexes for direct evidence routing;
2. typed agent-event, task-episode, goal, hook, and entity routes;
3. a portable SQLite search projection and optional structured shards;
4. a source-owned agent atlas under `maps/`;
5. graph neighborhoods, bridges, timelines, and GraphRAG packets;
6. raw or segment expansion when a claim needs stronger evidence.

Generated search and graph material is replaceable. It must carry freshness,
cost, and evidence-ref posture, and it must never outrank raw transcripts,
segment indexes, or reviewed owner records.

For skill-related evidence, selection, loading, editing, validation,
co-occurrence, and consequences are separate candidate states. A selected or
loaded skill is not automatically invoked or followed. Foreign correlation
results remain rejected context with refs rather than accepted consequences.

## Maintenance and pressure

Maintenance is coordinated so hooks, timers, and manual writers do not race.
Hot paths use bounded freshness gates; large search or graph repairs use
explicit resource-aware routes. Live transcripts within the quiet window are
deferred rather than misreported as stable corruption.

Search pressure and graph pressure are cardinality questions before they are
SQLite-compaction questions. Read models may omit or roll up generated rows
only after a replacement route preserves evidence refs, recall boundaries,
freshness, and a rollback path. Raw archives are never storage-cleanup
candidates.

## Review and naming

Naming and distillation are separate from capture. Naming-readiness first
checks evidence coverage and identity consistency. Phase discovery produces
open candidates; reviewed naming routes apply accepted labels without changing
raw identity.

First-pass and batch distillation classify review candidates. They do not
promote claims. Manual-review packets are append-only evidence queues, and
promotion belongs to the stronger owner named by the candidate.

## Portable installation

Export and install copy only the portable kernel unless session inclusion is
explicitly requested. Existing workspace sessions are preserved during a
kernel upgrade. Hook examples are regenerated with portable placeholders, and
user-level skill installation remains an explicit operator choice.

Exact operator syntax belongs to the executable CLI. Inspect the relevant
subcommand help in `scripts/aoa_session_memory.py`; use the matching route under
`skills/` when an agent needs a procedural workflow. Short repository checks
are listed only in the nearest `AGENTS.md`.

## Owner map

- `DESIGN.md` owns archive architecture and evidence boundaries.
- `DESIGN.AGENTS.md` owns agent-facing route and authority design.
- `PIPELINE.md` owns lifecycle and projection flow.
- `READINESS.md` owns the durable readiness model, not a host snapshot.
- `INSTALL.md` owns portability and installation semantics.
- `NAMING.md` owns session and phase naming semantics.
- `stats/` owns the local measurement question and central stats handoff.
- `scripts/aoa_session_memory.py` owns commands and runtime behavior.
- nearest `AGENTS.md` files own district-specific working guidance.

## Core rule

```text
Raw JSONL is evidence.
Segment Markdown is the readable archive.
Indexes and read models are navigation.
Statistics are bounded derived views.
Distillation is a later reviewed act.
```
