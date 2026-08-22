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

The generated Codex command first enters a small standard-library adapter. It
atomically persists the exact private hook bytes, byte count, digest, selected
roots, event kind, and signal count before returning schema-limited output.
Byte-identical global and project signals share one ingress identity; the count
and observation interval remain visible. Different bytes never coalesce. Queue
admission means durable pending capture, not an indexed or current archive.

Lifecycle ingress wakes one single-flight background process. That process
loads the full projection engine outside the foreground hook latency, verifies
the envelope, replays it through the ordinary owner handler, writes the normal
receipt, and drains bounded hook jobs under the shared maintenance lease. A
lease collision leaves ingress pending for the persistent retry dispatcher.
The synchronous owner path remains an environment-controlled rollback and an
enqueue failure attempts it before failing open.

When raw is unavailable, the lifecycle handler writes the incident, diagnostic,
session manifest, and minimal session-registry record synchronously during
replay but queues the derived name and directory indexes. Those indexes are
rebuildable navigation views; deferring them does not defer session visibility
or weaken the incident evidence.

Hook sync execution intent is coalesced by session and transcript across the
pending and deferred queues. A later lifecycle signal updates the one active
intent with the newest source snapshot while retaining the earliest queue time,
event names, reasons, and a total signal count. Legacy duplicates are moved to
the generated `superseded` receipt lane before one canonical job remains; they
are not executed repeatedly or discarded as if they never existed. A running
job may have one pending successor so source growth observed during execution
is not lost.

### Identity-bound validation telemetry

Validation-owner telemetry enters session memory only as a dedicated typed
receipt or an explicitly named structured capture facet. The generic hook does
not infer workload, candidate, source, environment, treatment, acceptance,
cache, resource, or trajectory identity from operation text. A capture facet is
kept lightweight; it does not make the hook a validation owner.

The post-hoc profiler may read generated indexes for correlated structured
call-to-result spans, but it retains missing, unknown, unobservable, and
excluded states and never reads transcript bodies to fill owner fields. An
external receipt is admitted only after digest, session, source, and declared
projection identities join to the exact expected context. A stale-readable
prefix remains explicitly stale and cannot enter a current comparison pair.

The resulting identity-bound packet is an evidence projection owned by
session-memory. Pair admission checks exact identity, reviewed trajectory,
correlation completeness, cache posture, resource posture, and currentness;
it emits no effect, causal, proof, evaluator, or acceptance verdict. Heavy
receipt production, reindex, and catch-up stay behind their owning resource and
resumability routes.

## 2. Raw preservation

Readable source JSONL is mirrored into the local archive before semantic
processing. Source metadata records origin, size, line count, and digest.
Missing or unreadable raw material remains an explicit diagnostic state.

Capture and indexing advance independently. When bounded foreground work
cannot publish a complete session generation, it appends only new bytes to
immutable content-addressed blocks, advances a hash-chained source epoch in
`raw/capture-ledger.json`, and atomically advances `raw/capture.latest.json` plus
`raw/live-tail.index.json`, a compact redacted
`raw/live-tail.postings.json` manifest, and bounded immutable posting revisions
under `raw/live-tail-postings/`.
New block bytes and the compatibility suffix are fsynced before the ledger
watermark is replaced and its parent directory is fsynced. A process crash
before that replacement leaves the old watermark authoritative; retry truncates
any uncommitted compatibility suffix and deterministically replays the delta.
Device/inode change, truncation, or a mismatch at
the last committed block opens a new epoch instead of splicing histories. A
capture ahead of the indexed digest makes dependent answer projections stale;
it does not replace the last-good `raw/session.raw.jsonl`, manifest, segments,
or indexes. Repeated capture of identical bytes is idempotent and reads no raw
payload. Operational hook observations remain outside the semantic projection.

The live-tail reader may use the persistent overlay only when its source
identity and captured size, ledger epoch and chain head, compatibility-view
size, last immutable block receipt, and archived-prefix attestation all match.
The postings frontier consumes only newly completed captured lines. Ordinary
append reads at most one open posting shard, writes an immutable replacement
revision or new shard, and publishes its compact manifest last. Each shard
persists safe tokens, a local inverted token-to-entry map, redacted previews,
typed fields, and exact byte ranges, and never persists raw line bodies or
reversible secret digests. Manifest Bloom filters reject irrelevant shards
without opening them. A positive posting hit intersects the selected local map,
then reads and reclassifies only the selected raw ranges before returning
evidence. An exact allowlisted schema-2 predecessor may be linked as a sealed
legacy shard; unknown predecessors fail closed. A newly recognized sensitive
literal re-sanitizes retained derived shards but reads no historical raw.
A first capture with a very large unprojected backlog bootstraps only a bounded
recent complete-line window. Capture-block newline receipts recover exact raw
line numbers with at most one bounded block read; the manifest records omitted
bytes and lines explicitly. Raw remains complete authority and stable
projection owns older navigation, so this window cannot support exhaustive
negative claims. Later appends continue from its exact frontier and do not
revisit the omitted prefix.
A miss falls back to bounded direct-source validation or remains unresolved;
it cannot support an exhaustive negative claim, and the overlay never upgrades
semantic projections by itself.

The capture ledger persists portable SHA-256 continuation state. Small epochs
derive it portably. On supported Linux hosts, a first large capture self-tests
the public OpenSSL `SHA256_CTX`, hashes during the required delta read, and
exports its block-aligned eight-word state into the same portable schema. It
persists no native object and no pending raw bytes; a later append rereads at
most 63 boundary bytes and hashes only the new tail. Native unavailability or
self-test failure falls back to the exact block chain and an explicitly
deferred conventional continuation. An already-required stable full scan may
migrate that older state by attesting an exact aligned continuation at the same
capture watermark. Hook-observed paths enter a bounded capture-watch frontier.
An ordinary hot timer reads this frontier and component-outbox readiness only;
it performs no archive discovery and no raw read for an unchanged watched
source. Catchup, deep, and audit remain the global reconciliation routes.
`capture-watch` exposes that same bounded frontier reconciliation as a
capture-only operator or timer route. It never discovers the archive or starts
stable projection work, so fresh evidence can advance ahead of historical debt.

Raw preservation is append-oriented. Repair may regenerate derived material,
but ordinary cleanup never deletes raw session evidence.

Stable indexing does not recopy an exact ledger-backed capture. It publishes
`append_only_capture_ledger_with_bounded_materialization_v1`, binding the
processed byte/line watermark, conventional raw digest, epoch, chain root, and
block count. Admission checks contiguous ledger coverage, content-addressed
block metadata, the frontier-block digest, capture materialization size, and
capture state. The stable manifest defines the readable upper bound when the
append-only materialization later grows. `raw/session.raw.jsonl` remains as a
last-good compatibility snapshot and is replaced only on the legacy or
non-attested monolithic fallback route.

