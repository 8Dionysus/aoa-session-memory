# AoA Session Memory

`aoa-session-memory` is a portable memory organ that preserves agent-session
trajectories as evidence and turns them into queryable, provenance-carrying
read models without confusing memory with truth.

Its current production adapter is Codex. The architecture is intentionally
broader than Codex: sessions, evidence, episodes, indexes, typed relationships,
freshness, and review boundaries are the durable center.

## Why It Exists

Long agent work does not fit safely inside active context.

Sessions compact, terminate, move between runtimes, and accumulate more exact
evidence than a summary can preserve. Commands, corrections, failed branches,
decisions, tool results, verification, and ownership boundaries must remain
recoverable after the context that produced them is gone.

`aoa-session-memory` separates:

- preserved evidence from interpretation;
- retrieval from proof;
- memory from current owner truth;
- candidate learning from promoted capability;
- portable source from local runtime state.

## Current System

The portable implementation currently provides:

- Codex transcript capture and lifecycle receipts;
- raw transcript mirrors and compaction-coordinate raw blocks;
- readable segments plus machine indexes;
- stable session identity, naming, and archive navigation;
- typed agent events and task episodes;
- exact/literal search and structured route filters;
- entity registry, usage-chain, consequence, and neighborhood routes;
- generated atlas, search, graph, and operational rollup projections;
- bounded graph neighborhood, bridge, timeline, and GraphRAG-style packets;
- projection freshness, maintenance coordination, and recovery routes;
- read-only, plan-only MCP access;
- clean export and installation into another workspace.

These capabilities are read and evidence surfaces. They do not make generated
classifications, graph edges, or summaries reviewed truth.

## Direction of Growth

The organ is intended to grow from reliable session recall toward cumulative
agent experience:

```text
experience
  -> evidence-backed memory
  -> reviewed understanding
  -> eval
  -> skill / automation / dataset / training candidate
  -> changed agent
  -> new experience
```

Future adapters may preserve dialogue-oriented sessions, model experiments,
instrumentation, eval/training lineage, and experience across model versions.
Those are architectural horizons, not claims about the current implementation.

The organ does not itself own eval verdicts, skills, automation policy, model
training, or agent identity. It preserves the evidence and lineage from which
their owners may make reviewed decisions.

## Architecture at a Glance

```text
agent runtime
  -> adapter and lightweight capture
  -> raw session evidence
  -> segments, typed events, and task episodes
  -> exact / structured / semantic / graph / narrative projections
  -> bounded evidence packets with freshness and refs
  -> human or agent review
  -> owner-controlled promotion
```

The downward route always remains available:

```text
narrative or answer
  -> episode / graph / search hit
  -> segment
  -> raw or external owner evidence
```

## Evidence and Authority

Use the source that owns the question:

| Question | Authority |
| --- | --- |
| What was recorded in the session? | raw transcript and source metadata |
| Where is the relevant evidence? | generated indexes and route packets |
| What does a repository do now? | that repository's current source |
| What did an eval prove? | the eval owner and admitted evidence |
| Is a projection current? | live projection and maintenance status |
| Why does the architecture have this boundary? | `DESIGN.md` and owner decisions |

Session memory can find owner truth. It does not replace it.

## Repository and Install Shapes

The same portable source can run as:

```text
standalone aoa-session-memory repository
workspace/.aoa
```

A live workspace may contain private session archives, generated search/graph
stores, and diagnostics. A portable bundle always excludes those runtime
surfaces; private evidence transfer belongs to a separate owner-to-owner
migration route.

Before publication, run the same bounded public-safety gate used by
`export-bundle`:

```bash
python3 scripts/aoa_session_memory.py portable-public-safety-audit \
  --aoa-root /path/to/portable/.aoa
```

The gate fails closed on runtime evidence, credential-like values, private
host paths, or incomplete scan coverage without echoing matched values.

## Quick Start

Validate a source or installed root:

```bash
python3 scripts/aoa_session_memory.py validate \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

Inspect filesystem and adapter health:

```bash
python3 scripts/aoa_session_memory.py doctor \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

Inspect projection and maintenance state without mutating:

```bash
python3 scripts/aoa_session_memory.py projection-status \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa

python3 scripts/aoa_session_memory.py maintenance-status \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --full
```

For installation, hooks, and clean export, use `INSTALL.md`.

## Common Evidence Routes

Plan an exact path, UUID, command, error, or literal phrase query:

```bash
python3 scripts/aoa_session_memory.py literal-query-plan \
  "Traceback ValueError"
```

Verify an exact literal against one archived raw authority when the planner
selects that fallback:

```bash
python3 scripts/aoa_session_memory.py archived-raw-search \
  --session SESSION_ID_OR_LABEL --query "exact literal"
```

A complete negative result is authoritative only when the packet reports a
digest-verified, non-truncated scan.

Ask how an operational entity was used and what happened after:

```bash
python3 scripts/aoa_session_memory.py usage-chain \
  aoa-session-memory-mcp --kind mcp
```

