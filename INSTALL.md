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

Kernel upgrades preserve existing session directories and the generated
projection overlay. Changed producer identities mark only their owned stages or
components dirty; normal catch-up reuses unchanged raw blocks, segments,
classification summaries, and task-episode shards. A full rebuild is reserved
for explicit bootstrap, migration, or deep-repair cases. Forced export may
replace portable files while preserving repository-owned `.git`, `.github`, and
`kag` surfaces.
It must not silently delete runtime evidence. `export-bundle --force` therefore
fails closed before mutation when its target contains a runtime install
profile, archived sessions, or generated runtime stores. Upgrade an installed
root with `install --force`; reserve forced export for a clean portable target.

Runtime install upgrades replace authored map templates but transactionally
overlay the existing generated atlas indexes, entry files, projection state,
and entity registry afterward. A failed overlay restores the previous map
tree. Generated projections remain non-authoritative and may still be marked
dirty by the new producer generation; preservation prevents an upgrade from
turning ordinary incremental catch-up into accidental bootstrap loss.

## Hook rendering

The committed hook file is a placeholder example. Installation renders a
configuration for the chosen workspace and AoA roots. Host-wide hook placement
and native Codex hook trust are explicit user operations.

Project and user hooks may both run. Archive writes are idempotent for the same
raw source, while duplicate receipts remain possible and visible.

## Systemd unit rendering

Fresh capture, discovery/stable sweep, and persistent retry dispatch are
separate owner lanes. The fresh-capture unit is capture-watch-only;
discovery/stable projection runs in a separately named resource-gated sweep
unit; and the retry timer invokes the bounded owner dispatcher, which performs
resource admission for each child. Render them into an explicitly chosen
target when a runtime owner is ready to review deployment:

```bash
python3 scripts/aoa_session_memory.py render-systemd-units \
  --workspace-root /absolute/path/to/workspace \
  --aoa-root /absolute/path/to/workspace/.aoa \
  --output-dir /absolute/path/to/user/systemd \
  --force
```

An installed-root upgrade can render the same six named files with
`install --systemd-unit-dir <target> --force`: capture service/timer, sweep
service/timer, and retry-dispatch service/timer. The installer never enables,
starts, reloads, or trusts a unit, and it never changes a live systemd
directory unless that directory is explicitly supplied by the caller. The
rendered capture contract must remain one `capture-watch` `ExecStart`; the
resource-gated sweep owns transcript discovery and stable projection; and the
retry unit must contain only the bounded `auto-maintenance-retry` dispatcher,
not capture, sweep, or projection-catchup work.

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
installer records that choice in a runtime-only install profile. The profile
also records the source root, local source commit and tree, producer-script
SHA-256, install timestamp, and a deterministic install identity. `doctor`
accepts an absent test tree only when that profile is valid and bound to the
selected workspace and AoA root; missing or incomplete source provenance is
not admitted. A `working_tree` source status is explicit branch-trial
evidence; current production activation must use a clean canonical checkout.
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

After installation, `projection-status` and `freshness-vector <session>` expose
capture, live-overlay, stable-projection, and downstream-consumer progress.
`auto-maintenance hot --apply` remains the bounded event-driven queue producer;
the source-rendered retry timer invokes `auto-maintenance-retry`, while
`projection-catchup` and deep maintenance remain explicit child/repair routes.

For a supported global exact query, a SQLite projection timeout or missing
index is followed by the same bounded recent live/raw fallback used by the
ordinary search route. Recovered refs are usable bounded navigation evidence,
not a global absence claim or proof that every downstream consumer is current;
the fallback never edits queues, indexes, or raw evidence.