## 3. Compaction boundaries and blocks

Native compaction markers divide a transcript into ordered intervals. The raw
block ledger and compaction-event ledger preserve that topology independently
of rendered Markdown. Open intervals remain open until later source evidence
closes them.

`PostCompact` normally queues interval sealing. Large or busy sessions may
defer work to the worker path; a later sweep or maintenance pass closes the
same evidence gap without inventing a boundary.

## 4. Readable segments

Every raw interval produces a sibling machine index and a compact readable
segment synopsis. The index is the default routing surface; both preserve raw
line or block refs. Full redacted event-body Markdown is materialized only for
one selected segment through `render-segment` or an explicit audit/export path,
and is stored separately under `segments/rendered/` with a render receipt.

Segment generation may classify event type, conversation act, session act,
agent event, task episode, route signals, relationships, and token counts.
These are deterministic projections and remain weaker than raw evidence and
later reviewed owner records.

The segment worker admits pre-redacted classification metadata only from an
exact generation-bound cache record whose raw block identity and artifact
receipt were verified. Fresh token observations derived from parsed raw are
redacted separately before joining that container, and contextual facet maps
still run through the established complete policy pass. A direct or unattested
writer uses the complete pass for the whole index. The admission optimization
belongs to the segment producer ABI and does not invalidate reusable
classification blocks.

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

The same journal commits a deterministic immutable component-delta outbox
record before the publication is marked complete. A pre-commit crash removes
that new record while restoring last-good. A committed journal is finalized,
not rolled back. Search, episode-semantic, entity, and graph consumer states
begin as queued or deferred and require a separate exact completion receipt.
Graph propagation queues the session contribution and only segment IDs whose
semantic component digest changed; it does not enqueue every sealed segment on
an ordinary tail append.

Exact search acknowledgement requires a committed changed-component search
generation. Episode semantic is acknowledged from the same per-session result
only for `current`, `no_task_episodes`, or `no_admitted_episode_text`. Entity
acknowledgement additionally requires that exact-search
receipt and a current registry route dependency. Graph acknowledgement requires
a successful mutation and a source-ledger entry carrying the exact outbox
publish identity. Other consumers remain pending until their own receipts are
proved.

`freshness-vector <session>` reports capture, live overlay, stable projection,
search, episode-semantic, entity, graph, returned-evidence, and global-recall
axes separately. A current positive live-tail result does not admit an
exhaustive negative search or a global-current claim.

Task episodes inside session assembly materialize as immutable
content-addressed shards under `session-index-shards/`. Each shard is redacted
under the ephemeral whole-session literal policy before persistence, and its
manifest binds episode-local source identity, task-episode generation, policy
versions, artifact and payload hashes, order, and the current projection
publish identity. Closed compatible shards remain reusable across an unrelated
tail append. A persisted builder frontier reuses the sealed compatible prefix
and replays only the final two boundary-adjacent episodes with the new tail.
Atomic validation reads and verifies the ordered shard payloads. The bounded
task-episode CLI/MCP route verifies and hydrates only the ordered shards needed
to satisfy its limit. Its receipt reports total versus hydrated components and
keeps global recall and negative claims false unless every selected session was
fully scanned. Full semantic-digest, audit, and projection consumers continue
to verify the whole component set. Other readers share the manifest-first
loader; `session.index.json` keeps aggregate metadata and an empty compatibility
field. A legacy index without component storage may still use its embedded
array.

Episode reduction derives semantic text once per event and reuses it across
admission checks, while ordered segment ranges use logarithmic lookup. Cold
shard publication performs one whole-session-literal redaction pass. A prior
shard comparison also performs one pass, then supplies that exact payload to
the worker for reuse or restamping instead of scanning it again. Any missing
payload proof falls back to worker redaction; persistent shard contents and
privacy policy are unchanged.

Credential matchers retain their exact admitting expressions; cheap
necessary-marker prefilters skip only matchers that cannot possibly match the
current text, while opaque-credential detection remains unconditional.

Sibling session-projection stages name their producer PID before a publish
journal exists. If that process terminates during construction, maintenance may
remove the generated stage only after the PID is absent, while holding the
shared lease, and after any staged raw copy matches either published owner raw
or its resolvable external source. A legacy stage without producer identity is
not guessed away: its reported content digest and quiet-age guard require
explicit operator confirmation in addition to the raw-authority proof. Any
journal-bearing stage remains owned by journal recovery.

A complete PID-owned orphan may instead be recovered without a full reindex
through `session-stage-promote`. The dry-run binds one exact direct-child stage
and reports its content digest. Apply requires that digest, a still-absent
producer and journal, full projection-generation validation, and monotonic raw
proof: published owner raw is a byte prefix of staged raw, which is a byte
prefix of the resolvable live source. Publication uses the normal atomic
last-good boundary, refreshes the registry, and marks search and graph dirty;
it does not claim either derived projection is fresh.

A long session rebuild uses a sibling content-addressed
`.projection-work-<work-id>` directory rather than one disposable stage. Its
umbrella identity binds raw publication and atomic-publication contracts only.
Independent stage checkpoints bind capture, classification, correlation
summaries, segment index, review rendering, task episodes, goal lifecycles, and
the session component manifest to their exact upstream stage identities and
local contracts. Completed raw blocks and segments carry size-and-SHA receipts.
The ordinary append lane admits an exact records-root/component identity plus
size/mtime attestation and relinks the immutable file without opening it;
periodic `doctor --deep-projection-artifacts` bypasses the stat-keyed digest
cache and re-hashes every admitted classification, segment, and task-episode
artifact. Task-episode component publication uses the same exact SHA plus
size/mtime gate and mandatory digest filename. Ctime may change during the
attested hardlink publication lifecycle. It falls back to full content
validation whenever its receipt is absent or stale. Alongside those gates, the v2 session semantic
receipt combines named per-component roots. A current
segment-index receipt supplies its canonical semantic SHA and a current
Markdown receipt supplies its content SHA without reopening either artifact;
legacy or drifted receipts take the exact-content fallback and are restamped.
For an index artifact of at most `8 MiB`, the receipt may materialize the same
canonical volatile-key-free JSON once and hash it in bulk. Larger artifacts
retain the streaming scalar hash. Both paths implement one semantic mode and
must produce the same digest.
The records root also binds privacy structural markers. Candidate-bearing
markers may identify exact raw-line byte ranges without storing values or
digests; repeat policy construction reads only those ranges from raw authority,
while absent or malformed range metadata selects a full raw-block scan.
The marker has its own schema and exact raw-block binding, so a rooted marker
may survive an unrelated classification-generation change. That crossing does
not admit the classification artifact: positive marker ranges are reread from
raw under the current detector, and a negative marker skips only an exact
published raw prefix.
Upstream, event classification uses append-stable content-addressed raw line
blocks.
Each completed block is checkpointed, so a cooperative deadline can preserve
progress before segment generation and a growing session can reuse its sealed
prefix. The cache stores derived classification fields and mergeable raw-free
block summaries only: raw text, parsed payloads, and exact sensitive literals
remain excluded. The compact cache index stores block identities, receipts, and
privacy markers; summaries stay in immutable block artifacts rather than being
duplicated into the growing index. On an ordinary append, rehydration
materializes only a bounded raw/classification tail and merges its block
summaries with the exact previously published session aggregate. A broken or
incompatible prefix explicitly hydrates all block summaries. The hot path also
reuses attested sealed raw blocks and segment topology. Cold migration or
small-session compatibility selects the explicit full-replay fallback. A goal
signal expands the bounded replay frontier to the start of the crossing open
lifecycle, then merges rebuilt tail lifecycles with stable prior ranges.
Cooperative deadlines are checked between
phases and bounded classification or segment waves; a timeout preserves
compatible work and the published last-good generation. Source growth changes
the umbrella raw identity, while a stage producer or policy change invalidates
only that stage and its declared downstream checkpoints.

