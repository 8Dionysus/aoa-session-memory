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

Capture and indexing advance independently. When bounded foreground work
cannot publish a complete session generation, it preserves a content-addressed
raw snapshot and atomically advances `raw/capture.latest.json`. A capture ahead
of the indexed digest makes dependent answer projections stale; it does not
replace the last-good `raw/session.raw.jsonl`, manifest, segments, or indexes.
Repeated capture of identical bytes is idempotent. Operational hook
observations remain outside the semantic projection.

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

When raw metadata declares a fork, the manifest also records the parent and the
structural child-work boundary. Replayed pre-boundary material stays preserved
in raw evidence but is scoped separately from local fork work in task episodes.
An adapter bootstrap immediately before `task_started` is a transport
coordinate, not a delegated intent. The structured child task-start begins the
local scope but contributes no task semantics by itself. A parsed inter-agent
`NEW_TASK` envelope may contribute the initiating intent; unavailable or
encrypted task content remains explicitly unavailable. Repeated envelopes may
share one episode only while its lifecycle is open and must not overwrite the
first admitted initiating delegation ref. `task_complete` closes that
lifecycle; a later `task_started` opens a new structural episode whose
`NEW_TASK` supplies intent. Without that coordinate, a post-terminal
`NEW_TASK` is the bounded new-lifecycle fallback. Matching transport names do
not prove semantic replay.
Retrieval may consolidate it with an unambiguous parent episode only after an
exact relevant-evidence comparison, and must retain both physical routes.

The repository registry and archive indexes point to sessions. They do not
replace the per-session manifest or raw evidence.

Session raw, blocks, segment Markdown and indexes, manifest, session index, and
indexed capture state publish as one validated file generation. Readers abstain
while its publish journal exists. An interrupted replacement restores the
complete prior generation and removes its stage and backup; it never repairs a
mixed tree in place. Physical raw-block compression and confirmed plaintext
removal use the same boundary while keeping stable evidence refs.

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

For a supported exact query scoped to one archived session, an insufficient or
timed-out projected result may fall back to a bounded read of that session's
raw JSONL before broader raw-text search. The pass writes no index and computes
the manifest digest while scanning. Only a complete digest-verified pass can
prove absence; partial or unverifiable scans must expose that state. The live
append-only tail remains a separate freshness route.

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
or effectiveness. When a caller supplies one session and structured dispatch
evidence is absent, the usage route may lazily read only the bounded initial
developer/system context and admit an exact `### Available skills` entry as
`prompt-visible` context. It writes no posting, never becomes usage, and keeps
negative claims blocked when the bounded raw probe is incomplete.

## 10. Freshness and live tails

Projection freshness compares source fingerprints, schema versions, and
generated state. Recently changing live transcripts are deferred through a
quiet-window posture. A stable older projection may remain usable while the
latest live tail is explicitly unavailable for current claims.

Episode semantic state, entity postings, their repair queue, and the optional
dense sidecar persist the route-signal classifier epoch that generated them.
An epoch change makes those projections dirty even when the raw fingerprint
and document count did not move. Queue seeding resets an exhausted old-epoch
attempt so automatic maintenance can rebuild it instead of preserving a
terminal retry state from a superseded classifier.

Per-session physical entity-posting counts use an independent metadata version.
Bounded automatic maintenance may reconcile those watermarks from existing
current-epoch postings without reparsing raw transcripts or rebuilding episode
documents. Cardinality replacement proof remains partial until both these
watermarks and the operational route rollup are current.

Deferred live state is not silently green and is not stable corruption. The
next route is either to wait for quiet, run a targeted catch-up, or inspect raw
evidence directly when authorized.

Graph readers expose global recall freshness and bounded returned-evidence
freshness as separate axes. Returned evidence-bearing nodes and edges are
mapped through their source contributions, then checked against store
generation identity, source fingerprints, and the source-state ledger. A clean
bounded scope never makes a stale global graph current; missing, truncated, or
unverified contributor coverage never becomes `scope_current`. When a compact
timeline is selected from a wider neighborhood, both scope states remain
visible.

