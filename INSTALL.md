# Portable installation

The repository can operate as a standalone portable bundle or as the source
for a workspace-local `.aoa/` installation. Installation copies the kernel; it
does not transfer owner authority, live session history, or host configuration.

## Install shapes

### Standalone source

In a standalone checkout, the repository root is the AoA root. Source tests,
portable validation, and export operate directly on that root. Runtime session
capture is optional.

### Workspace-local root

In a project workspace, the kernel lives under `.aoa/`. Generated archives,
indexes, search and graph stores, and diagnostics then belong to that workspace
installation. Local AoA or Tree of Sophia meaning remains an overlay outside
the portable kernel.

## Copy boundary

Portable export includes authored root documents, configuration, schemas,
hooks, manifests, maps, scripts, skills, stats, and tests. It excludes session
archives and generated runtime stores by default.

An explicit session-inclusive export is a private evidence operation, not a
normal package release. Such an export must preserve raw-evidence handling and
must never be treated as public-safe merely because the kernel is portable.

## Existing installations

Kernel upgrades preserve existing session directories and rebuild the
registry/index views from those archives. Forced export may replace portable
files while preserving repository-owned `.git`, `.github`, and `kag` surfaces.
It must not silently delete runtime evidence.

## Hook rendering

The committed hook file is a placeholder example. Installation renders a
configuration for the chosen workspace and AoA roots. Host-wide hook placement
and native Codex hook trust are explicit user operations.

Project and user hooks may both run. Archive writes are idempotent for the same
raw source, while duplicate receipts remain possible and visible.

## User skills

The global session-memory router and the evidence route are approved for
explicit user-level installation. Other bundle skills stay local as focused
procedures. User skill links are host state and are not part of portable source
readiness.

## Validation after install

Source validation, installed-root health, and completion audit are different
questions. A clean portable bundle may validate without runtime sessions;
doctor evaluates the selected installation; audit can still report missing
live grounding.

For the Codex adapter, grounding validates the effective context and
auto-compaction contract. Explicit configuration wins when present; otherwise
the command resolves the selected model defaults through `codex debug models`
instead of requiring redundant local overrides.

The executable CLI owns exact export, install, hook-rendering, skill-install,
validate, doctor, and audit syntax. Inspect the selected subcommand help in
`scripts/aoa_session_memory.py`. Short focused check routes live in the nearest
`AGENTS.md` rather than in this document.
