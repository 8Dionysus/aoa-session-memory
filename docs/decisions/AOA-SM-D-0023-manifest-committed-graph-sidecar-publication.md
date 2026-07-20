# Manifest-Committed Graph Sidecar Publication

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0023
- Original date: 2026-07-19
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: graph indexing, incremental maintenance, atomic publication, partial-failure recovery, freshness
- Projection layers: graph store, graph sidecar, graph index, graph readers
- Guard families: manifest commit, generation identity, dependency pinning, content digest, stale abstention, rollback
- Posture: accepted

## Context

The SQLite graph store and the optional `nodes.jsonl` and `edges.jsonl`
sidecar have different publication boundaries. Incremental maintenance
previously exported those files while the graph transaction was still open.
The export helper also committed the connection itself. A dependency change
detected immediately afterward could therefore leave the database mutation
committed, or replace one or both sidecar files while the maintenance packet
reported a rollback.

Per-file temporary renames prevent a reader from observing a partly written
file, but they do not prove that two files and their SQLite source belong to
one generation. An old `index.json` also cannot authorize newly replaced
sidecar bytes.

## Options Considered

- Export the sidecar before committing SQLite and rely on a later rollback.
  Rejected because filesystem renames are outside the SQLite transaction and
  the export helper must not commit its caller's mutation.
- Commit SQLite and replace the sidecar files without a shared manifest.
  Rejected because interruption between file renames leaves no verifiable
  cross-file generation boundary.
- Make the sidecar the live graph store. Rejected because it is an optional
  offline and publication snapshot; the normalized SQLite store and stronger
  source contributions own generated graph state.
- Stage the sidecar privately, commit the verified graph transaction, publish
  the staged files, and atomically write a content-bearing manifest last.

## Decision

Graph sidecar publication uses `graph/index.json` as a logical commit
manifest. Sidecar nodes and edges are rendered to private files without
changing the published snapshot or committing the caller's SQLite
transaction.

Incremental maintenance rechecks its pinned entity-registry dependency and
commits the graph store before publishing staged sidecar files. Full rebuild
continues to publish its staged SQLite store first. In both routes,
`graph/index.json` is written only after both sidecar artifacts are present.
The manifest records their names, byte sizes, SHA-256 digests, and the
committed graph store's update identity, generation, registry dependency, and
semantic digest.

Readers validate the manifest against the files and store before accepting a
sidecar. A missing or incompatible manifest, file mismatch, store mismatch,
dependency mismatch, or semantic-digest mismatch rejects the complete
sidecar. The route then uses the live graph store or a bounded source-backed
fallback. A failed publication removes partial optional artifacts rather than
leaving navigation files that can look current.

## Rationale

Writing one small manifest last turns three independently atomic files into
one verifiable projection generation. It preserves SQLite as the graph
read-model owner, prevents a helper from crossing its transaction boundary,
and makes interruption observable without requiring an unsafe multi-file
rollback protocol.

Content identities protect against same-size replacement and manual damage.
The store semantic digest and dependency identity prevent a byte-consistent
sidecar from being reused after an incremental graph commit or registry
change. Rejection is preferable to serving a mixed snapshot; raw, segment,
session, and graph-source evidence remain available through stronger routes.

## Consequences

- Positive: a sidecar becomes answer-bearing navigation only after a
  verifiable manifest-last commit.
- Positive: pre-commit failure leaves both the last-good store and sidecar
  unchanged; post-commit export failure leaves the store usable and the
  optional sidecar explicitly absent or rejected.
- Positive: tampering, interrupted rename, stale store identity, and registry
  drift have distinct rejection reasons.
- Tradeoff: full sidecar admission hashes the exported files and may calculate
  a graph semantic digest; export is therefore an offline or maintenance
  operation rather than an interactive route.
- Tradeoff: legacy sidecars without a commit manifest require regeneration or
  a source-backed fallback.
- Follow-up: measure real export cost and verify the same manifest fields in
  portable and MCP packets without exporting runtime graph data.

## Boundaries

This decision does not make the sidecar, manifest, graph store, or MCP
response source truth. It does not provide a cross-filesystem atomic rename,
nor does it claim that a successfully published graph is semantically
correct. It provides an admission boundary: readers can distinguish one
complete generated snapshot from partial or stale files.

This decision does not rewrite raw evidence, require sidecar export for normal
SQLite graph retrieval, or convert graph adjacency into causality, usage,
ownership, or consequence.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Run injected pre-commit staging failure, post-commit publish failure, manifest
tamper, restart, deterministic double rebuild, and real graph freshness
checks. Then regenerate and audit source, standalone, skill, and MCP consumers
through the owner export route.

## Verification

Focused tests prove that an uncommitted staged sidecar never replaces the
published files, rollback restores the previous graph semantic digest,
temporary stage files are removed, and file tampering rejects the sidecar.
The broader graph suite covers rebuild determinism, dependency rollback,
incremental maintenance, graph freshness, pruning, storage, and retrieval.
Real sealed-lab rebuild and portable/runtime parity remain separate completion
gates.

## Review Amendment — 2026-07-20

A real store-only rebuild exposed an uncovered publication state: the graph
store was current and had no dirty source contributions, while its optional
sidecar required regeneration. `graph-maintenance --export-sidecar` completed
its deep source scan but skipped export because the mutation candidate pool
was empty. Forcing a source dirty or repeating the full graph rebuild would
misrepresent semantic work and spend resources without changing graph
content.

A clean current store may therefore execute a sidecar-only manifest commit
under the same maintenance lease and pinned registry dependency. It stages and
hashes nodes and edges, publishes the manifest last, and verifies the store
semantic digest exactly as the mutation-bearing route does. The result exposes
`sidecar_exported=true` and `semantic_progress=false`; process completion or
sidecar publication must not be reported as graph semantic advancement.

This clarification does not permit export from a stale or incompatible graph
store and does not make the sidecar mandatory for normal SQLite-backed
retrieval. Focused regression starts from a current store-only build, exports
with an empty dirty queue, validates file content and store semantics, and
then confirms that SQLite retrieval remains the live route. A matching
negative regression changes only the store generation identity while keeping
the source queue clean and proves that sidecar publication is refused rather
than laundering that incompatible store as current.
