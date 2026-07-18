# AoA Session Memory Readiness

## Role

`READINESS.md` defines what readiness means and which proof route applies to
each layer of `aoa-session-memory`.

It is a stable contract, not a dated status snapshot, command history, metrics
ledger, or substitute for running live gates. Current counts, versions,
watermarks, timings, storage, queues, failures, and successful runs belong to
generated diagnostics and runtime status packets.

## Readiness Thesis

The organ is ready for a claim only when the evidence required by that claim is
current enough, resolvable, and verified through the owning route.

Readiness is typed:

- an archive may be preserved but not indexed;
- exact retrieval may be ready while semantic or graph projections are stale;
- a projection may be stale-readable while its catch-up is deferred;
- a portable bundle may be valid while a live install has runtime debt;
- tests may be green while semantic retrieval remains unproven;
- a route may find evidence without proving the claim built from it.

No single green boolean should erase those distinctions.

## Status Vocabulary

Every agent-facing projection or gate should use explicit states:

| State | Meaning |
| --- | --- |
| `current` | source, version, and watermark requirements are satisfied |
| `stale-readable` | the last committed projection remains usable within a stated boundary |
| `deferred` | work is known and intentionally waiting for time, quiet, resource, or dependency |
| `blocked` | progress requires a named external condition or owner action |
| `failed` | the attempted operation failed and has an evidence-bearing diagnostic |
| `truncated` | only part of the requested evidence was returned |
| `fallback` | a weaker or more expensive route answered because the preferred route was unavailable |
| `unresolved` | the system cannot establish the requested identity, relation, or claim |

`deferred` and `blocked` are not success. `stale-readable` is not
`current`. A systemd or timer success is not semantic readiness.

## Evidence Classes

Readiness proof may come from several classes:

1. **Mechanical proof** — schemas, serialization, deterministic builds, ref
   resolution, idempotency, file presence, bounded budgets, and parity.
2. **Runtime proof** — real hooks, queues, locks, watermarks, catch-up,
   restart, resource deferral, and live access.
3. **Retrieval proof** — exact and semantic gold refs, ranking, omissions,
   noise, collisions, and abstention.
4. **Relationship proof** — temporal, causal, owner, dependency, and graph path
   correctness.
5. **Reading proof** — claim support, contradiction, supersession, current
   versus historical state, and unsupported-claim control.
6. **Resource proof** — latency, context, storage, cardinality, update cost,
   WAL, and headroom.
7. **Portability proof** — clean export, standalone behavior, source parity,
   neutral paths, and excluded private/runtime state.

Mechanical proof can establish mechanical invariants. It cannot establish
semantic relevance, causality, or model/agent learning by itself.

## Layer Gates

### 1. Capture

Ready when:

- producer identity and source metadata are preserved;
- lifecycle receipts are schema-valid;
- hooks are fail-open and bounded;
- missing raw material becomes a visible incident;
- capture does not depend on heavy interpretation.

Typical proof:

- focused capture tests;
- `codex-grounding` and `codex-hooks-status` for the Codex adapter;
- a real lifecycle probe when hook behavior changes;
- incident inspection for negative paths.

### 2. Raw archive

Ready when:

- preserved raw bytes or an explicit unavailable state exist;
- source identity and hashes are coherent;
- raw refs resolve;
- archive repair is idempotent;
- no generated projection is required to recover authority.

Do not infer archive readiness from segment or search presence alone.

### 3. Segments and indexes

Ready when:

- generated intervals match preserved coordinates;
- segment and session indexes resolve to raw evidence;
- schema/classifier versions are visible;
- stale indexes are detected and rebuildable;
- compaction markers do not create false semantic microsegments.

### 4. Episodes

Ready when:

- task, decision, failure, and recovery boundaries are manually plausible;
- intent, action, result, verification, and open branches carry refs;
- compaction is treated as a coordinate, not a forced semantic boundary;
- ambiguous episodes expose confidence and flags;
- raw events remain available.

### 5. Exact and typed retrieval

Ready when:

- paths, UUIDs, commands, flags, errors, names, dates, and phrases recover
  expected refs;
- entity registration, mention, usage, and consequence remain distinct;
- literal fallback remains available until a replacement is proved;
- route selection and cost are inspectable;
- hard negatives do not become positive claims.

### 6. Semantic and hybrid retrieval

Ready when:

- multilingual and mixed code/text cases recover relevant episodes;
- boilerplate, loaded skill bodies, system instructions, and tool dumps are
  source-aware;
- semantic improvements do not hide exact-recall regressions;
- fusion/reranking adds lane-specific value under equal budgets;
- insufficient evidence produces abstention.

### 7. Graph views

Ready when:

- relations are typed, directed, and evidence-backed;
- mention/cooccurrence are not presented as causality or usage;
- traversal starts from specific anchors;
- node, edge, evidence, time, and context budgets are bounded;
- graph expansion improves its intended lane over retrieval without graph;
- high-fanout and cardinality pressure are measured;
- important paths resolve to raw/segment/session refs.

### 8. Narrative and global memory

Ready when:

- consolidation occurs over episodes after a proved trigger;
- global answers preserve exceptions, conflicts, and refs;
- local questions do not pay global expansion cost;
- summaries do not replace evidence or promote doctrine;
- iterative deepening stays bounded.

### 9. Freshness and orchestration

Ready when:

- projection versions, dependencies, and watermarks are visible;
- dirty state propagates;
- incremental workers are idempotent and restartable;
- live tails wait for a quiet window without hiding stable evidence;
- resource/lock deferral later resumes automatically;
- no heavy necessary projection starves indefinitely;
- readers see honest stale/fallback state;
- graph readers distinguish global recall freshness from bounded returned-
  evidence freshness without letting either scope hide the other;
