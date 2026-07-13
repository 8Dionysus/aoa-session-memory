# Session-memory readiness model

This file defines what readiness means for `aoa-session-memory`. It is not a
dated host report, release log, maintenance ledger, or substitute for current
diagnostics. Current state is computed by the CLI from the selected source or
runtime root.

## Readiness layers

### Portable source readiness

A portable source bundle is ready when its required authored files, schemas,
fixtures, hook example, skills, maps, manifests, local stats port, and tests are
present and internally valid. The bundle may intentionally contain no session
archive, search database, graph database, live hooks, or host-local evidence.

Portable readiness proves that the kernel can be installed and exercised. It
does not prove a live host is wired, an archive is current, or every scenario
can execute without runtime evidence.

### Installation readiness

An installed `.aoa` root is ready when portable contracts agree with rendered
workspace paths, required hook events and approved skills are available, and
the runtime topology is valid for the selected installation mode.

Host hook trust, user-level links, optional providers, timers, and resource
policy are installation facts. They remain outside the portable source bundle.

### Archive readiness

An archive is ready for evidence routing when raw availability or an explicit
raw-unavailable diagnostic is recorded, compaction topology and segment
topology agree, indexes match their sources, and returned packets retain raw,
segment, session, or receipt refs.

Recent live tails may be deferred until the quiet window. That posture must be
visible and must not be collapsed into either corruption or a current claim.

### Projection readiness

Search, atlas, entity, graph, and rollup projections are ready when their
schema and source fingerprints are current for the scope being queried. A
bounded stable subset is not an archive-wide proof. Missing or stale generated
stores route to repair without changing raw authority.

### Review readiness

Naming or distillation is ready only when the candidate has an evidence-bounded
scope, adequate refs, explicit coverage, and a named stronger owner for any
promotion. Generated classifiers and scenario checks cannot review their own
claims.

## Portable scenario posture

The source-owned live-scenario corpus mixes cases that need a real archive with
cases backed by reviewed privacy-safe fixtures. A clean portable bundle runs
only the latter and reports the rest as skipped. Executed, skipped, failed, and
actionable-gap counts remain separate.

`stats/` exposes a revision-bound ratio of reviewed fixture-backed cases to all
declared corpus cases. That statistic measures portable fixture coverage only;
it does not measure route correctness, memory quality, production adoption, or
live readiness.

## Current evidence routes

- `validate` checks deterministic pipeline invariants.
- `doctor` checks a selected installation and its generated topology.
- `audit` checks objective-level completion and may remain incomplete.
- `maintenance-status` reports current projection, live-tail, lock, and
  resource posture.
- `live-scenario-corpus list` describes source cases without claiming runtime
  success.
- `live-scenario-corpus check` separates executed proof from allowed skips.

Exact syntax belongs to CLI help. Current results belong in generated JSON
diagnostics or the active session, not in this source document.

## Completion boundary

No single green test, validator, doctor packet, scenario corpus result, or
statistic proves the whole system ready. A completion claim must name its
scope, current evidence, skipped or unknown surfaces, live/reference posture,
and stronger authority routes.
