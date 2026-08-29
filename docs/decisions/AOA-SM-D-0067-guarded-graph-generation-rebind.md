# Guarded Graph Generation Rebind

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0067
- Original date: 2026-08-12
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: graph indexing, generation identity, migration, freshness
- Projection layers: graph source contributions, graph store, entity registry
- Guard families: exact predecessor, source attestation, materialization equivalence, atomic rebind
- Posture: accepted

## Context

Projection-scoped producer identity correctly invalidates graph rows when code
inside the declared graph producer ranges changes. Some changes alter only the
execution shape used to derive the same contribution and aggregate semantics,
such as replacing repeated per-source aggregate refresh with one set-wise
refresh. Treating that transition as an unconditional full rebuild discards a
complete content-addressed graph even when its schemas, policies,
dependencies, contributions, and query-bearing materialization remain valid.

Live incremental maintenance can also make the store temporarily mixed: newly
processed sources carry the current producer identity while untouched sources
retain the exact predecessor. Requiring one stored generation before any proof
turns successful bounded progress into another reason for a global rebuild.

## Options Considered

- Require a full graph rebuild after every producer-range change. Rejected as
  the only route because it couples implementation-only changes to all source
  history and repeats already-attested contribution work.
- Rewrite generation and dependency columns directly. Rejected because a
  metadata update alone does not prove graph content or registry
  materialization compatibility.
- Admit any predecessor with matching schema and policy fields. Rejected
  because broad structural equality can hide a real producer semantic change.
- Declare one exact predecessor-to-current pair and exact previous source,
  then rebind only after the existing complete materialization and content
  proofs pass.

## Decision

A projection-scoped graph generation may cross to the current generation only
when the exact ordered pair is declared in source and the supplied previous
producer file has the declared whole-file SHA. The transition reconstructs the
predecessor graph identity from that source and the current non-producer
identity fields; the reconstruction must equal the stored identity exactly.

The graph registry rebind proof evaluates every distinct source-generation
group independently. A mixed store is admissible only when every group is
either exactly current or passes the declared predecessor proof, every source
has a dependency binding, static graph versions match, and the complete
registry materialization proof has no unhandled mismatch. The existing
query-bearing content digest, process-loaded source guard, dependency guard,
single SQLite transaction, rollback path, and post-commit currentness proof
remain mandatory. Successful application restamps all source and metadata
bindings together; it does not leave a persistent compatibility reader mode.

## Rationale

The exact pair and full-source attestation make this a bounded reviewed
migration rather than schema-level trust. Reconstructing the stored identity
proves that all graph identity fields outside the declared producer contract
are unchanged. Complete materialization and content digests prove the stored
graph rather than assuming that the implementation change was harmless.
Per-group admission preserves useful incremental progress without weakening
the final atomic publication boundary.

## Consequences

- Positive: an execution-only producer change can retire generation debt in
  one guarded transaction instead of rebuilding all historical sources.
- Positive: mixed current and exact-predecessor source rows no longer block the
  proof solely because bounded maintenance already made progress.
- Positive: unknown generation pairs, wrong previous source, malformed
  identities, missing bindings, static-version drift, and materialization
  mismatches still fail closed.
- Tradeoff: every intentional compatible transition requires a reviewed exact
  pair and previous-source SHA in current source.
- Follow-up: remove obsolete transition entries after current stores have been
  restamped and portable migration fixtures no longer need them.

## Boundaries

This decision does not declare arbitrary producer changes semantically
compatible, make generated graph data an authority over raw sessions, admit
unknown dependency epochs, or bypass source freshness. It does not repair an
actively growing session whose preserved raw capture is ahead of its session
projection. It does not authorize GitHub publication.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Run `graph-registry-rebind` first without `--apply` using the exact previous
producer source. Apply only the emitted ready plan under owner resource and
maintenance controls, then verify source-generation distribution, content
digest invariance, SQLite integrity, graph freshness, and portable parity.

## Verification

Focused regressions cover exact-pair admission, missing or altered previous
source refusal, and mixed current/predecessor source groups. Live proof must
record the complete preflight, unchanged query-bearing content digest, atomic
source-row rebind, post-commit current generation, and SQLite integrity. Run
decision-index regeneration/check, `py_compile`, focused pytest, portable
export validation, and `git diff --check` before local landing.