- manual maintenance is not a hidden happy-path dependency.

### 10. Access plane

Ready when:

- CLI, skill, and MCP packets follow the same evidence contract;
- MCP remains read-only and plan-only unless its owner contract explicitly
  changes;
- payloads preserve refs, freshness, truncation, and next route;
- access-plane success is not treated as proof authority;
- mutation stays behind explicit owner commands.

### 11. Promotion and learning

Ready for promotion only when:

- a real repeated or important observation has been reviewed;
- the target owner is named;
- provenance and negative evidence are retained;
- a minimal invariant or candidate artifact is appropriate;
- the target eval/admission route passes;
- rollback or supersession is possible.

Finding a candidate is not promotion. A session-memory packet never grants
training, skill, automation, policy, or owner-write authority.

### 12. Portability

Ready when:

- authored source is identified;
- clean export is produced through the owner builder;
- private sessions, diagnostics, caches, DBs, secrets, and host paths are
  excluded;
- source and standalone behavior are checked;
- the bundle is understandable without the local AoA deployment;
- adapter-specific behavior does not redefine the portable identity.

### Portable scenario posture

The owner-local `stats/` port may publish a revision-bound census of which
declared live-scenario cases have a reviewed, privacy-safe portable fixture.
That statistic measures portable proof capacity only. It does not establish
that a case passed, retrieval is correct, a live archive is healthy, or the
system is ready. Its packet must name the source revision, population, refs,
and authority ceiling.

## Change-Specific Verification

Use the narrowest sufficient route.

| Changed surface | Minimum evidence |
| --- | --- |
| Root docs or authority map | link/role review, clean export, source/standalone parity |
| Config or schema | focused tests, schema validation, affected projection rebuild path |
| Capture or hooks | focused tests, adapter grounding, hook status, live lifecycle probe |
| Classifier or taxonomy | reindex/catch-up, manual positive/negative samples, freshness |
| Exact search | fixed gold refs, collision and fallback cases, latency |
| Semantic/rerank | unchanged gold corpus, per-lane A/B, exact-recall guard |
| Episode formation | manually adjudicated boundaries and cross-compaction cases |
| Graph semantics | relation/path review, hybrid-only comparison, cardinality |
| Orchestration | real incremental, quiet-window, resource-block, restart, catch-up |
| Storage/pruning | replacement proof, refs, fallback, before/after, rollback, post-cleanup rerun |
| Portable behavior | export, validation, portable audit, source/standalone smoke |
| Owner-local stats port | manifest and packet validation, source-revision derivation, authority-ceiling review |

## Manual Semantic Proof

Manual laboratory evidence is primary for semantic correctness.

A strong protocol:

1. select evidence independently from the tested retriever;
2. seal the expected refs and forbidden claims;
3. run the candidate routes with fixed versions, freshness, budgets, and seed;
4. reveal and adjudicate the result;
5. inspect raw/segment refs for important hits;
6. record false positives, omissions, unsupported relations, and cost;
7. repeat with new negative, collision, temporal, causal, multilingual, and
   randomized cases.

Tests or eval fixtures should grow from stable observed failure modes. Synthetic
fixtures must identify their origin and cannot substitute for archived-session
proof.

## A/B and Return Discipline

For an architectural retrieval or projection change:

- preserve baseline A before implementation;
- compare A and B on the same evidence, versions, budgets, and freshness;
- report results by query lane;
- do not accept a mean gain that hides critical exact, provenance, freshness,
  causality, or abstention loss;
- rerun after cleanup;
- return to earlier layers when later evidence invalidates their proof.

A layer is not complete forever. New episode, graph, narrative, or freshness
evidence may reopen taxonomy, capture, indexing, routing, or presentation.

## Live Status Route

Do not infer current posture from this file.

Start with read-only packets:

```bash
python3 scripts/aoa_session_memory.py projection-status \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa

python3 scripts/aoa_session_memory.py maintenance-status \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --full

python3 scripts/aoa_session_memory.py search-provider-status \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

Use their exact next action rather than copying a generic maintenance command.
For a portable checkout, use the standalone audit:

```bash
python3 scripts/aoa_session_memory.py audit \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/aoa-session-memory \
  --portable-bundle
```

## Completion Audit

`audit` is the mechanical and topology completion gate. It may fail honestly
while the local mechanism is otherwise usable.

```bash
python3 scripts/aoa_session_memory.py audit \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

A green audit does not prove every semantic lane. Completion of a larger
retrieval, graph, narrative, or learning goal additionally requires its manual
corpus, A/B evidence, provenance review, runtime/freshness proof, resource
evidence, and cleanup conditions.

## Diagnostic Retention

Generated diagnostics may preserve:

- exact command and config versions;
- timestamps and watermarks;
- before/after metrics;
- queue, lock, and resource state;
- seeds and corpus IDs;
- failure and recovery receipts;
- proof artifact refs.

Diagnostics are runtime evidence, not durable architecture. Keep them under
their retention policy and do not summarize their changing values into root
docs.

Historical implementation narratives remain discoverable through Git history,
release/diagnostic evidence, and session memory. They should not burden the
current readiness contract.

## Completion Rule

Do not say “ready” or “complete” because:

- tests are green;
- a command exited zero;
- a timer ran;
- a projection exists;
- a candidate was found;
- one aggregate score improved;
- a summary sounds plausible.

State exactly which layer, scope, evidence class, freshness state, and owner
gate have passed, and which remain open.
