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
hooks, manifests, maps, scripts, skills, stats, and tests. It always excludes
session archives, raw evidence, generated runtime stores, and diagnostics.

Hidden atomic-publish scratch files marked with `.tmp` are transient writer
state, not portable source. Export excludes them while continuing to fail on a
missing or unreadable stable authored file. This permits a live source export
to overlap an atomic map publication without copying partial bytes or
requiring the runtime maintenance lease.

The legacy `--with-sessions` spelling is rejected before target mutation.
Private evidence transfer is a distinct owner-to-owner migration operation,
not a portable export.

Every export runs the bounded `portable-public-safety-audit`. Credential-like
values, private host paths, runtime databases, diagnostics, non-empty session
registries, or an exhausted scan budget make the export non-admissible. The
audit reports only issue classes, counts, and relative file paths; it never
prints matched credential or host values.

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

An install created with `--no-tests` is a supported runtime shape. The owner
installer records that choice in a runtime-only install profile. `doctor`
accepts an absent test tree only when that profile is valid and bound to the
selected workspace and AoA root; accidental test-tree loss still fails.
Source/export completion and standalone release proof require the full
portable test suite.

For the Codex adapter, grounding validates the effective context and
auto-compaction contract. Explicit configuration wins when present; otherwise
the command resolves the selected model defaults through `codex debug models`
instead of requiring redundant local overrides.

The executable CLI owns exact export, install, hook-rendering, skill-install,
validate, doctor, and audit syntax. Inspect the selected subcommand help in
`scripts/aoa_session_memory.py`. Short focused check routes live in the nearest
`AGENTS.md` rather than in this document.
