# Package Projection Contract

This directory is owned by `abyss-stack`. It defines the one-way export of the
authored `aoa-session-memory-mcp` package into the standalone
`aoa-session-memory` repository under `ABYSS-STACK-D-0084`.

The downstream package is a committed distribution read model, not a second
implementation owner. Change implementation, tests, package metadata, and this
policy here first; then export from a clean committed owner checkpoint.

## Export

From the `abyss-stack` repository root:

```bash
python mcp/services/aoa-session-memory-mcp/scripts/export_standalone_package.py \
  --source-root mcp/services/aoa-session-memory-mcp \
  --destination /path/to/aoa-session-memory/packages/aoa-session-memory-mcp
```

The exporter copies only the declared allowlist into a staging directory,
builds a deterministic catalog and manifest, validates the candidate, and
atomically replaces the bounded destination. It refuses a dirty owner checkout,
an unexpected source root, symlinks, unsafe destination paths, and unknown files
in an existing projection.

Use check mode for owner/downstream parity without writing:

```bash
python mcp/services/aoa-session-memory-mcp/scripts/export_standalone_package.py \
  --source-root mcp/services/aoa-session-memory-mcp \
  --destination /path/to/aoa-session-memory/packages/aoa-session-memory-mcp \
  --check
```

After export, the downstream package validates itself without `abyss-stack`:

```bash
python packages/aoa-session-memory-mcp/scripts/validate_package_projection.py
```

Neither route installs, deploys, restarts, or registers an MCP service.
