# Build and release

## Build without changing the checkout

Install the MCP runtime and public build dependencies in an external virtual
environment, then use the repository helper:

```bash
python -m venv /tmp/aoa-session-memory-build
/tmp/aoa-session-memory-build/bin/pip install \
  'mcp>=1.28,<2' 'build>=1.3,<2' 'jsonschema>=4.25,<5'
/tmp/aoa-session-memory-build/bin/python scripts/build_mcp_package.py \
  --outdir /tmp/aoa-session-memory-artifacts \
  --staging-root /tmp/aoa-session-memory-stage \
  > /tmp/aoa-session-memory-build.json
```

The helper validates the package projection, derives `SOURCE_DATE_EPOCH` from
the owner commit recorded in the package manifest, builds in external staging,
canonicalizes sdist ownership and timestamps, hashes both artifacts, and fails
if the package source tree changes.

For a reproducibility check, build twice into two new empty output/staging
directories and compare the ordered `artifacts` arrays in the JSON receipts.
Both wheel and sdist must be byte-identical in the fixed build environment.

## Install the artifact

```bash
python -m venv /tmp/aoa-session-memory-artifact
/tmp/aoa-session-memory-artifact/bin/pip install \
  /tmp/aoa-session-memory-artifacts/aoa_session_memory_mcp-*.whl
/tmp/aoa-session-memory-artifact/bin/aoa-session-memory-mcp --help
/tmp/aoa-session-memory-artifact/bin/aoa-session-memory-mcp-server --help
```

Use `examples/synthetic/bootstrap_demo.py` and
`examples/synthetic/mcp_protocol_smoke.py` for the standalone protocol proof,
then `examples/synthetic/negative_case_matrix.py` for installed-package root,
transport, bearer, drift, and stale-evidence refusal cases.

## Maintainer projection route

Package changes originate in the clean committed
`abyss-stack/mcp/services/aoa-session-memory-mcp` owner source. The owner
exporter uses a declared allowlist, staging, atomic publication, file digests,
and `--check` drift detection. A downstream release must never contain a manual
package fix absent from the owner.

## Release gates

A release candidate requires:

1. owner/package export and manifest parity;
2. green Python 3.11 and 3.14 standalone CI;
3. byte-reproducible wheel and sdist;
4. clean wheel installation and stdio MCP protocol smoke;
5. a blocking-clean current tree and a reviewed retained-history inventory;
6. confirmed root license and dependency review;
7. integrated foundation handoff and final generated-index parity;
8. an explicit maintainer publication decision.

GitHub visibility, GitHub Release publication, PyPI upload, systemd changes,
Codex registration changes, and live MCP deployment are separate operations.
This build route performs none of them.
