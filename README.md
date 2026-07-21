# AoA Session Memory

**Preserves agent experience as verifiable evidence for reflection, evaluation, and improvement.**

`aoa-session-memory` is a portable memory system for long-running agent work. It captures the history of a session, gives important events stable coordinates, and builds bounded ways to navigate that history without losing the path back to the original evidence.

The current production adapter is Codex. The architecture is broader than one runtime: sessions, events, episodes, entities, relationships, freshness, provenance, and review boundaries form the durable center of the project.

This repository was prepared for **OpenAI Build Week 2026** in the Developer Tools category.

## Why I built it

During years of working with ChatGPT, and later with Codex, I accumulated a large amount of interaction history. Those sessions contained ideas, decisions, mistakes, research, useful working methods, unfinished directions, and things worth returning to later.

I began to see this history as a gold mine because it reflected my own projects, questions, preferences, and way of thinking. In practice, it was difficult to use. The sessions formed an enormous stream of raw information, and valuable experience became buried inside old transcripts.

Long Codex sessions made the problem more concrete. During one task, an agent may inspect a repository, try several approaches, abandon some of them, change the architecture, write code, run tests, and revise earlier conclusions. After context compaction, only part of that trajectory remains available to the agent.

The first goal of `aoa-session-memory` was simple: recover the task, important decisions, failures, verification results, and unresolved work after compaction or between sessions.

While building it, I noticed that agent work contains recurring entities and event types. Goals, tasks, decisions, skills, MCP servers, tools, commands, errors, checks, results, and consequences can be identified and connected to the evidence that produced them. This opened a wider use case: studying how an agent actually worked across many sessions and using that experience to improve the surrounding system.

## Build Week demo

The demonstration asks Codex a normal working question:

> Use aoa-session-memory to review how the aoa-session-memory skills performed in recent sessions. Which ones were actually used, where did they help, where were they used poorly or incorrectly, and what likely affected the results? Start with a concise overview and show examples from the sessions.

The workflow then:

1. finds relevant recent sessions;
2. identifies real skill-use chains;
3. distinguishes mention, availability, selection, reading, application, completion, and verification;
4. compares strong, weak, partial, and misleading uses;
5. separates observed evidence from interpretation and likely contributing factors;
6. opens resolvable references back to the original session events;
7. proposes a concrete skill improvement and a candidate eval.

Follow-up questions stay conversational:

```text
Open the strongest example and show me what the assessment is based on.

Now show me the weakest or most misleading use.

Based on this, what should be improved in the aoa-session-memory skills,
and which eval should be added first?
```

This demonstrates the larger purpose of the project: accumulated agent experience can become usable material for reflection, evaluation, and reviewed improvement.

## What it does

The portable implementation currently provides:

- Codex transcript capture and lifecycle receipts;
- preserved raw transcript mirrors and compaction-coordinate blocks;
- readable segments and machine indexes;
- stable session identity, naming, and archive navigation;
- typed agent events and task episodes;
- exact and literal retrieval;
- structured entity, usage-chain, consequence, and neighborhood routes;
- semantic and hybrid retrieval surfaces;
- temporal and graph-based views;
- bounded GraphRAG-style evidence packets;
- projection freshness, maintenance, and recovery state;
- skill routing for agent-facing session-memory work;
- read-only, plan-only MCP access;
- clean export and installation into another workspace.

These routes are at different levels of maturity. Each important result should expose its evidence references, freshness state, truncation state, and the next route to use when the available evidence is insufficient.

## The core idea

A session transcript preserves valuable experience, including mistakes, abandoned branches, temporary assumptions, and disagreement. That history becomes useful when it can be searched and interpreted while keeping its origin visible.

`aoa-session-memory` keeps two durable records separate:

1. **Session evidence**, which records what happened during the work.
2. **Owner repositories**, which define the current state of the systems being built.

A memory record can show that a decision was made in a session. The repository that owns the decision determines whether it still governs. A memory record can preserve an eval run. The eval owner determines what that run proves.