The umbrella checkpoint carries control state only. Its classification entry
references the compact cache index, its raw-block entry references the staged
block index and small receipts, and its segment map contains only newly built
tail components. Stable published segments are deliberately omitted and can be
relinked again after interruption, preventing every later phase checkpoint from
rewriting the historical component maps.

The work identity follows the core producer DAG rather than a circular global
source epoch: classification precedes segment and task-episode production, and
the session index follows both. During the declared 0.7.0 transition, a cache
block or segment from one exact predecessor generation may cross that boundary
only after its full identity payload, raw-block/input digest, and artifact
receipt validate. The staged copy is rewritten with the current generation
before publication. No schema-wide or caller-declared compatibility route is
available. Any such crossing adds a deterministic migration receipt to the
atomic session manifest with exact predecessor/target IDs, artifact counts,
raw fingerprint, publish ID, and rollback posture.
The same bounded bridge may carry a later exact owner-reviewed predecessor
whose stage output has independent semantic-parity proof, including the D-0088
execution-only validation kernels. Every source ID remains enumerated; unknown
or malformed identities still fail closed.

For a growing session, each published raw block is admitted for reuse only
when its role, line range, byte size, declared SHA-256, and freshly measured
artifact SHA-256 all match the current raw event slice. The immutable block is
then linked into the sibling work tree; the changed tail and new blocks are
materialized normally. A current per-block token summary may be reused only
under the current accounting schema and generator. This avoids rewriting and
re-accounting sealed history without trusting the manifest alone.

Session-sensitive literal discovery scans the same bounded raw blocks, in a
bounded process pool when useful, but merges exact values only in process
memory. It first searches for the mandatory family
of sensitive assignment labels before invoking the exact assignment matcher.
Every exact assignment match contains one of those labels, so benign oversized
lines avoid pathological regex backtracking without reducing credential
coverage. The ephemeral literal policy is still rebuilt from raw authority and
is never serialized.

Within that one policy-bound build, recursive derived-text redaction may reuse
a bounded process-local `(field, text)` result for short repeated strings.
The cache is never serialized, is discarded with the process, and has an exact
uncached execution path. It changes execution cost, not privacy admission,
artifact identity, or evidence authority.

Heavy construction owns a nonblocking per-session build lease. It does not own
the global maintenance lease. A completed build is revalidated against current
raw and generation identities, then takes the global lease only for atomic
publication, registry update, and dirty propagation. A source race abstains and
leaves last-good readable. Maintenance never removes a current resumable work
directory; it may remove only an old incompatible work identity after proving
the session lease inactive and revalidating current raw authority.

Generated session-projection debris has a separate cleanup conveyor. The
ordinary apply route verifies only a bounded number of PID-owned orphan stages
per run; `--session-stage-verification-limit` lets a scheduled owner raise that
small bound without turning hot status into a raw scan. Exact projection-work
classification remains excluded from ordinary apply and requires the explicit
`--inspect-session-projection-work` flag behind a resource-gated maintenance
owner. The deeper route still proves current raw identity, inactive session
lease, incompatibility, and the quiet-age guard immediately before removal.
Schedulers may run the bounded stage drip frequently and the projection-work
contour less often. Neither contour removes raw evidence, current resumable
work, or published last-good projections, and cleanup progress does not imply
semantic freshness. An unattended scheduler may use
`--success-on-deferred-lock` so healthy owner contention becomes a clean retry
on the next timer tick rather than a false service failure; the cleanup packet
still reports `deferred_active_writer` and no mutation.

Projection-work reclamation is producer-local first. Once a session builder
has proved the current work identity and owns that session's build lease, it
removes only quiet, shape-valid sibling work whose stored identity is
incompatible with the proved current identity. This avoids rescanning
unrelated raw transcripts and prevents normal source growth from leaving an
unbounded trail of obsolete generations. A producer-local mutation writes a
compact diagnostics receipt immediately, so a later build failure cannot hide
the already observed cleanup effect. The scheduled contour is a recovery
fallback: `--session-work-verification-limit` selects one persisted
round-robin batch per run, records its cursor under diagnostics, and leaves all
unselected work as explicit `verification_deferred`. A host scheduler must use
a calendar trigger with a visible next elapse; an elapsed timer without a next
trigger is unhealthy even if its unit remains active. Doctor excludes both
projection stages and projection-work directories from archive counts and
reports them separately.

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

When the published session generation remains compatible and only token fields
are stale, backfill stages the existing projection and atomically rewrites the
manifest, raw-block index, segment indexes, and session-index accounting
fields. It verifies the raw SHA before and after and does not rerun
segmentation. A `raw_mirrored_index_deferred` session without a complete
projection still requires initial materialization.

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

Projection lifecycle uses a complete owner source set, not the current bounded
batch, to distinguish omission from retirement. A full all-session search
build persists a versioned deterministic registry-set identity; bounded
updates may add current sources but cannot infer deletion. When a previously
projected ID is absent from a valid complete registry, search and episode
readers withhold generated candidates until a clean replacement succeeds.
The replacement removes monolith-owned exact, episode, dense, posting, and
queue rows, rebuilds existing shards, cleans Atlas, and removes orphaned graph
contributions. Its tombstone list is a generated projection-retirement receipt;
the preserved session directory, raw bytes, hashes, and refs remain evidence
authority. A missing or malformed registry cannot make a complete-source-set
claim, and an authoritative empty registry may publish an empty projection.

