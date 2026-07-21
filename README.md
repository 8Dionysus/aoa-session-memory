# aoa-session-memory

`aoa-session-memory` gives developers and agents a local, evidence-first way to
recover what happened across long coding sessions without treating recall as
proof.

Long sessions compact, stop, and move between contexts. Summaries lose exact
commands, failures, corrections, decisions, and verification; ordinary search
can retrieve a phrase while hiding whether its source is stale or indirect.
This project preserves session evidence, builds provenance-carrying and
freshness-aware read models, and returns bounded packets that lead back to raw
or owner evidence.

The practical result: ask for an exact identifier, a task episode, how a tool
was used, or a typed graph relation, then inspect the returned evidence refs
before relying on the answer.

## Three-minute standalone quickstart

Requirements: Git and Python 3.11 or newer. The standalone path does not need
OS Abyss, `/srv`, `abyss-stack`, `abyss-machine`, systemd, a bearer token,
sibling repositories, or private transcripts.

```bash
git clone https://github.com/8Dionysus/aoa-session-memory.git
cd aoa-session-memory

python -m venv /tmp/aoa-session-memory-venv
/tmp/aoa-session-memory-venv/bin/pip install 'build>=1.3,<2' 'jsonschema>=4.25,<5'

/tmp/aoa-session-memory-venv/bin/python scripts/build_mcp_package.py \
  --outdir /tmp/aoa-session-memory-artifacts \
  --staging-root /tmp/aoa-session-memory-stage

/tmp/aoa-session-memory-venv/bin/pip install \
  /tmp/aoa-session-memory-artifacts/aoa_session_memory_mcp-*.whl

/tmp/aoa-session-memory-venv/bin/python examples/synthetic/bootstrap_demo.py \
  --destination /tmp/aoa-session-memory-demo

/tmp/aoa-session-memory-venv/bin/aoa-session-memory-mcp \
  --workspace-root /tmp/aoa-session-memory-demo \
  search DEMO-ANCHOR-42 --limit 5
```

The demo destination must be absent or empty. It is built outside the
repository from an invented transcript.

Try the other evidence routes:

```bash
/tmp/aoa-session-memory-venv/bin/aoa-session-memory-mcp \
  --workspace-root /tmp/aoa-session-memory-demo \
  usage-chain query_component --kind mcp_tool --limit 4

/tmp/aoa-session-memory-venv/bin/aoa-session-memory-mcp \
  --workspace-root /tmp/aoa-session-memory-demo \
  task-episodes latest --limit 5

/tmp/aoa-session-memory-venv/bin/aoa-session-memory-mcp \
  --workspace-root /tmp/aoa-session-memory-demo \
  graph-neighborhood synthetic-catalog-mcp --kind mcp

/tmp/aoa-session-memory-venv/bin/aoa-session-memory-mcp \
  --workspace-root /tmp/aoa-session-memory-demo \
  freshness-check raw:line:17 --session latest
```

Run the real stdio protocol smoke to list tools, resources, templates, and
prompts; call the main route families; open a returned raw ref; and prove the
archive hash tree is unchanged:

```bash
/tmp/aoa-session-memory-venv/bin/python examples/synthetic/mcp_protocol_smoke.py \
  --workspace-root /tmp/aoa-session-memory-demo \
  --cwd /tmp
```

## MCP installation and configuration

The distribution is `aoa-session-memory-mcp`. It installs two entrypoints:

- `aoa-session-memory-mcp-server` — stdio MCP server;
- `aoa-session-memory-mcp` — read-only command-line access to the same routes.

Register the installed stdio server with current Codex CLI:

```bash
codex mcp add aoa_session_memory -- \
  /tmp/aoa-session-memory-venv/bin/aoa-session-memory-mcp-server \
  --workspace-root /tmp/aoa-session-memory-demo

codex mcp get aoa_session_memory
```

Start a new Codex session if an already-running session does not see the newly
registered server. Other MCP clients can launch the same command over stdio.
The portable configuration needs no credential.