Every derived representation remains a navigation layer over stronger evidence:

```text
answer or narrative
  -> episode / graph / search result
  -> segment
  -> raw session event or external owner evidence
```

This allows the system to retrieve broadly while remaining conservative about important claims.

## Architecture

```text
Codex or another agent runtime
  -> lightweight capture
  -> raw session evidence
  -> segments, typed events, and task episodes
  -> exact / structured / semantic / graph projections
  -> bounded evidence packets with freshness and resolvable refs
  -> human or agent review
  -> owner-controlled improvement or promotion
```

The experience lifecycle is:

```text
experience
  -> preserved evidence
  -> reviewed understanding
  -> eval
  -> skill / tool / automation / dataset candidate
  -> changed agent system
  -> new experience
```

No transition is automatic. Evidence may suggest an improvement, while review and the target owner's admission route decide whether that improvement becomes durable.

## What it can be used for

### Continuity after compaction

Recover the active task, decisions, failed approaches, verification results, and unresolved work after a long session has been compacted.

### Cross-session reflection

Compare earlier and recent work, find recurring patterns, and reopen ideas whose value may become clearer as models and tools improve.

### Skill, MCP, tool, and workflow evaluation

Trace how an operational entity was actually used, what happened afterward, where procedure was followed or ignored, and which outcomes may be connected to that behavior.

### Repository and process provenance

Move in both directions:

```text
repository artifact
  -> session episode
  -> intent, decisions, failures, and verification
```

```text
session episode
  -> actions and decisions
  -> commits, tests, artifacts, and current repository state
```

### Personal datasets and specialized agents

Raw transcripts contain repetition, temporary hypotheses, errors, private material, and unsupported claims. Session memory provides a foundation for reviewed selection and labeling. Over time, that process can support curated datasets, specialized agents, and other forms of model adaptation owned by downstream systems.

## How Codex and GPT-5.6 were used

The project was developed through long Codex sessions. Earlier work used GPT-5.5, while most of the current architecture was designed and implemented with **GPT-5.6 Sol**.

Codex participated in:

- architecture research and repeated design review;
- implementation and refactoring;
- repository navigation;
- test design and regression analysis;
- investigation of real session-memory failures;
- creation and calibration of skills;
- documentation and portability work;
- return loops where later evidence reopened earlier assumptions.

The project was also used during its own development. The same long-running sessions that motivated the system became material for capture, retrieval experiments, failure analysis, and further calibration.

This created a direct dogfooding loop: Codex helped build a system that preserves Codex experience, then used that preserved experience to evaluate and improve its own working procedures.

## Quick start

### Supported platform

The current tested platform is Linux with Python 3.12. The portable kernel, validation, and tests can run without Codex. Codex CLI is required for live Codex session capture and adapter grounding checks.

### Clone the repository

```bash
git clone https://github.com/8Dionysus/aoa-session-memory.git
cd aoa-session-memory
```

### Validate the standalone source

In a standalone checkout, the repository root is the AoA root:

```bash
python3 scripts/aoa_session_memory.py validate \
  --workspace-root "$PWD" \
  --aoa-root "$PWD"
```

Inspect filesystem and adapter health:

```bash
python3 scripts/aoa_session_memory.py doctor \
  --workspace-root "$PWD" \
  --aoa-root "$PWD"
```

Run the portable completion audit:

```bash
python3 scripts/aoa_session_memory.py audit \
  --workspace-root "$PWD" \
  --aoa-root "$PWD" \
  --portable-bundle
```

### Run the tests

```bash
python3 -m pip install \
  pytest==9.0.3 \
  "PyYAML>=6.0,<7.0" \
  "jsonschema>=4.0,<5.0"

python3 -m pytest -q -p no:cacheprovider \
  tests/test_session_memory.py \
  tests/test_skill_system.py \
  tests/test_skill_behavioral_sandbox.py
```

### Install into another workspace