The graph has an additional generated dependency: one verified persisted
entity-registry snapshot is pinned for the complete build or maintenance
operation. Every source contribution uses the immutable index from that
snapshot, and both graph metadata and source rows record its dependency
identity. Runtime aliases are not re-resolved independently per record.
That dependency separates a rare declared semantic epoch (registry schema and
canonicalization versions) from the frequent content revision (source
fingerprint, semantic digest, and entity count). The complete dependency ID
still pins one immutable operation. Same-epoch content growth makes graph reads
abstain only until a proof-gated registry-materialization rebind advances the
pins; it is not a structural full-rebuild reason.
When the old and current dependency identities have the same exact registry
entry-set fingerprint, entity count, and semantic epoch, and every stored graph
source has a valid old binding plus a declared compatible generation
transition, rebind is metadata-only by construction. It updates generation and
dependency columns transactionally without rescanning node/edge payloads or
running selective registry migration. Entry-set drift retains the complete
materialization proof and bounded refresh route.

Ordinary hot maintenance status remains metadata-bounded: it does not parse
raw transcripts to classify temporary projection-work compatibility. Exact
raw and producer identity is still required by explicit cleanup and repeated
immediately before any removal (AOA-SM-D-0078).

After bounded graph source refresh removes every registry materialization
mismatch, final generation/dependency rebind repeats complete registry node and
route-pair equality instead of rehashing unrelated graph payload tables. Any
remaining mismatch falls back to bounded refresh (AOA-SM-D-0079).

The complete materialization proof derives expected registry pairs from each
source's normalized route-token set and recomputed selective dependency digest.
It compares all aggregate/contribution registry edges, registry-node semantics,
and endpoint existence without parsing unrelated contribution payloads
(AOA-SM-D-0080).

Completion of a session-generation predecessor queues graph maintenance only
for that session. Global historical graph work remains an explicit backlog
route and is never inferred from one live session transition (AOA-SM-D-0081).

When the complete compact registry/materialization proof identifies exact
source contributions whose route pairs disagree with the current registry,
repair those exact sources with `graph-maintenance --source-key ... --apply`.
Exact apply requests rebuild their named clean sources, never widen without
source keys, do not override blocked or orphaned source state, and must be
followed by the same proof before registry rebind (AOA-SM-D-0082).

Do not classify registry links intentionally omitted by event/segment
high-fanout policy as source-version drift. When compact rebind proves only
missing registry-to-route contribution pairs, its mutation adds that exact set
and refreshes only touched aggregates; any extra pair, semantic mismatch,
dangling endpoint, malformed payload, selective dependency drift, or changed
count fails the additive guard (AOA-SM-D-0083).

For a declared projection-generation predecessor, reconstruct producer fields
from the exact predecessor source but preserve dependency generations from the
stored predecessor identity. Substituting current dependencies would make a
real dependency transition impossible to prove. Exact source SHA, declared
pair, full identity equality, and complete materialization proof remain
mandatory (AOA-SM-D-0084).

Entity-registry construction distinguishes incremental navigation history from
an authoritative rebuild. Incremental refresh may retain bounded prior-snapshot
aliases and retired identities under an explicit history policy. A full rebuild
uses only current declared owner sources and route terms built in the same
candidate search store; it cannot merge the prior generated registry or prefer
an older operational rollup. The registry records both its history policy and a
versioned semantic fingerprint of the observed route entries. A changed or
unverifiable observed dependency makes the registry stale even when runtime
source mtimes, schema, producer generation, and entity count are unchanged.
The registry separately records a versioned runtime-owner fingerprint derived
from stable entity identities and content-bearing source-ref tokens. A newer
runtime-source `mtime` causes that fingerprint to be recomputed: an exact match
proves a content-equivalent rewrite for registry purposes, while mismatch or
missing legacy coverage requires registry catch-up. Timestamp advance alone is
neither semantic freshness nor semantic staleness. When the persisted
registry, producer generation, semantic digest, and observed-route dependency
are all verified and the only stale reason is a changed runtime-owner
fingerprint, the atomic registry/search sync refreshes that runtime layer
directly over the persisted observed entries. It then updates only changed
registry search documents. This bounded route must fail closed to the complete
builder for any observed dependency drift, requested history/source-policy
change, unverified digest, or producer change; it never uses an old observed
projection to conceal route-term debt.
The complete archived route-term fallback uses one grouped pass across all
registry layers. It begins from a compact covering document index and follows
document-route primary-key order rather than issuing one route-led random
document walk per layer. Its optional bound is applied by per-layer rank after
the shared aggregation, and rows merge into canonical entities as the cursor
advances instead of retaining every route-signal row twice in memory. Bounded
and complete semantics remain equivalent.
Previous registries, rollups, and route terms remain generated navigation
surfaces; their resolvable raw and owner refs remain the evidence authority.

## 8. Consumer routing

Consumers should start with the cheapest typed route that matches the
question. Exact identities and structured filters precede broad text search.
Materialized rollups precede shard resampling. Graph packets are used for
bounded topology, not for evidence-free conclusions. Raw or segment expansion
is the final authority route when a claim matters.

Default portable search enforces that order, not only the route planner. For
exact identifiers, commands, and short literals it probes the compatible exact
posting generation first and executes lexical FTS only after an exact miss.
`route_selection` and the cost profile expose whether the fallback ran. A
missing projection with automatic raw fallback disabled remains unresolved,
but returns a truth-qualified explicit next route instead of an empty command.

For a supported exact query scoped to one archived session, an insufficient or
timed-out projected result may fall back to a bounded read of that session's
raw JSONL before broader raw-text search. The pass writes no index and computes
the manifest digest while scanning. Only a complete digest-verified pass can
prove absence; partial or unverifiable scans must expose that state. The live
append-only tail remains a separate freshness route.

For an unscoped supported exact query, the read path may also supplement the
generated global result from a bounded recent-session window selected from
persisted search freshness state plus a small newest-registry mtime probe. Live
and actionable-dirty candidates have separate quotas; source scans share one
strict time/session/byte envelope and stop after the first matching session.
This route writes no index, suppresses generated compaction-history copies, and
always reports `global_scope_complete=false`: a bounded miss is never a global
absence claim or a freshness upgrade.

Episode query normalization retains the exact token. A bounded Russian
instrumental-form expansion may use an FTS prefix to obtain candidates, but a
sparse candidate receives semantic term credit only when the query and source
tokens reduce to the same bounded morphology stem. Prefix-only collisions are
rejected and counted in the packet; the query-time policy is independently
versioned without rewriting episode projections.

Hybrid episode fusion preserves one sparse rank-one candidate only when its
lead is decisive and either coherent source evidence or a narrow typed
structural relation with raw coordinates explains that lead. The packet names
the guard, refs, score gap, fusion-policy version, and bonus. Ordinary
candidates still use reciprocal-rank fusion; source-kind weight, semantic
similarity, mention, or adjacency alone cannot activate the guard. This is a
navigation rule and never admits the replay, fork, delegation, failure,
recovery, or consequence claim without its normal evidence-reading gate.