The package is a deterministic projection of the authored MCP implementation
in `abyss-stack`; it is not a second independently maintained server. Its
manifest records owner commit, exporter identity, file modes and digests,
entrypoints, compatibility, discovery behavior, authority boundaries, and the
complete MCP catalog.

## Synthetic demo

`examples/synthetic/rollout-builder-week-demo.jsonl` is invented public-safe
data. Its bootstrap creates a temporary standalone root with:

- an exact identifier and explicit user intent;
- a correlated MCP failure, recovery, and verified result;
- a superseded decision;
- a task episode and typed entity relationships;
- search, atlas, entity-registry, and graph projections;
- resolvable raw and segment refs plus freshness state.

The demo's readiness packet is deliberately partial: one synthetic session is
useful for route proof, not a claim of production coverage or retrieval
quality. See [the demo guide](examples/synthetic/README.md).

The same guide includes an installed-package negative matrix for root
discovery, portability, transport/authentication refusal, manifest drift, and
stale evidence.

## Architecture

```text
agent runtime / transcript adapter
              |
              v
       raw session evidence  <---------------------------+
              |                                          |
              v                                          |
 segments + typed events + episodes                      |
              |                                          |
              v                                          |
 search + atlas + graph + freshness projections          |
              |                                          |
              v                                          |
 evidence packets with resolvable refs ------------------+
              |
              v
       human or agent review -> current owner truth

abyss-stack authored MCP source
              |
    allowlisted deterministic export
              v
packages/aoa-session-memory-mcp
              |
              +-- standalone stdio installation
              +-- stack-owned system deployment remains in abyss-stack
```

Every derived layer can route downward. A narrative, graph edge, or search hit
never replaces its segment, raw transcript, or stronger external owner.

## Example evidence packet

This shortened packet is derived from the synthetic exact-identifier route:

```json
{
  "ok": true,
  "query": "DEMO-ANCHOR-42",
  "result_count": 1,
  "provider": {
    "authoritative_result_provider": "portable_sqlite",
    "status": {
      "providers": {
        "portable_sqlite": {
          "freshness": {
            "status": "current"
          }
        }
      }
    }
  },
  "results": [
    {
      "event_type": "DECISION",
      "session_id": "builder-week-synthetic-demo",
      "refs": {
        "raw": "raw:line:17",
        "segment": "000__initial-to-latest.md#event-000017--decision--assistant-message"
      },
      "freshness": {
        "status": "fresh",
        "basis": "indexed_snapshot"
      }
    }
  ],
  "authority_boundary": "Raw and segment evidence remain authoritative."
}
```

The packet routes review; it does not prove that the decision is currently
correct in another repository or that one event caused another.

## Evidence, projections, and owner truth

| Layer | What it can establish | What it cannot establish |
| --- | --- | --- |
| Raw transcript and source metadata | What was recorded at a resolvable location | That every recorded claim was correct |
| Segments, episodes, search, atlas, and graph | Where relevant evidence may be and how recorded entities relate | Reviewed truth, causality, or current external state |
| Freshness and diagnostics | Whether a particular projection is current enough for its declared use | Semantic correctness of the source evidence |
| Current repository, service, eval, or operator owner | Present truth for the owned question | The complete history of how a session reached it |

Session memory can find stronger owner evidence. It does not replace that
owner.

## What it can do

- **Exact retrieval** for identifiers, commands, errors, paths, and phrases.
- **Task episodes** with boundaries, failure state, recovery, and verification
  state.
- **Typed entities and relations** that distinguish mention, selection,
  invocation, result, verification, and consequence.
- **Graph routes** for neighborhoods, bridges, timelines, and bounded paths.
- **Freshness-aware answers** that expose current, stale, deferred, missing,
  or unresolved projection state.
- **Resolvable evidence refs** back to raw, segment, session, receipt, or owner
  surfaces.
- **Abstention and next actions** when evidence is missing, stale, unsupported,
  or too weak for a current-state or causal claim.

The MCP catalog is read-only or plan-only. It exposes no write, repair,
reindex, export, install, distillation, or promotion tool.

## Privacy and local-first posture

The core runs locally over a filesystem root and SQLite. stdio is the default
transport. Session evidence, indexes, and queries do not need a hosted service.

