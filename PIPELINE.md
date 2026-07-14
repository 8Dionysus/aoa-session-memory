# Session-memory pipeline

This document owns the durable flow of the portable session-memory kernel. It
describes what each stage means and where authority remains. Exact command
syntax belongs to `scripts/aoa_session_memory.py` and its subcommand help.

## Codex adapter grounding

Codex is the current production adapter, not the identity boundary of the
organ. Its hook schema, model context, compaction behavior, and local
configuration may change independently of this pipeline.

Before relying on that adapter, `codex-grounding` observes the installed Codex
contract. Context-window and auto-compaction values may come from explicit
configuration or from the selected model defaults resolved through
`codex debug models`; grounding validates the effective contract rather than
requiring manual overrides. Repeat grounding and live hook proof after an
adapter or runtime change.

## 1. Intake

Codex lifecycle hooks and explicit import routes identify a transcript and its
workspace. The intake boundary records the stable session id, source location,
hook event, and diagnostic posture without assuming the transcript is complete
or readable.

Foreground hooks are bounded and fail-open. A hook failure produces a receipt
or incident that later recovery can inspect; it does not make the active agent
session depend on archive health.

## 2. Raw preservation

Readable source JSONL is mirrored into the local archive before semantic
processing. Source metadata records origin, size, line count, and digest.
Missing or unreadable raw material remains an explicit diagnostic state.

Raw preservation is append-oriented. Repair may regenerate derived material,
but ordinary cleanup never deletes raw session evidence.

## 3. Compaction boundaries and blocks

Native compaction markers divide a transcript into ordered intervals. The raw
block ledger and compaction-event ledger preserve that topology independently
of rendered Markdown. Open intervals remain open until later source evidence
closes them.

`PostCompact` normally queues interval sealing. Large or busy sessions may
defer work to the worker path; a later sweep or maintenance pass closes the
same evidence gap without inventing a boundary.

## 4. Readable segments

Every raw interval produces a readable segment and a sibling machine index.
The segment is for review; the index is for routing. Both point back to raw
line or block refs.

Segment generation may classify event type, conversation act, session act,
agent event, task episode, route signals, relationships, and token counts.
These are deterministic projections and remain weaker than raw evidence and
later reviewed owner records.

## 5. Session assembly

The session manifest records archive identity, source state, segment topology,
hook receipts, accounting summaries, and generated-version posture. The
session index supplies bounded navigation across segments, task episodes,
agent events, goals, decisions, errors, and open threads.

The repository registry and archive indexes point to sessions. They do not
replace the per-session manifest or raw evidence.

## 6. Count-only accounting

Token observations are separated by basis:

- `provider_reported` for provider usage fields;
- `exact_tokenizer` for a named deterministic tokenizer;
- `estimated` for the local estimator;
- `unknown` when no supported basis exists.

Aggregates retain basis counts and totals. No aggregation may merge an
estimate into provider-reported or exact usage. Accounting stores counts and
refs only; it excludes prompt text, raw text, transcript paths, session titles,
and tokenizer payloads.

## 7. Route projections

Segment and session indexes feed several generated projections:

- typed agent answers, closeouts, progress updates, and reasoning boundaries;
- task episodes and goal lifecycle observations;
- route-signal and entity registries;
- portable search and optional monthly structured shards;
- atlas entries;
- graph source contributions and aggregate topology;
- operational route and direct-event rollups.

Every projection reports freshness and retains a route back to session,
segment, raw, or receipt evidence. Generated rows may be rebuilt after
classifier or schema changes.

## 8. Consumer routing

Consumers should start with the cheapest typed route that matches the
question. Exact identities and structured filters precede broad text search.
Materialized rollups precede shard resampling. Graph packets are used for
bounded topology, not for evidence-free conclusions. Raw or segment expansion
is the final authority route when a claim matters.

Search results, graph paths, atlas entries, registry states, and scenario
checks are navigation packets. They may expose useful counts or confidence,
but they do not become reviewed memory, eval verdicts, or owner decisions.

## 9. Correlation and candidate semantics

Tool results and consequences must match the source correlation when a
correlation id exists. Foreign parallel results remain visible as rejected
context with evidence refs and cannot enter an accepted consequence chain.

Skill evidence similarly keeps dispatch and behavior separate. Selection,
payload loading, file editing, validation, mention, and co-occurrence are
distinct states. The presence of skill text never proves procedure adherence
or effectiveness.

## 10. Freshness and live tails

Projection freshness compares source fingerprints, schema versions, and
generated state. Recently changing live transcripts are deferred through a
quiet-window posture. A stable older projection may remain usable while the
latest live tail is explicitly unavailable for current claims.

Deferred live state is not silently green and is not stable corruption. The
next route is either to wait for quiet, run a targeted catch-up, or inspect raw
evidence directly when authorized.

## 11. Maintenance coordination

All generated writers share a maintenance lease and coordinator packet. Hot,
backlog, catch-up, deep, and manual-bulk profiles represent different resource
and mutation envelopes. Timer-driven work yields to active owners and records
resource-pressure deferrals.

Incremental maintenance repairs only dirty source contributions when possible.
Missing schemas, corrupt stores, or large policy migrations route to explicit
rebuilds. Interrupted generated-store temporary files are cleanup candidates;
raw evidence is not.

## 12. Search and graph pressure

Storage diagnosis separates physical bytes, duplicate generated payload,
cardinality, and recall requirements. WAL checkpointing is distinct from row
reduction, database rebuilding, or physical compaction.

Search context-tail omission is permitted only where a current replacement
rollup preserves route refs and bounded recall fallbacks. Graph high-fanout
reduction requires equivalent evidence refs and query behavior before generated
rows can be removed. Neither route changes raw or segment authority.

## 13. Naming and review

Naming-readiness checks archive integrity and evidence coverage before labels
are proposed. Whole-session names, phase names, topics, and aliases are
different objects. Phase discovery remains provisional until a reviewed route
applies a label.

First-pass distillation and review waves create candidate packets. They are
append-only work queues, not promotion. Durable memory, skill, automation, and
policy changes return to their owning repositories.

## 14. Portable export and install

Portable export copies authored kernel files and source fixtures while
excluding runtime sessions by default. Installation renders workspace-local
hook paths, preserves an existing archive, and keeps optional host providers as
overlays rather than dependencies.

The standalone bundle and a workspace-local installation must validate from
the same source contracts. Host-local proofs, generated databases, diagnostics,
and user skill symlinks are never treated as portable package content.

## 15. Validation and audit

Validation checks deterministic source and generated invariants. Doctor checks
the health of a selected installation. Audit asks whether the larger objective
is grounded and may remain incomplete even when the kernel itself is healthy.
Live scenario checks retain executed, skipped, failed, and actionable-gap
counts separately.

The owner-local stats port derives only a revision-bound portability statistic
from the source-owned scenario corpus. It neither reads live archives nor turns
scenario coverage into memory quality or runtime readiness.

## Executable authority

The CLI parser and implementation in `scripts/aoa_session_memory.py` are the
single executable command authority. Procedural agent routes live in
`skills/*/SKILL.md`; short focused check entrypoints may appear in the nearest
`AGENTS.md`. This pipeline deliberately carries no copied command catalog.