Local cross-encoder reranking has a separate escalation policy. Weak lexical
coverage remains visible but cannot trigger automatic work by itself.
Automatic reranking requires a structural causal, recovery, or
explicit-sequence reason and a bounded provider-health result proving the
optional model already loaded. Cold, unknown, or unavailable providers are
reported as deferred and are not woken. Explicit reranking remains an opt-in
route whose cold-start cost is shown separately. Health packets omit
host-private model and cache paths, and reranker order remains navigation
under the ordinary evidence and claim-shape gates.

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

Automatic transcript sweeps separate raw preservation from projection cost.
Once a source exceeds the sweep indexing envelope, the sweep publishes a
content-addressed raw capture and preserves the last-good indexes instead of
starting one uninterruptible whole-session rebuild. The capture remains
explicitly ahead of the stale projection until a compatible heavy or resumable
index route lands. Every selected non-current record enters either its declared
repair or a visible fallback repair route; a new freshness reason cannot become
an unowned `skipped_unhandled_freshness` state. A deferred projection upserts one
session-scoped persistent obligation bound to the capture epoch, byte watermark,
and digest.

Before a sampled live-tail candidate is declared quiet enough for automatic
catch-up, the status route rechecks its declared transcript path with one
bounded filesystem stat. A newer live mtime overrides the persisted scheduling
clock, so an active session remains read-only-fallback accessible without
starting a full projection pass from a stale quiet-window observation.

A session-scoped skill or MCP usage probe may preserve a verified archived-raw
source contribution even when the selected global search provider is missing,
stale, or incomplete. `bounded_current` canonicalizes only that returned
scope, carries its source fingerprint and evidence refs, and always states
that it does not upgrade global freshness or authorize an exhaustive negative
claim.

Graph readers expose global recall freshness and bounded returned-evidence
freshness as separate axes. Returned evidence-bearing nodes and edges are
mapped through their source contributions, then checked against store
generation identity, source fingerprints, and the source-state ledger. A clean
bounded scope never makes a stale global graph current; missing, truncated, or
unverified contributor coverage never becomes `scope_current`. When a compact
timeline is selected from a wider neighborhood, both scope states remain
visible.

Graph freshness also verifies the pinned entity-registry schema, producer
generation, source fingerprint, and semantic digest against the current
persisted snapshot and its stronger owner sources. A missing, changed, or
owner-obsolete dependency blocks graph candidate admission. Owner-source mtime
advance is only a bounded recheck trigger; the versioned runtime-owner
identity/content fingerprint decides whether the registry semantics changed.
This does not make a resolvable local evidence ref false; that ref remains
available through its stronger source route.

## 11. Maintenance coordination

All generated writers share a maintenance lease and coordinator packet. Hot,
backlog, catch-up, deep, and manual-bulk profiles represent different resource
and mutation envelopes. Timer-driven work yields to active owners and records
resource-pressure deferrals.

Atlas maintenance separates compatible session drift from structural
generation migration. Missing or empty state may bootstrap incrementally, and
current-generation source-fingerprint changes remain bounded. An invalid
schema, incompatible producer generation, incomplete root/state publish epoch,
or mismatched axis epoch requires a clean build. Non-deep automatic profiles
defer that work with the exact deep next route instead of invoking
`--no-clean`; the deep profile owns the budgeted all-session rebuild. Readers
remain stale until root, projection state, and every axis share the expected
generation and publish identity.

Confirmed source retirement is likewise structural work. Non-deep bounded
profiles defer the search, episode/dense, shard, Atlas, and graph clean
producers together and expose the exact deep next route. The deep profile uses
the complete current registry for atomic monolith replacement and global
orphan cleanup. Candidate admission stays closed between detection and
publication; a successful process or partial cleanup cannot promote the old
source set to current.

Each writer pins its generation identities to the producer bytes loaded by the
current process. It rechecks the resolved producer source before atomic
publication; a missing, unreadable, or changed source refuses publication and
preserves the last-good projection. Re-reading a mutable script path must not
make in-memory code claim a newer generation.

Optional JSON progress events are best-effort observability. A broken progress
pipe is detached and later heartbeat events are suppressed without aborting
semantic work. The operation packet exposes delivery, failure, and suppression
counts separately. Projection receipts, generation checks, resolvable evidence,
and atomic publication prove semantic progress; heartbeat delivery, process
exit, timer completion, and lock acquisition do not.

Bounded projection work also persists a durable progress receipt immediately
after the atomic publication and its component-delta outbox record. The
receipt is correlated to the maintenance execution, session, work identity,
and publish identity, so a resource hard-timeout or missing child stdout can
recover the exact bounded publication evidence from the owner store. Recovery
proves bounded publication progress and keeps the retry obligation, but it
does not prove child completion, remaining-work exhaustion, or global
freshness. Work checkpoints and the retry queue use the same durable atomic
write boundary, allowing continuation to reuse completed segments instead of
restarting the session.

Multi-lane evaluations use the same coordinator in read mode. They pin
source and projection semantic identities before candidate generation, reject
an active writer or incompatible generation without publishing a pin, and
admit results only when a second snapshot under the same lease is semantically
identical. Physical database bytes, inode, mtime, and observation clocks remain
race diagnostics rather than evaluation identity. Operational rollup shard
paths, source file size and mtime, scan duration, and graph-ledger clean/dirty
clocks are likewise telemetry. Their query-bearing status, counts, source
digests, generations, and evidence coordinates remain part of semantic
identity.

A cold reader can itself create or retire SQLite WAL/SHM observations while
capturing an otherwise unchanged semantic snapshot. The reader may retry at
most three immediate captures only when every failure diagnostic names that
capture-local physical transition. Every attempt remains visible. Any source,
schema, generation, semantic, integrity, or mixed diagnostic stops the retry
and refuses the evaluation.

Timer-originated `auto-maintenance-resource` deferrals are also written to the
generated persistent retry queue under `diagnostics/`. The
`auto-maintenance-retry` dispatcher consumes at most a bounded number of due
items, deduplicates by profile and target, applies exponential backoff, recovers
an interrupted in-flight claim after dispatcher restart, and stops after the
profile retry limit for actual resource or execution failure. Contention with
another healthy maintenance owner does not consume that failure budget: the
dispatcher resets the attempt cycle, records a contention cycle, and keeps the
same intent pending for the next fair window. A later successful periodic or
retry launch clears the pending intent. Manual operator launches do not
silently create background work. A host scheduler may invoke the portable
dispatcher, but the queue and retry semantics remain owned by this organ;
scheduled retry is not semantic maintenance success.

A session-projection freshness obligation is stronger than an ordinary bounded
resource retry. The profile attempt limit bounds one execution cycle but cannot
delete the obligation. Backlog or deep targets the exact session through the
resumable projection lane. A green process, timer, fallback, or checkpoint
retires the item only after the stable manifest proves coverage of its required
capture watermark. Append-only capture uses a same-epoch published byte
watermark; a monolithic capture requires exact bytes and digest. Failed cycles,
oldest obligation age, due count, and next attempt remain visible in
`maintenance-status`.

