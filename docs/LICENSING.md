# Licensing review and publication gate

## Current status

The repository root has no confirmed `LICENSE`. That blocks public visibility
and release publication. No root license should be inferred from the package
subdirectory or from dependency licenses.

The proposed root license is Apache License 2.0 because the authored MCP owner
source already uses Apache-2.0 and the projected package includes the exact
owner license. The repository owner must explicitly accept or replace this
proposal before a root `LICENSE` is added.

## Dependency and artifact review

| Surface | License or status | Distribution posture |
| --- | --- | --- |
| Projected `aoa-session-memory-mcp` source | Apache-2.0 | Includes a byte-identical copy of the `abyss-stack` owner license. |
| Python MCP SDK | MIT | Runtime dependency; its upstream license and installed 1.28.1 metadata agree. |
| PyPA `build`, setuptools, pytest, jsonschema, and PyYAML | MIT | Build/test dependencies; not copied into the source tree. |
| Python standard library | PSF license family | Runtime platform dependency; not vendored. |
| `actions/checkout` and `actions/setup-python` | MIT | CI actions pinned by commit; executed by GitHub Actions, not redistributed here. |
| Synthetic demo | Original repository fixture | Invented text and identifiers; no owner transcript or third-party media. |
| Package export manifest and generated indexes | Repository/owner generated output | Provenance and source digests are retained; no external snippets were identified. |

No upstream `NOTICE` file exists in the current Apache-2.0 MCP owner source,
and the reviewed MIT dependencies do not require a project `NOTICE`. Add one
only if a future copied dependency or owner notice creates that obligation.

Primary license references:

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/blob/main/LICENSE)
- [PyPA build](https://github.com/pypa/build/blob/main/LICENSE)
- [pytest](https://github.com/pytest-dev/pytest/blob/main/LICENSE)
- [jsonschema](https://github.com/python-jsonschema/jsonschema/blob/main/COPYING)
- [PyYAML](https://github.com/yaml/pyyaml/blob/main/LICENSE)
- [actions/checkout](https://github.com/actions/checkout/blob/main/LICENSE)
- [actions/setup-python](https://github.com/actions/setup-python/blob/main/LICENSE)

This inventory is an engineering publication gate, not legal advice.
