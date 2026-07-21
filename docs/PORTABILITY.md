# Portability and dependency boundary

The standalone path is a local Python, SQLite, filesystem, and stdio MCP
application. OS Abyss can add accelerators and managed deployment, but it is
not required to install the package, build the synthetic demo, query evidence,
or run the required CI lane.

## Dependency census

| Relationship | Class | Portable behavior |
| --- | --- | --- |
| Python 3.11 or newer | core runtime | Required by the package metadata and tested in standalone CI. |
| Python standard library, including SQLite and TOML readers | core runtime | Owns local archive reads, root discovery, and portable retrieval. |
| `mcp>=1.28,<2` | core runtime | Provides the MCP server/client protocol surface. |
| A marker-valid repository root or `workspace/.aoa` | core data input | Selected by explicit argument, explicit environment, or marker-based discovery; no host path fallback exists. |
| `build`, `pytest`, and `jsonschema` | test/build only | Declared in the package `test` extra; not imported by the running server. |
| `PyYAML` | test/validation only | Used by repository-level validation, not by the MCP package runtime. |
| `abyss_machine_nervous` | optional integration | Disabled in `config/search-providers.json`; absence is reported as disabled or unavailable and portable SQLite remains authoritative. |
| `abyss_stack_rag` | optional integration | Disabled future service; it cannot replace raw or indexed `.aoa` evidence. |
| `abyss-machine resource launch` routes | optional orchestration | Returned only as bounded next-action plans for expensive expansion routes; the MCP does not execute them and ordinary routes do not require the command. |
| Authenticated loopback Streamable HTTP | optional deployment | The portable default is stdio. HTTP requires an explicit loopback bind and bearer source. |
| systemd credentials and service units | system deployment configuration | Stack-owned launch policy; no unit or credential is shipped as a portable default. |
| `/srv` workspace and launch paths | system deployment configuration | Supplied by an explicit stack-owned profile. Generic discovery does not assume them. |
| `aoa-kag`, `aoa-stats`, `aoa-skills`, and `aoa-evals` | optional ecosystem validation | Checked only by the manual/scheduled ecosystem workflow, never by required standalone CI. |
| Host process, Codex config, and HTTP fixtures | test fixture | Synthetic values exercise deployment diagnostics without becoming defaults. |
| Naming goldens, generated KAG indexes, and decision indexes | generated or historical reference | Rebuildable/public source projections; they do not configure the running MCP. |

## Portable defaults

- `aoa-session-memory-mcp-server` starts stdio unless HTTP is explicitly
  selected.
- Root discovery accepts only explicit roots or marker-valid standalone and
  workspace-local roots.
- Search uses the local `portable_sqlite` provider by default.
- Optional providers are accelerators. Their absence never removes raw,
  segment, session, or freshness evidence.
- MCP calls are read-only or plan-only. They do not run archive maintenance,
  export, repair, reindex, or orchestration commands.

The system deployment remains an `abyss-stack` responsibility. Its explicit
workspace, credential, transport, Python, and process-lifecycle profile is not
part of this repository's standalone contract.

## Boundary checks

Run the repository-local gates without sibling repositories:

```bash
python scripts/audit_public_tree.py --root . --fail-on blocking
python packages/aoa-session-memory-mcp/scripts/validate_package_projection.py
python packages/aoa-session-memory-mcp/scripts/release_check.py
```

The optional ecosystem workflow separately checks stronger owner contracts and
OS-specific profiles when their repositories and credentials are available.
