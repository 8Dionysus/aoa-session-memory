# Security policy

## Reporting a vulnerability

Use a [private GitHub security advisory](https://github.com/8Dionysus/aoa-session-memory/security/advisories/new)
for vulnerabilities, credential exposure, private transcript exposure, unsafe
path handling, MCP authentication bypass, or a history object that would be
unsafe to publish.

Do not open a public issue containing a secret, raw session text, a bearer
value, private host topology, or a working exploit against a live deployment.
Include only the minimum reproduction material needed to establish the issue.
Synthetic evidence is preferred.

Ordinary bugs and feature requests can use the public issue tracker once the
repository is public.

## Security boundaries

- Raw transcripts and resolvable archive refs are stronger evidence than MCP
  summaries, but they may also contain private material.
- The MCP package is a read-only or plan-only access plane. A route that writes,
  repairs, reindexes, exports, or promotes memory is a contract violation.
- stdio is the standalone default. Optional Streamable HTTP must remain
  loopback-only and bearer-authenticated.
- Generated search, atlas, graph, readiness, and diagnostic data are
  rebuildable projections, not proof authority.
- Public examples must be invented synthetic data, never edited owner
  transcripts.

See the package [threat model](packages/aoa-session-memory-mcp/docs/THREAT_MODEL.md),
[public-tree audit](scripts/audit_public_tree.py), [full-history
inventory](scripts/audit_git_history.py), and [publication
boundary](docs/PUBLICATION.md) for the current checks and residual-risk posture.

Security fixes target the current maintained branch and any explicitly
supported release. No public stable release is implied by this policy.
