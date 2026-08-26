# Source Install Provenance and Bounded Global Exact Recovery

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0097
- Original date: 2026-08-25
- Owner surfaces: `scripts/aoa_session_memory.py`, `INSTALL.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: source lineage, installation, query fallback, freshness
- Projection layers: runtime install profile, portable SQLite search, bounded raw navigation
- Guard families: local source identity, install admission, query timeout, bounded fallback
- Posture: accepted

## Context

The source-rendered retry and publication paths can be active while a runtime
install profile remains detached from the source that produced its executable.
That leaves byte equality as only a weak observation: the install has no
commit, tree, script digest, or installation timestamp to bind it to a local
source identity. Separately, the supported global exact search route can time
out in SQLite and return before invoking the existing bounded recent raw
fallback. An ordinary agent then receives neither a usable ref nor a clear
bounded recovery route under the same pressure that caused the timeout.

## Options Considered

- Continue recording only install shape and generated time. Rejected because
  it cannot distinguish a current source install from an untraceable byte copy.
- Treat a timeout as success or run an unbounded rebuild/retry. Rejected because
  transport success is not freshness and an unbounded repair violates query
  budgets and separate queue ownership.
- Bind each runtime profile to local source identity and route eligible global
  exact failures through the existing bounded recent raw reader. Accepted.

## Decision

The runtime install profile uses schema v2 and records the local source root,
source commit, source tree, producer-script SHA-256, `installed_at`,
`source_worktree_clean`, `source_identity_status`, and a deterministic
`install_id`. A local Git identity is read without remote access. Missing
commit/tree/script identity fails closed before install mutation. A dirty
source is recorded as explicit `working_tree` branch-trial provenance; only a
clean source records `current` production provenance. Doctor validates the
complete profile and nested identity rather than treating a generated time as
source currentness.

When a supported global exact search times out or its published SQLite index is
missing, the normal session-scoped recovery is attempted first and the result
then passes through the existing bounded recent live/archive exact fallback.
If bounded raw evidence is recovered, the result exposes refs, the selected
fallback route, and the original timeout or missing-index state while marking
the query result usable as bounded navigation evidence. If no bounded evidence
is recovered, the query remains an honest unresolved/error result. The route
does not claim global absence, semantic consumer completion, or global
freshness, and it performs no mutation.

## Rationale

The profile fields bind the executable bytes to a locally inspectable source
identity and preserve a truthful distinction between a clean canonical
install and a branch trial. The pre-mutation gate prevents an untraceable
runtime install from becoming the next live source. Reusing the bounded global
fallback closes the control-flow gap without adding another reader or writer;
it preserves the established raw-evidence authority and budget boundary.

## Consequences

- Positive: runtime health can reject a profile whose source lineage is
  missing, tampered, or internally inconsistent.
- Positive: a supported exact query can return current bounded refs after an
  index timeout or absence when the recent raw route has evidence.
- Tradeoff: old v1 profiles require a source-authorized reinstall, and dirty
  source installs remain explicitly branch-trial rather than currentness proof.
- Follow-up: export/admission and live activation must report source, artifact,
  profile, unit, and runtime identities separately.

## Boundaries

This decision does not make a profile, timer, retry receipt, fallback result,
or query `ok` flag into proof that all session consumers or global recall are
current. It does not authorize manual queue edits, catch-up, reindex, retry,
sweep, raw reads outside bounded routes, live activation, or remote/GitHub
mutation. It does not change observer, wake, return, Goal, or task-DAG
machinery.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `INSTALL.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Run source compilation, the install/profile and timeout regressions, decision
index validation, the full owner suite, portable export/admission, and the
separate runtime activation and semantic acceptance routes.

## Verification

Focused tests cover profile provenance, fail-closed profile validation, and a
global exact timeout recovered through bounded recent raw evidence. Source
identity, export safety, live activation, and fresh natural successor evidence
remain separate claims in the owner report and handoff.