Validate and preview admission of an immutable reviewed skill-use receipt:

```bash
python3 scripts/aoa_session_memory.py skill-usage-receipt validate RECEIPT.json
python3 scripts/aoa_session_memory.py skill-usage-receipt record RECEIPT.json
```

Only an explicit second call with `--apply` writes the receipt. A current
reviewed receipt can support invocation, deflection, and verification claims,
plus an effect-attribution candidate. It cannot issue a benefit or promotion
verdict; that authority remains with `aoa-evals`.

Inspect one task interval:

```bash
python3 scripts/aoa_session_memory.py task-episodes latest \
  --limit 10 --order recent
```

Inspect a bounded relation between known anchors:

```bash
python3 scripts/aoa_session_memory.py graph-bridge \
  aoa-session-memory-mcp exec_command \
  --source-kind mcp --target-kind tool
```

These commands return navigation and evidence packets. Open the returned raw,
segment, session, receipt, or owner refs before relying on an important claim.

The complete operational and recovery reference lives in `PIPELINE.md`.

## Freshness Is Part of the Answer

Generated projections may be:

- `current`;
- `stale-readable`;
- `deferred`;
- `blocked`;
- `failed`;
- `truncated`;
- `fallback`;
- `unresolved`.

A stale packet can still route older evidence, but it cannot silently answer a
current-state question. Use the packet's typed next action or the relevant
maintenance route. A timer success is not proof that every semantic projection
is current.

Graph freshness includes the exact persisted entity-registry generation used
to canonicalize its nodes and edges. Graph metadata and every source
contribution pin that dependency. If the registry generation, semantic digest,
source fingerprint, or stronger owner-source freshness changes, graph routes
abstain until catch-up or full rebuild; they do not mix aliases dynamically
inside one graph generation.

## Agent Access

Agents should use progressive disclosure:

1. classify the question;
2. select an exact or typed route;
3. inspect the bounded packet and freshness;
4. expand to episodes, graph, semantic, or narrative layers only when needed;
5. open raw evidence for exact verification;
6. return unknown when the evidence is insufficient.

`DESIGN.AGENTS.md` defines this contract. The MCP surface follows the same
read-only evidence route and does not own mutation or proof.

## Automatic Maintenance

Capture stays lightweight. Incremental workers and maintenance routes advance
segments, indexes, search, atlas, registry, graph, and other generated
projections.

The intended happy path is automatic and observable:

- dirty state propagates through projection dependencies;
- active live tails wait for a quiet window;
- bounded jobs resume after resource or lock deferral;
- readers retain the last committed usable snapshot;
- status distinguishes launcher success from semantic freshness.

Manual commands remain available for diagnosis, controlled repair, deep
rebuild, and recovery. See `PIPELINE.md`.

## Documentation Map

| File | Read it for |
| --- | --- |
| `AGENTS.md` | immediate laws, authority, and task routing |
| `DESIGN.md` | identity, architecture, boundaries, and open horizon |
| `DESIGN.AGENTS.md` | agent query and evidence-access contract |
| `PIPELINE.md` | operational lifecycle, command reference, maintenance, and recovery |
| `READINESS.md` | readiness states, proof requirements, and gate selection |
| `INSTALL.md` | installation, hook generation, and portable export |
| `NAMING.md` | archive labels and semantic naming |
| `docs/decisions/` | durable rationale and generated decision lookup indexes |
| `stats/` | bounded revision-level measurements over portable source surfaces |

Source code, config, and schemas own runtime behavior. Live commands and
generated diagnostics own current status. Git history and session evidence own
historical development detail.

The owner-local stats port currently measures portable scenario-fixture
coverage at a named source revision. It does not inspect live archives or turn
fixture coverage into memory quality, route correctness, or readiness.

## Portability

Export a clean bundle from the active authored source:

```bash
python3 scripts/aoa_session_memory.py export-bundle \
  --source-aoa-root /path/to/source/.aoa \
  --target-dir /path/to/aoa-session-memory \
  --force
```

Install into a workspace:

```bash
python3 scripts/aoa_session_memory.py install \
  --source-aoa-root /path/to/aoa-session-memory \
  --workspace-root /path/to/workspace \
  --force
```

Do not hand-copy generated hooks or portable consumers when the builder/export
route exists.

## What Does Not Belong Here

The portable owner terrain should not accumulate:

- private transcripts or session-specific notes;
- experiment diaries, temporary benchmarks, or failed variants;
- changing runtime counts and version snapshots;
- local operator doctrine;
- generated search/graph databases or maintenance reports;
- model caches or training artifacts;
- unreviewed claims promoted from session history.

Keep construction history in session provenance and diagnostics. Promote only
the smallest durable contract, invariant, fixture, or decision that the owner
actually needs.

## Core Rule

```text
Preserve evidence.
Project without replacing it.
Route by intent.
Expose freshness.
Review before promotion.
```