Projection generation follows materializer ownership rather than file
co-location. In particular, task-episode generation covers lineage and the
task-episode builder/materializer, not transcript discovery, capture, import,
sweep, retry, or resource orchestration. An orchestration-only edit must not
create task-episode, episode-semantic, or graph rebuild debt. Moving a
materializer boundary requires a source-contract regression test; exact known
predecessors may cross only through reuse-then-restamp proof, while unknown
generations remain incompatible.

A periodic launch that observes an open graph-drip circuit must not clear the
same profile's retry intent while the dispatcher owns it in flight. The
dispatcher alone reconciles that claim and, when bounded work remains, creates
its successor. Circuit-open cleanup applies only to a non-running queued item.
When the circuit names session-generation predecessors, the periodic resource
wrapper uses the same bounded, deduplicated reindex handoff as the hook worker
instead of merely stopping at the circuit. A directly launched graph fallback
also performs that handoff from its verified child result. Each predecessor
queues graph continuation only after its session generation is current. A
worker wave with a pending predecessor does not probe deferred graph jobs
first, and a wave without predecessors computes one graph-circuit snapshot for
all deferred graph jobs rather than rescanning the same dependency per job.

A resource-blocked bounded fallback becomes semantic success only when its own
typed child result is verified and its post-run state proves zero remaining
work. That verified fallback result clears the profile retry intent even though
the primary resource route was denied. Partial fallback progress keeps the
intent pending, and an untyped or unverifiable child cannot claim completion.

Bounded session discovery does not rescan global derivative state. For the
backlog and deep owner profiles, the auto-maintenance coordinator instead
passes its already-observed preflight entity-registry state into bounded index
planning. A stale preflight state schedules the atomic registry/search sync.
A bounded search update cannot claim that sync as covered when its global
derivatives were explicitly deferred; the dedicated action remains required.
The later owner-level post-maintenance freshness probe may retire that bounded
deferral only when it proves the index surface current with no diagnostics.

Route readiness keeps absent selected-scope evidence visible without turning
it into synthetic maintenance work. Missing source axes, missing generated
axes, failed global gates, and diagnostics remain retryable. A current route
index with zero signals for a required semantic layer reports an evidence gap
but does not schedule another maintenance cycle merely to wait for unrelated
future source evidence.

The catch-up resource route consumes an explicitly ready live-tail command
independently of the packet's global recommendation. An unrelated cleanup or
historical projection recommendation must not displace a ready recent-session
catch-up; the shared lease, resource gate, and command-local guards still
decide whether that bounded writer may run.

Before host resource admission, that live-tail selection reads only persisted
search freshness scheduling state and, when no search candidate exists, the
generated graph hot state. It may recheck the named live transcript with one
bounded filesystem stat for quiet-window truth. This pre-admission route does
not run global maintenance status, rebuild observed entity-registry
dependencies, classify cleanup candidates, hash projection stages, or parse
raw evidence. Missing or insufficient scheduling state falls through to the
ordinary host resource gate; the admitted child retains complete dependency,
lease, checkpoint, and publication validation. The navigation packet declares
that it performed no source scan and never upgrades persisted scheduling state
to freshness truth.

Inside an admitted incremental search cycle, archived route-term mutations
set a versioned transactional entity-registry dependency marker in the same
SQLite transaction. A clean marker lets repeated freshness and
post-publication checks reuse the persisted observed semantic dependency
without grouping the complete monolith again. Missing tracking, a missing
trigger, or a dirty marker falls back to the exact observed-dependency
recomputation. The marker is cleared only after the existing registry
snapshot, observed-source, history-policy, search-document, generation, count,
and signature gates commit successfully. It is invalidation metadata, not
dependency identity or freshness authority.

Within one admitted process, repeated consumers of the same atomically
published entity-registry snapshot reuse its already exact semantic digest
only while device, inode, size, nanosecond mtime, and nanosecond ctime all
remain identical. The first read recomputes the digest; any rewrite or
replacement invalidates the bounded process cache. Search sync may reuse that
same digest only when maintenance status has verified it against the snapshot's
stored digest. Resource-demand keys carry a profile epoch, including the
index-drip fallback, so a materially optimized execution shape starts a fresh
bounded learner instead of inheriting obsolete peaks from an older algorithm.

That fast path remains inside the selected profile's route-size envelope. An
oversized live-tail target is deferred to an explicit heavy or resumable route,
while ordinary bounded maintenance continues across the rest of the backlog;
one large session must not monopolize recurring catch-up attempts.

The `hot` and `catchup` profiles never spend their bounded freshness window on
an oversized deferred or generation-stale projection. They exclude every
heavy candidate from ordinary repair, record a handoff to `backlog` or `deep`,
and continue directly with recent bounded work. The `backlog` and `deep`
profiles may advance at most one heavy projection per slice before their
ordinary maintenance. All automatic oversized builders share a nonblocking
heavy-lane lease across profiles. When it is held, another owner profile
defers only its heavy candidate and continues toward ordinary bounded
maintenance; it does not start a second memory-heavy build. Applying Codex
sweeps use the same lease per selected raw source at or above the heavy
threshold, including mirror-only capture; smaller sources in the sweep remain
eligible.

A preserved capture ahead of an otherwise compatible published session is also
an explicit resumable-lane candidate even when route-generation drift is not
present. Large captures enter the exclusive heavy lane. A smaller capture is
not promoted into the automatic heavy-lane exclusion set: its watermark-bound
obligation directly targets the same checkpointed reindex command, leaving hot
capture-watch reconciliation available instead of letting ordinary metadata
maintenance declare a no-op.

The recurring catch-up resource wrapper has two freshness routes. A ready
live-tail target keeps the bounded targeted command. When no live-tail target
is ready and the timer explicitly enables index drip, the wrapper launches the
probe-class bounded `index-maintenance` route directly; it does not first
attempt the global catch-up child and wait for resource denial. This preferred
drip retains admission, the maintenance lock, dirty-first fairness, semantic
progress receipts, and automatic retry. Its completion is bounded-scope
completion only; backlog/deep remain responsible for global convergence.

The bounded drip publishes selected session rows into the monolith search
store but does not rebuild the global search catalog or synchronize the global
entity registry in its latency-critical process. It marks the catalog stale
and forces shard readers to fall back to the now-current monolith, so selected
evidence is immediately queryable without presenting stale shard topology as
current. The maintenance result names these global derivatives as unresolved;
backlog, deep, or the explicit catalog/registry routes own their convergence.
Manual targeted recovery can set
`AOA_SESSION_MEMORY_SEARCH_DEFER_GLOBAL_DERIVATIVES=1` for scoped
`search-index <session> --no-rebuild` commands to use the same bounded
publication contract without changing a producer identity through a new CLI
surface. Run the global catalog and entity-registry refresh once after the
target batch instead of paying that whole-database cost after every session.
The recurring drip also admits only `light` search work and caps route raw
repair at 32 MiB. Warm and heavy sessions remain explicit live-tail targets or
backlog/deep work; a single old session cannot consume the freshness timer's
entire wall-clock budget.