## 11. Maintenance coordination

All generated writers share a maintenance lease and coordinator packet. Hot,
backlog, catch-up, deep, and manual-bulk profiles represent different resource
and mutation envelopes. Timer-driven work yields to active owners and records
resource-pressure deferrals.

Timer-originated `auto-maintenance-resource` deferrals are also written to the
generated persistent retry queue under `diagnostics/`. The
`auto-maintenance-retry` dispatcher consumes at most a bounded number of due
items, deduplicates by profile and target, applies exponential backoff, recovers
an interrupted in-flight claim after dispatcher restart, and stops after the
profile retry limit. A later successful periodic or retry launch clears the
pending intent. Manual operator launches do not silently create background
work. A host scheduler may invoke the portable dispatcher, but the queue and
retry semantics remain owned by this organ; scheduled retry is not semantic
maintenance success.

Due retry items are ordered by a versioned profile-aware dispatch deadline,
not by retry-ready time alone. Short hot and catch-up wait targets bound urgent
latency. Once a backlog or deep target is breached, one earliest breached
heavy item receives the first selection slot, after which ordinary deadline
order continues. This reservation prevents an overloaded short-work stream
from permanently displacing heavy work; it bounds queue selection only when
the dispatcher receives execution opportunities and does not invent host
capacity or semantic progress. Automatic profiles also use a cooperative work
budget distinct from the longer host launcher timeout; explicit overrides
remain visible. Queue and status packets expose the policy version, order,
deadlines, breaches, fairness reservation, and selected item. These scheduling
signals do not make a projection current.

Observed query demand is a bounded scheduling input, not evidence authority.
An automatic scoped profile may prepend only the configured bounded set of
demanded archive sessions that fell outside its normal date or count window.
An applying graph queue consumer may likewise top up actionable demanded
sources from the generated ledger even while the queue is nonempty, but only
to one batch-sized reserve and counting entries already queued. Reports retain
the original scope, added targets, queue top-up, remaining work, and freshness;
the demand signal never makes a projection current by itself.

Resource-blocked all-session graph fallback also maintains a separate bounded
background candidate reserve. Existing entries count toward the reserve, and
only the missing count is admitted from the generated ledger before ordinary
priority and refresh-cost selection. An individually oversized source remains
queued for a compatible heavy route but cannot prevent cheaper sources from
entering the candidate window. A child process that exits successfully without
advancing any actionable source while work remains reports a retryable
`resource_blocked_graph_drip_no_progress`, not completion. Reports expose the
existing queue count, reserve, requested top-up, progress, and remaining work.

Conversely, a child may commit bounded mutations and then return deferred or
budget-exhausted. Explicit allowlisted mutation counters in the action result
admit only that bounded progress; generic processed, current, attempted,
selected, or skipped counts do not. The wrapper must preserve both facts:
mutation occurred and remaining work needs a persistent retry. Neither the
child exit code nor the outer action status may erase an explicit mutation
receipt or promote partial work to global freshness.

Incremental maintenance repairs only dirty source contributions when possible.
Missing schemas, corrupt stores, or large policy migrations route to explicit
rebuilds. Interrupted generated-store temporary files are cleanup candidates;
raw evidence is not.

A search schema mismatch is incremental only for an owner-declared additive
version pair whose live store still has documents, route indexes, route terms,
and no structural schema diagnostic. The first committed dirty-session repair
may advance the store epoch; every untouched session remains dirty until its
own projection state is regenerated. Both outer preflight and the inner index
planner use this same transition contract; a bounded automatic profile must
not silently reinterpret an admitted incremental transition as a PID-local
full rebuild. Unknown or structurally incomplete transitions keep the
deep/full-rebuild boundary.

`maintenance-cleanup` recognizes PID-tagged graph and search rebuild temps,
removes only those whose producer PID is absent while holding the shared
maintenance lease, and leaves live stores and raw evidence untouched. An
active writer defers cleanup rather than racing publication.

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
