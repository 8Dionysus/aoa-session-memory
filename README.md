# AoA Session Memory

**Memory for long-running agent work, with a path back to the evidence.**

A long Codex session contains much more than its final answer. It contains
decisions, corrections, failed approaches, commands, tool results, verification,
and working patterns that may become useful again later.

Most of this experience remains buried inside transcripts. Context gets
compacted, sessions end, repositories change, and the exact path that produced
an important result becomes difficult to recover.

`aoa-session-memory` preserves that path. It captures agent-session history,
gives important events stable coordinates, and builds ways to search and inspect
the experience without losing the connection to its original source.

The current production adapter is Codex.

## What it does

`aoa-session-memory` can help an agent:

- recover important context after a long session has been compacted
- find decisions, errors, verification results, and unfinished work
- compare events and working patterns across multiple sessions
- inspect how skills, tools, MCP servers, and workflows were actually used
- trace conclusions back to the session evidence they came from
- connect development history with the current state of a repository
- prepare reviewed candidates for evals, skills, automations, and datasets
- derive privacy-safe recurring-motif candidates from reviewed stage profiles
  without adopting them as policy

The portable implementation includes raw session preservation, readable
segments, typed task episodes, stable session identity, structured entities,
exact and semantic retrieval, temporal and graph views, freshness tracking,
agent-facing skills, and read-only MCP access.

These parts work together, but they do not all claim the same authority.
A search result helps locate evidence. A generated episode helps interpret a
part of the work. The original session records what happened. The current
repository source describes what the software does now.

## How it works

```text
agent session
  -> lightweight capture
  -> preserved raw evidence
  -> events, segments, and task episodes
  -> exact / structured / semantic / graph views
  -> bounded evidence packet
  -> human or agent review
  -> improvement or eval candidate
```

The `aoa-session-experience-metabolism` skill consumes only bounded,
generated `stage_profile_v1` reports. It retains counterevidence and
trajectory cost, then routes candidates through independent review, eval,
shadow, owner acceptance, and a separate explicit adoption receipt, plus
reversible rejection or rollback. Frequency and correlation never produce an
automatic skill, policy, or benefit claim.

Derived views are used for navigation. Important results keep references back to
their sources:

```text
answer or narrative
  -> episode / graph / search result
  -> segment
  -> raw session event or external repository evidence
```

This distinction matters in real agent work.

Normal operation is event-driven and incremental. Hooks append a durable raw
capture ledger and update the live-tail overlay first, so a newly observed
session can be queried before every heavier projection has caught up. Published
session components have separate generation identities and checkpoints;
unchanged raw blocks, segments, classifications, and task-episode shards are
reused instead of rebuilt. A transactional outbox then advances exact search,
semantic, entity, and graph consumers independently. Their freshness remains
visible and no partial reader is allowed to make a global negative claim.

A skill may appear in a transcript without being used. It may have been visible
to the agent, selected, read, partially followed, completed, verified, or linked
to a later result. `aoa-session-memory` treats these as different states instead
of collapsing them into a single “skill used” claim.

The same principle applies to decisions and repository state. Session memory can
preserve why a decision was made. The repository that owns the decision
determines whether it still applies.

## Try it

You do not need access to the author's private Codex sessions.

The repository includes public-safe synthetic fixtures that run through the real
session-memory mechanics. They exercise skill routing, evidence packets,
lifecycle boundaries, recovery behavior, attribution limits, and Codex adapter
handling.

The optional `inference_economy_session_contribution` source function exposes
only count-only token ledgers and raw compaction-boundary refs for the shared
provider-neutral inference-economy ABI. It is default-off, keeps provider-
reported and estimated counts separate, and does not claim runtime outcome,
eval, closeout, promotion, or owner acceptance.

Behavioral-sandbox cases run in isolated temporary environments. They cannot
make an in-process network connection or modify the authored source tree. One
router-integration case additionally uses the separately owned `aoa-skills`
contract and therefore belongs to the optional ecosystem lane.

### Supported environment

- Linux
- Python 3.11 or newer

Codex CLI is not required for the standalone fixture tests. It is required only
for live Codex capture and adapter-grounding checks.

### Clone the repository

```bash
git clone https://github.com/8Dionysus/aoa-session-memory.git
cd aoa-session-memory
```

### Create an isolated environment

```bash
python3 -m venv /tmp/aoa-session-memory-venv
/tmp/aoa-session-memory-venv/bin/pip install \
  "mcp>=1.28,<2" \
  "build>=1.3,<2" \
  "jsonschema>=4.25,<5" \
  "pytest>=8,<10" \
  "PyYAML>=6.0,<7.0"
```

### Run the standalone behavioral sandbox

```bash
/tmp/aoa-session-memory-venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_skill_behavioral_sandbox.py \
  -k "not route-global-owner-cli"
```