For bounded freshness, the cost ceiling is applied twice. Session-registry raw
bytes, event counts, and segment counts, augmented by the selected sessions'
persisted search document counts when that database is available, first reject
obviously warm or heavy records before semantic projection files are opened.
The persisted count lookup is one bounded indexed query over the discovery
window; it never scans document payloads. The same lookup excludes a persisted
`deferred_live` session from global bounded discovery, including its
round-robin reserve; an explicit live-tail target remains its repair owner. The
discovery cursor still advances across the original window and the deferral
remains visible. Semantic fingerprints then provide authoritative dirty-state
classification only for the admitted subset. Pre-admission is a resource
guard, not freshness proof; unavailable or incomplete cheap metadata is
admitted rather than trusted.
The materially changed index-drip execution shape uses a fresh resource-demand
epoch so obsolete learned peaks cannot silently restore the old admission cost.
Segment generation uses a deterministic process pool with a default of four workers
and a bounded one-to-six range, falling back visibly to serial execution when
the pool cannot start. Segment processes use the isolated `spawn` start method
and receive immutable classification-block refs, exact line ranges, bounded
reconciliation patches, and raw-block refs. They load only overlapping block
ranges and receive no serialized `RawEvent` slice. On ordinary append work the
parent also retains only the bounded replay tail and mergeable historical block
summaries instead of a whole-session `RawEvent` graph. Event classification
uses the same bounded worker
envelope and persists a receipt after every completed block. Every other
oversized deferred candidate is also
excluded from the remainder of that locked cycle; otherwise a second heavy
session could fall through the ordinary repair selection and rebuild under the
global lease. A compatible published oversized session remains in the ordinary
metadata/search lane; an indexed session enters the heavy lane only when its
session route generation actually requires a projection rebuild. Recent
smaller sessions can still reach their search and session projections. Catch-up
and backlog give the exclusive heavy lane up to a 900-second slice when the
enclosing cooperative budget permits; hot maintenance retains its short slice.
Event-dense archives
may still require multiple slices, but classification now advances a durable
block checkpoint instead of repeating the full pre-segment cost. Timer-originated resource
denial retains the normal persistent retry intent; a checkpoint is progress,
not completion.

The recurring catch-up route has a narrow hard-timeout grace after its
cooperative budget. The host resource launcher terminates a child that cannot
reach an internal checkpoint within that envelope and records a retryable
timeout instead of allowing an unbounded service run.

When that termination follows a completed atomic publication, the launcher
matches only the exact execution-correlated progress receipts for its target.
It reports `progress_recovered` alongside the unverified process result and
retains the retry item until a later run proves the required watermark.

Interrupted projection stages are removable only after a stronger raw authority
is verified again at deletion time. A content-addressed owner capture qualifies
when its declared and actual SHA-256 both exactly match the staged raw; the
published last-good projection remains untouched.

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

The host launcher timeout is a hard runtime envelope, not an alternate work
budget. For automatic profiles it is the smaller of the profile's absolute
timeout ceiling and the effective cooperative budget plus separate bounded
allowances for resource-process startup and in-flight atomic completion. The
startup allowance prevents interpreter/module initialization before the
cooperative clock starts from consuming the atomic-completion allowance. Full
search and atlas rebuild paths receive the same remaining
cooperative budget as incremental work; rebuilds publish from temporary state
only after completion. A host-enforced termination is reported as
`resource_hard_timeout`, never as semantic completion, and remains eligible for
the persistent retry route. The outer wrapper waits only a bounded cleanup
margin beyond that hard envelope.

Observed query demand is a bounded scheduling input, not evidence authority.
An automatic scoped profile may prepend only the configured bounded set of
demanded archive sessions that fell outside its normal date or count window.
An applying graph queue consumer may likewise top up actionable demanded
sources from the generated ledger even while the queue is nonempty, but only
to one batch-sized reserve and counting entries already queued. Reports retain
the original scope, added targets, queue top-up, remaining work, and freshness;
the demand signal never makes a projection current by itself.

Automatic index discovery is also bounded before any per-session manifest,
segment index, or projection fingerprint is opened. Each profile selects a
fixed dirty-first window from persisted search freshness state, reserves part
of that window for a round-robin registry cursor, and rotates the dirty tail
independently so one repeatedly blocked source cannot starve the rest of the
backlog. The cursor packet under `diagnostics/` is generated scheduling state,
not projection truth. A bounded pass always reports
`global_scope_complete=false`; only persisted projection states and owner
freshness checks decide whether selected work is current. Explicit manual
maintenance without a discovery limit retains the strict whole-scope scan for
audits, migrations, and rebuild decisions. Thus recurring cost is bounded by
the profile window while repeated successful runs still converge across a
growing archive.

Resource demand identity follows that bounded profile envelope. When a
profile's discovery, repair, graph, or fallback envelope changes materially,
its demand epoch advances so host runtime learning cannot carry an obsolete
pre-change peak into the new route. Host-specific owner floors remain outside
the portable bundle; they must cite revision-bound observations, retain a
guarded margin, and allow larger learned peaks to win. A timer receipt that
only proves admission or denial does not calibrate the floor; use successful
transient-unit peaks from the matching demand epoch.

Resource-blocked all-session graph fallback also maintains a separate bounded
background candidate reserve. Existing entries count toward the reserve, and
only the missing count is admitted from the generated ledger before ordinary
priority and refresh-cost selection. An individually oversized source remains
queued for a compatible heavy route but cannot prevent cheaper sources from
entering the candidate window. A child process that exits successfully without
advancing any actionable source while work remains reports a retryable
`resource_blocked_graph_drip_no_progress`, not completion. Reports expose the
existing queue count, reserve, requested top-up, progress, and remaining work.

Queued graph follow-up from a hook worker is likewise a bounded graph-queue
consumer, never an all-source discovery pass. It seeds only one bounded
candidate window from the persisted source ledger, prioritizes an explicitly
targeted session, and publishes queue and ledger state after each portion. The
job's cooperative budget therefore begins around a bounded source window; an
old queued graph intent cannot monopolize the shared maintenance lease merely
because the archive continued to grow before that job was resumed.

An applying graph-queue consumer packs complete session groups into its hard
source-count batch limit. It may skip a group that does not fit the remaining
capacity and admit a later complete group; only a single session larger than
the whole limit is split, and that split is explicit in the maintenance
packet. This aligns contribution hydration with its session boundary and
prevents a larger planning window from repeatedly parsing sources that the
current transaction cannot commit. Dry exact-cost planning retains its
declared candidate window and does not claim this mutation posture.

