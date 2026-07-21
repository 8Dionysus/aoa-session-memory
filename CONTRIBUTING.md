# Contributing

Contributions should preserve evidence, provenance, freshness, and owner
boundaries. A green test is necessary, but it does not make a generated packet
or MCP summary authoritative.

## Set up an external development environment

Keep virtual environments and build output outside the checkout so the same
tree can pass the public-safety audit:

```bash
python -m venv /tmp/aoa-session-memory-dev
/tmp/aoa-session-memory-dev/bin/pip install \
  'mcp>=1.28,<2' 'build>=1.3,<2' 'jsonschema>=4.25,<5' \
  'pytest>=8,<10' 'PyYAML>=6,<7'
```

Run the standalone gates:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/aoa-session-memory-dev/bin/python \
  -m pytest -q -p no:cacheprovider tests/test_session_memory.py \
  tests/test_public_tree_audit.py tests/test_git_history_audit.py
/tmp/aoa-session-memory-dev/bin/python packages/aoa-session-memory-mcp/scripts/release_check.py
/tmp/aoa-session-memory-dev/bin/python scripts/audit_public_tree.py --root . --fail-on blocking
```

## Respect the MCP projection boundary

`abyss-stack` owns the authored MCP implementation. The directory
`packages/aoa-session-memory-mcp/` is a generated, manifest-checked projection;
do not patch it independently. MCP behavior changes must first land in the
owner source and then arrive through the declared exporter. Repository-owned
examples, CI, release instructions, and public landing documentation remain
outside that directory.

## Pull requests

- Add the smallest test that proves the changed contract.
- Use synthetic fixtures; never commit real session evidence or host state.
- Preserve raw, segment, session, and freshness refs in derived packets.
- State which owner surface changed and which checks passed.
- Run the current-tree audit before requesting review.
- Treat the full-history audit as a publication gate; an ordinary branch test
  cannot prove that every remote ref or GitHub-hosted surface was fetched.
- Do not include wheels, sdists, virtual environments, databases, caches, logs,
  diagnostics, or generated runtime sessions.

Changes to durable authority or architecture belong in the repository decision
lane. Generated decision and KAG indexes should be refreshed once after the
authored source is stable, not mixed through every logical commit.