A successful run exits with status `0`.

### Validate the standalone checkout

```bash
/tmp/aoa-session-memory-venv/bin/python scripts/aoa_session_memory.py validate \
  --workspace-root "$PWD" \
  --aoa-root "$PWD"
```

### Run the portable source suite

```bash
/tmp/aoa-session-memory-venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_session_memory.py \
  tests/test_public_tree_audit.py \
  tests/test_git_history_audit.py
```

The fixtures verify their named behavioral and mechanical boundaries. They do
not claim that a model independently selected the best skill or that a skill
improved performance. Those questions require live evidence and a separate eval.
The complete skill-router integration suite uses a pinned `aoa-skills` checkout
and runs in the optional ecosystem workflow; it is not a standalone dependency.

## Public Goal catalog

The owner-local `goal-catalog` read surface enumerates current and historical
Goal lifecycles from the complete available session index. It returns
public-safe correlation and lifecycle fields, source generation and watermark,
opaque immutable pagination, and item/page digests. Missing, unknown, stale,
deferred, and invalid source states fail closed instead of becoming a current
dashboard snapshot. See [`docs/GOAL_CATALOG.md`](docs/GOAL_CATALOG.md) for the
CLI contract and privacy boundary.

The owner-local `goal-thread-board` read surface publishes a real board for
one exact Goal/master-thread binding. It combines allowlisted lifecycle
markers from current owner indexes with safe immutable item markers and direct
parent/fork observations from typed Codex app-server reads, while withholding
all prompt/transcript bodies, raw paths, and private metadata. Branch lifecycle
and replayable event ordering remain explicitly missing when their owner does
not publish them. See [`docs/GOAL_THREAD_BOARD.md`](docs/GOAL_THREAD_BOARD.md)
for the exact query, pagination, currentness, and privacy contract.

### Run the standalone MCP demo

Build and install the read-only MCP package without writing build state into
the checkout:

```bash
/tmp/aoa-session-memory-venv/bin/python scripts/build_mcp_package.py \
  --outdir /tmp/aoa-session-memory-artifacts \
  --staging-root /tmp/aoa-session-memory-stage

/tmp/aoa-session-memory-venv/bin/pip install \
  /tmp/aoa-session-memory-artifacts/aoa_session_memory_mcp-*.whl
```

Create an invented public-safe session corpus and query it:

```bash
/tmp/aoa-session-memory-venv/bin/python examples/synthetic/bootstrap_demo.py \
  --destination /tmp/aoa-session-memory-demo

/tmp/aoa-session-memory-venv/bin/aoa-session-memory-mcp \
  --workspace-root /tmp/aoa-session-memory-demo \
  search DEMO-ANCHOR-42 --limit 5
```

Run the real stdio protocol smoke. It lists the MCP catalog, calls the main
route families, opens returned evidence, and verifies that read-only access did
not change the archive:

```bash
/tmp/aoa-session-memory-venv/bin/python \
  examples/synthetic/mcp_protocol_smoke.py \
  --workspace-root /tmp/aoa-session-memory-demo \
  --cwd /tmp
```

## Use it with Codex

Install the portable kernel into a Codex workspace:

```bash
python3 scripts/aoa_session_memory.py install \
  --source-aoa-root "$PWD" \
  --workspace-root /absolute/path/to/workspace \
  --write-user-hooks /absolute/path/to/workspace/.codex/hooks.json \
  --force
```

The installed system will live under:

```text
/absolute/path/to/workspace/.aoa
```

Validate it:

```bash
python3 /absolute/path/to/workspace/.aoa/scripts/aoa_session_memory.py \
  validate \
  --workspace-root /absolute/path/to/workspace \
  --aoa-root /absolute/path/to/workspace/.aoa
```

On a machine with Codex installed, the adapter can also be checked with:

```bash
python3 /absolute/path/to/workspace/.aoa/scripts/aoa_session_memory.py \
  codex-grounding \
  --workspace-root /absolute/path/to/workspace \
  --aoa-root /absolute/path/to/workspace/.aoa
```

This also installs workspace-local hooks for live Codex capture. Verify them:

```bash
python3 /absolute/path/to/workspace/.aoa/scripts/aoa_session_memory.py \
  codex-hooks-status \
  --workspace-root /absolute/path/to/workspace \
  --aoa-root /absolute/path/to/workspace/.aoa
```

Inspect incremental freshness and bounded reader state without forcing a full
rebuild:

```bash
python3 /absolute/path/to/workspace/.aoa/scripts/aoa_session_memory.py \
  projection-status \
  --workspace-root /absolute/path/to/workspace \
  --aoa-root /absolute/path/to/workspace/.aoa

python3 /absolute/path/to/workspace/.aoa/scripts/aoa_session_memory.py \
  freshness-vector SESSION_ID \
  --workspace-root /absolute/path/to/workspace \
  --aoa-root /absolute/path/to/workspace/.aoa
```