Portable source and runtime evidence are separate. This repository excludes
private sessions, raw transcripts, segment bodies, runtime databases,
diagnostics, credentials, caches, and local profiles. The committed demo is
synthetic. Run the safe current-tree gate before publication or contribution:

```bash
python scripts/audit_public_tree.py --root . --fail-on blocking
```

The report returns only finding class, path, line, reason, and a safe
fingerprint — never a matched secret value. A clean current tree does not prove
that Git history or GitHub-hosted surfaces are safe; they are separate
publication gates. The predecessor history is not safe for a direct visibility
change, so publication must follow the [clean-seed route](docs/PUBLICATION.md).

## Current limitations

- The production adapter is currently Codex; universal agent-runtime support is
  an architectural direction, not a present claim.
- Generated episodes, entities, graph edges, and summaries need evidence review
  and can be incomplete or stale.
- The project does not yet claim measured retrieval quality across arbitrary
  private corpora.
- Semantic accelerators and resource-heavy graph expansions are optional and
  may be unavailable on a standalone machine.
- Session memory does not autonomously promote experience into doctrine,
  skills, eval verdicts, automation, datasets, or model changes.
- Causal and current-world claims require stronger admitted evidence; the MCP
  should abstain when that evidence is absent.

## Production adapter

Codex is the current production capture adapter and evidence source. The
portable organ's durable center is broader: session identity, evidence,
episodes, provenance, typed relations, freshness, and review boundaries.
Adapter-specific capture remains separate from the read-only MCP access plane.

## Optional OS Abyss integration

OS Abyss deployments can add managed lifecycle, authenticated loopback HTTP,
host diagnostics, resource admission, `abyss_machine_nervous`, and future
`abyss_stack_rag` acceleration. These integrations are disabled or unavailable
by default and cannot replace `.aoa` evidence.

The current system runtime remains owned, installed, configured, and serviced
by `abyss-stack`. Its explicit workspace, Python, transport, bearer reference,
and systemd profile are intentionally not portable defaults. See
[the dependency boundary](docs/PORTABILITY.md).

## Documentation map

| Document | Use it for |
| --- | --- |
| [INSTALL.md](INSTALL.md) | portable source install, hooks, and bundle lifecycle |
| [DESIGN.md](DESIGN.md) | identity, architecture, evidence, and authority boundaries |
| [DESIGN.AGENTS.md](DESIGN.AGENTS.md) | agent query and evidence-access contract |
| [PIPELINE.md](PIPELINE.md) | capture, projections, maintenance, recovery, and CLI routes |
| [READINESS.md](READINESS.md) | readiness states and proof requirements |
| [MCP package README](packages/aoa-session-memory-mcp/README.md) | complete tool/resource/prompt contract and deployment diagnostics |
| [Portability](docs/PORTABILITY.md) | dependency census and optional integration boundary |
| [Build and release](docs/BUILD_AND_RELEASE.md) | external reproducible build and release gates |
| [Publication boundary](docs/PUBLICATION.md) | predecessor audit verdict and clean public-seed gates |
| [Licensing review](docs/LICENSING.md) | dependency inventory and unresolved root-license gate |
| [Decisions](docs/decisions/README.md) | durable rationale and generated decision indexes |

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing evidence or generated
surfaces. Report credential exposure, unsafe history, transcript leakage, path
handling, or MCP authentication issues through the private route in
[SECURITY.md](SECURITY.md), not a public issue containing sensitive material.

## License

The projected MCP package is Apache-2.0 and contains the exact owner license.
The repository root license is not yet confirmed. Apache-2.0 is the documented
proposal, but public visibility and release publication remain blocked until
the repository owner explicitly chooses a root license and the corresponding
`LICENSE` is added. See [the licensing review](docs/LICENSING.md).

## OpenAI Builder Week context

This standalone packaging and demo work was prepared for
[OpenAI Builder Week](https://openai.com/build-week/). That context does not
imply acceptance, judging outcome, partnership, or OpenAI endorsement.

## Core rule

```text
Preserve evidence.
Project without replacing it.
Expose freshness.
Route back to sources.
Review before promotion.
```