When that consumer explicitly blocks a source because its session-index
generation changed, the hook worker persists the named predecessor as a
deduplicated one-session reindex job instead of retrying the graph source in a
loop. The predecessor build and publish remain under the shared maintenance
lock already held by the hook worker; the child must not reacquire that same
lock. Checkpointed or temporarily blocked work remains in the deferred queue,
while a hard failure is retained in the failed queue rather than mislabeled as
done. Only a direct current-generation probe may enqueue the successor graph
job; attempted, selected, checkpointed, or failed reindex work never admits
graph continuation. The handoff count is bounded per graph job, so later graph
passes discover any remaining predecessors without flooding the worker queue.
If the same blocked result already opened the no-progress circuit, the circuit
preserves that report as recovery evidence and queues its named predecessor
instead of reopening an identical graph attempt.

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

If the latest globally usable graph-maintenance report selected sources but
explicitly records `semantic_progress=false`, automatic graph recommendation
opens a circuit and emits no retry command until dependency or freshness state
changes. A queued hook-worker graph job is retained in the deferred queue and
promoted only after the circuit closes. The no-progress guard reopens only
after the graph store or one of that pass's bounded selected upstream source
paths changes. Capture, search, and non-graph sweep lanes continue
independently.

A search schema mismatch is incremental only for an owner-declared additive
version pair whose live store still has documents, route indexes, route terms,
and no structural schema diagnostic. The first committed dirty-session repair
may advance the store epoch; every untouched session remains dirty until its
own projection state is regenerated. Both outer preflight and the inner index
planner use this same transition contract; a bounded automatic profile must
not silently reinterpret an admitted incremental transition as a PID-local
full rebuild. Unknown or structurally incomplete transitions keep the
deep/full-rebuild boundary.

`maintenance-cleanup` recognizes PID-tagged graph, search, and pre-journal
session-projection temps, removes only those whose producer PID is absent while
holding the shared maintenance lease, and leaves live stores, published
last-good session files, and raw evidence untouched. Legacy unowned session
stages require an exact reported content digest; a mismatch causes no mutation.
An active writer defers cleanup rather than racing publication. Debris removal
is operational progress and always reports `semantic_progress=false`.
Operators may use `--surface graph`, `--surface search`, or
`--surface session-projection` to inspect and clean only that generated surface.
This prevents a bounded debris repair from paying unrelated raw-authority scan
cost; the default `--surface all` remains the complete cleanup audit.

Ordinary hot maintenance planning inventories abandoned session-projection
stages from metadata without hashing staged raw. Unverified generated debris
does not preempt semantic search or graph maintenance. Each cleanup apply cycle
checks at most one staged candidate and skips deep projection-work identity;
exact raw authority is still checked and rechecked before removal, while the
complete read-only debris classification remains an explicit dry-run audit
(AOA-SM-D-0085).

For current-session retrieval, the atomic projection publish identity owns the
stable archive byte, line, and digest watermark. An older source snapshot may
describe the work seed and the capture materialization may already contain a
newer append-only tail; neither replaces the publish watermark. The persistent
live-tail overlay bridges from that exact published prefix only after its
source identity, ledger chain, captured size, last block, and stored prefix
attestation all verify. Later growth of the same owner inode does not invalidate
the immutable captured prefix: the uncaptured suffix is exposed as unscanned
and keeps the result non-exhaustive until the next capture (AOA-SM-D-0086).

Graph incremental mutation checks its pinned registry dependency before
mutation and before commit. A dependency race rolls back the transaction.
Full rebuild publishes a temporary store only after the same recheck, so a
rejected rebuild leaves the previous graph intact. A graph store from before
the dependency contract requires an explicit full rebuild; a bounded
maintenance batch cannot silently upgrade its global semantics.
During that explicit rebuild, duplicate aggregate refresh is set-based: the
complete duplicate-ID set is materialized once, contribution counts are
summarized by one grouped scan per contribution table, while the richest
representative payload is retained inline by the bulk UPSERT. Final count and
evidence counters are applied with set-based JSON updates; full rebuild must
not hydrate every duplicate payload in Python or repeat contribution-table
aggregation. Incremental maintenance retains its bounded ID-chunk refresh
because it operates on a small dirty-source frontier. For a multi-source
append-only graph batch, contribution and source rows are inserted first and
their unique node and edge frontier is refreshed set-wise once inside the same
transaction. Exactly one new source retains the direct incremental aggregate
path. This prevents shared session or route aggregates from being decoded and
mutated once per segment while preserving cooperative deadline rollback,
pinned registry checks, and atomic type-count updates.
Known same-epoch dependency drift instead routes through the complete
registry-derived materialization proof and atomic rebind. Unknown epochs,
schema or canonicalization changes, malformed legacy bindings, and rejected
proofs retain the full-rebuild boundary.
An implementation-only graph producer transition may use the same rebind only
for an exact declared predecessor-to-current generation pair and the declared
whole-file SHA of the previous producer. The proof reconstructs that previous
projection identity and evaluates every distinct source-generation group, so a
store containing both current and exact-predecessor rows is not rejected merely
because bounded maintenance already made progress. Every group must be current
or explicitly admitted, every source must retain a dependency binding, static
versions and complete registry materialization must pass, and query-bearing
content remains digest-bound across one atomic restamp. This is a bounded
reuse-then-restamp migration, not a persistent compatibility reader mode.

Optional graph sidecar export is a separate manifest-committed projection.
Nodes and edges are rendered in private staging, the graph transaction and
pinned dependency are checked before publication, and `graph/index.json` is
written last with artifact hashes plus the committed store generation,
dependency, and semantic digest. Readers reject a missing, mismatched, or
interrupted manifest and return to the graph store or a bounded source-backed
fallback; sidecar files never make a rolled-back graph mutation visible.
A current clean graph store may publish a missing or stale sidecar without
inventing a dirty source or rebuilding the graph. That packet reports sidecar
publication separately and keeps semantic graph progress false.

## 12. Search and graph pressure

Storage diagnosis separates physical bytes, duplicate generated payload,
cardinality, and recall requirements. WAL checkpointing is distinct from row
reduction, database rebuilding, or physical compaction.

Search context-tail omission is permitted only where a current replacement
rollup preserves route refs and bounded recall fallbacks. Graph high-fanout
reduction requires equivalent evidence refs and query behavior before generated
rows can be removed. Neither route changes raw or segment authority.

An exact correlation graph request may carry `--session` through neighborhood
and timeline continuation. This is a bounded retrieval-seed constraint, not a
new graph identity or authority: recovered raw candidates still require exact
structured source-event correlation admission before nodes or edges appear.

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