`task-episodes SESSION_ID --limit N --order recent` hydrates only the verified
manifest shards needed for the requested result window. Heavy repair remains an
explicit bounded maintenance route, not a prerequisite for live capture or
ordinary recent-session access.

Live exact retrieval uses a compact receipt-bound manifest plus bounded
immutable posting shards. A normal append reads only the new complete JSONL
lines and, when needed, the last open shard; it does not re-sanitize or rewrite
all historical live postings. Returned candidates are still reverified against
their exact raw byte ranges, and a miss remains non-exhaustive.
For a very large unprojected first capture, the live layer indexes a bounded
recent complete-line window and records the omitted prefix explicitly; raw and
the later stable projection retain the complete history.

Large capture epochs also avoid a second whole-history SHA pass: their initial
exact digest is computed natively during capture, later appends remain current
through immutable block-chain evidence, and stable projection/audit supplies a
conventional full-stream digest at an exact watermark without changing raw.

Private session archives, generated runtime databases, diagnostics, secrets, and
host-specific configuration are excluded from the normal portable source.

## Example of live use

Once a workspace has accumulated its own sessions, a user can ask Codex a normal
working question:

> Use aoa-session-memory to review how this skill performed in recent sessions.
> Where did it help, where did it work poorly or get used incorrectly, and what
> likely affected the results? Show examples from the sessions.

The system can locate candidate uses, distinguish the different stages of skill
interaction, compare strong and weak cases, and open the evidence behind the
assessment.

The same approach can be applied to tools, MCP servers, errors, decisions,
workflows, and recurring development patterns.

## How Codex and GPT-5.6 were used

I built `aoa-session-memory` in close collaboration with Codex. Earlier parts
of the project were developed with GPT-5.5, while most of the current
architecture was completed with GPT-5.6 Sol.

Our work took place through long, iterative Codex sessions. We would move from
an architectural idea to implementation, test it, inspect what failed, and
return to earlier decisions when new evidence exposed a problem.

Codex was especially useful when a change touched many connected parts of the
system at once. It helped trace contracts across implementation, schemas,
skills, tests, documentation, generated projections, and portable exports.
This made the architecture-to-verification loop much faster while preserving
the wider context of the project.

Many important changes began with failures we found in real sessions. Semantic
similarity could surface a relevant-looking episode without enough evidence to
support an answer. A skill could appear in a transcript without having been
used. A generated projection could remain readable after the logic that created
it had changed.

We reproduced these cases, followed them through the repository, and turned
them into clearer contracts, evidence boundaries, and regression tests.

I directed the product and made the final architectural decisions, while Codex
helped research, challenge, implement, and verify them. Stable decisions were
then recorded in [`DESIGN.md`](DESIGN.md) and
[`docs/decisions/`](docs/decisions/).

These decisions include preserving session history as evidence, keeping
generated representations traceable to their sources, separating memory from
the current truth of a repository, and requiring review before experience
becomes a durable skill, eval, automation, or dataset.

The project was also used during its own development. Our preserved Codex
sessions became material for retrieval experiments, failure analysis, and
further calibration of the system.

## Documentation

| File | Purpose |
| --- | --- |
| [`DESIGN.md`](DESIGN.md) | architecture, authority, and long-term boundaries |
| [`PIPELINE.md`](PIPELINE.md) | capture, projection, retrieval, and maintenance |
| [`READINESS.md`](READINESS.md) | readiness states and proof requirements |
| [`INSTALL.md`](INSTALL.md) | installation, hooks, and portable export |
| [`docs/BUILD_AND_RELEASE.md`](docs/BUILD_AND_RELEASE.md) | reproducible package build and release gates |
| [`docs/PORTABILITY.md`](docs/PORTABILITY.md) | standalone and optional ecosystem dependencies |
| [`docs/decisions/`](docs/decisions/) | durable architectural decisions |
| [`docs/decisions/AOA-SM-D-0018-owner-capability-home-and-skill-evidence-lifecycle.md`](docs/decisions/AOA-SM-D-0018-owner-capability-home-and-skill-evidence-lifecycle.md) | capability ownership and skill-evidence lifecycle |

## Contributing and security

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before changing evidence or generated
surfaces. Report credential exposure, unsafe history, transcript leakage, path
handling, or MCP authentication issues through the private route in
[`SECURITY.md`](SECURITY.md), not a public issue containing sensitive material.

## License

The repository and projected MCP package are licensed under the
[Apache License 2.0](LICENSE).

## Core rule

```text
Preserve evidence.
Project without replacing it.
Route by intent.
Expose freshness.
Review before promotion.
```
