# Synthetic standalone demo

This fixture contains invented identifiers, calls, failures, and decisions. It
does not contain owner sessions or edited private transcripts.

Build a complete demo root in a new temporary directory:

```bash
python examples/synthetic/bootstrap_demo.py --destination /tmp/aoa-session-memory-demo
```

The bootstrap uses the repository's portable installer, then archives one
synthetic transcript and builds local SQLite search, atlas, graph, entity
registry, and readiness projections. The destination must be absent or empty;
the command never writes runtime sessions into this repository.

After installing `packages/aoa-session-memory-mcp`, point either entrypoint at
the demo root:

```bash
aoa-session-memory-mcp --workspace-root /tmp/aoa-session-memory-demo search DEMO-ANCHOR-42 --limit 5
aoa-session-memory-mcp --workspace-root /tmp/aoa-session-memory-demo usage-chain query_component --kind mcp_tool --limit 4
aoa-session-memory-mcp --workspace-root /tmp/aoa-session-memory-demo task-episodes latest --limit 5
aoa-session-memory-mcp --workspace-root /tmp/aoa-session-memory-demo graph-neighborhood synthetic-catalog-mcp --kind mcp
```

Returned packet summaries are navigation evidence. Raw transcript, segment,
and current external owner evidence remain stronger.

Run a real MCP stdio handshake after installing the package:

```bash
python examples/synthetic/mcp_protocol_smoke.py \
  --workspace-root /tmp/aoa-session-memory-demo \
  --cwd /tmp
```

The smoke lists tools, resources, templates, and prompts; verifies every tool's
read-only annotations; exercises exact search, usage, episode, graph,
freshness, missing-evidence, and causal-claim boundaries; opens one raw ref;
and proves the archive file digests are unchanged when the server exits.

Run the installed-package negative matrix in a separate scratch root:

```bash
python examples/synthetic/negative_case_matrix.py \
  --workspace-root /tmp/aoa-session-memory-demo \
  --scratch-root /tmp/aoa-session-memory-negative
```

It checks missing, invalid, explicit, conflicting, symlinked, space-bearing,
and Unicode roots; disabled optional providers; no host-only runtime helper;
malformed, non-loopback, and unavailable HTTP; missing bearer authentication;
unsupported transport; package manifest drift; and stale projection refusal.
Its receipt contains only case names and bounded status signals. The primary
demo archive must remain byte-unchanged.