```bash
python3 scripts/aoa_session_memory.py install \
  --source-aoa-root "$PWD" \
  --workspace-root /absolute/path/to/workspace \
  --force
```

The installed kernel will live at:

```text
/absolute/path/to/workspace/.aoa
```

Validate the installed workspace:

```bash
python3 /absolute/path/to/workspace/.aoa/scripts/aoa_session_memory.py validate \
  --workspace-root /absolute/path/to/workspace \
  --aoa-root /absolute/path/to/workspace/.aoa

python3 /absolute/path/to/workspace/.aoa/scripts/aoa_session_memory.py doctor \
  --workspace-root /absolute/path/to/workspace \
  --aoa-root /absolute/path/to/workspace/.aoa
```

On a machine with Codex installed, check the adapter grounding:

```bash
python3 /absolute/path/to/workspace/.aoa/scripts/aoa_session_memory.py codex-grounding \
  --workspace-root /absolute/path/to/workspace \
  --aoa-root /absolute/path/to/workspace/.aoa
```

Installation does not copy private session archives, generated runtime stores, secrets, diagnostics, or host configuration. Live Codex hook placement remains an explicit user operation.

## Useful evidence routes

Inspect recent task episodes:

```bash
python3 scripts/aoa_session_memory.py task-episodes latest \
  --limit 10 \
  --order recent
```

Ask how an entity was used and what happened afterward:

```bash
python3 scripts/aoa_session_memory.py usage-chain \
  aoa-session-memory-mcp \
  --kind mcp
```

Plan an exact query for a command, path, UUID, error, or phrase:

```bash
python3 scripts/aoa_session_memory.py literal-query-plan \
  "Traceback ValueError"
```

Inspect a bounded relation between known anchors:

```bash
python3 scripts/aoa_session_memory.py graph-bridge \
  aoa-session-memory-mcp \
  exec_command \
  --source-kind mcp \
  --target-kind tool
```

These commands return navigation and evidence packets. Open the returned raw, segment, session, receipt, or owner references before relying on an important claim.

## Freshness is part of the answer

Generated projections may report states such as:

- `current`;
- `stale-readable`;
- `deferred`;
- `blocked`;
- `failed`;
- `truncated`;
- `fallback`;
- `unresolved`.

A previous snapshot may still be useful for navigating historical evidence, while current-state questions require current owner evidence and an appropriate freshness scope.

## Privacy and portability

A live workspace may contain private transcripts, session archives, search and graph stores, and diagnostics. A normal portable export excludes those runtime surfaces.

An explicit session-inclusive export is a private evidence operation. It must preserve the handling rules of the raw archive and should never be treated as public-safe merely because the kernel itself is portable.

## Current scope

The current production adapter is Codex. Exact, structured, semantic, temporal, graph, skill, and MCP access surfaces exist, with maturity tracked per route and proof class.

The project preserves evidence and produces candidates for review. It does not issue final eval verdicts, silently rewrite skills, promote session observations into policy, or train models by itself.

Future adapters may preserve dialogue-oriented sessions, model experiments, eval and training lineage, and experience across model generations. These are architectural directions rather than claims about the current implementation.

## Documentation

| File | Read it for |
| --- | --- |
| `DESIGN.md` | identity, architecture, authority, and long-term boundaries |
| `DESIGN.AGENTS.md` | agent query and evidence-access contract |
| `PIPELINE.md` | capture, projection, retrieval, maintenance, and recovery |
| `READINESS.md` | typed readiness states and proof requirements |
| `INSTALL.md` | installation, hook generation, and portable export |
| `NAMING.md` | session identity and archive naming |
| `docs/decisions/` | durable architectural rationale and decision indexes |
| `capabilities/` | semantic capability graph and routing contract |
| `skills/` | agent-facing session-memory procedures |
| `evals/` | local evaluation ports and behavioral cases |

## Core rule

```text
Preserve evidence.
Project without replacing it.
Route by intent.
Expose freshness.
Review before promotion.
```
