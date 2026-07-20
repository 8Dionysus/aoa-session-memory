# Raw-Preserving Derived-Text Privacy Boundary

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0021
- Original date: 2026-07-19
- Owner surfaces: `scripts/aoa_session_memory.py`, `README.md`, `INSTALL.md`, `skills/aoa-session-archive-init/SKILL.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: raw preservation, derived text, query routing, privacy, portable export
- Projection layers: session and segment indexes, semantic episodes, exact and semantic search, entity registry, graph, evidence previews, portable kernel
- Guard families: raw authority, credential-value redaction, sensitive-query abstention, generation identity, public-safety audit, host neutrality
- Posture: accepted

## Context

A manually reviewed real-session case exposed a credential-like runtime value
that was correctly preserved in authoritative transcript evidence but was also
copied into generated indexes and navigation surfaces. Once duplicated there,
the value could survive rebuilds, appear in search or graph packets, and cross
the portable boundary even though none of those projections owned the
evidence.

Removing the value from raw would destroy provenance. Limiting the repair to
portable copy would leave the same value in local semantic, exact, entity, and
graph read models. Allowing an exact query containing the value to reach a raw
fallback would also make a navigation API a credential-recovery interface.

## Options Considered

- Redact or rewrite authoritative transcript and segment evidence. Rejected
  because evidence preservation and later provenance review require the
  observed bytes to remain intact under their owner access boundary.
- Filter only the portable export. Rejected because generated local indexes,
  graph rows, previews, and evidence packets would still duplicate the value
  and could later be exported through another consumer.
- Keep values in projections but suppress them only while rendering results.
  Rejected because the generated stores would remain a second sensitive-data
  surface, stale rows would survive policy changes, and non-rendering
  consumers could still recover the value.
- Apply one versioned raw-to-derived privacy projection at every durable or
  agent-facing text boundary, block credential-like navigation before any
  source read, and admit portable output only after a bounded leakage audit.

## Decision

Raw transcript, raw-block, and session evidence remains byte-preserving and
authoritative. Every derived text producer uses the shared, versioned
derived-text privacy projection before persisting or returning text.

The projection preserves non-secret labels and safe state metadata, but
replaces credential-like values with typed placeholders. Derived metadata may
record only policy version, redaction status, count, kind, and bounded label;
it must not retain the value, a value hash, or a reversible derivative.
Generation identity carries the privacy-policy version, so rows from an older
or unknown policy generation are not current answer candidates.

Exact, semantic, entity, agent-event, and graph navigation routes inspect
caller-supplied anchors before reading a projection or raw source. A
credential-like literal produces an explicit abstention with zero candidates
and a non-secret reason. A label-only query remains searchable so an agent can
find the relevant evidence boundary without recovering the value.

Portable export never includes session archives or raw evidence. The legacy
session-inclusive flag is rejected before target mutation and points to a
separate private owner-to-owner migration route. Export admission runs a
bounded public-safety audit over the produced tree. Session/runtime surfaces,
credential-like values, private host paths, runtime databases, diagnostics,
external symlinks, or incomplete scan coverage make the export non-admissible.
Audit output reports only issue classes, counts, and safe relative paths.

## Rationale

This keeps the strongest evidence intact while ensuring every weaker,
rebuildable representation has one privacy law and one generation boundary.
Filtering at ingestion alone would be insufficient because query-time raw
hydration, previews, graph evidence expansion, and portable copy are also
raw-to-derived transitions. Filtering only at presentation time would leave
the stored leak intact.

Pre-read query admission prevents exact fallback from becoming a secret
oracle. Retaining labels and safe status fields preserves operational recall
without preserving the credential. A fail-closed, budget-visible portable
audit makes public safety an executable admission result rather than a claim
in a manifest.

## Consequences

- Raw evidence may still contain sensitive values and therefore remains a
  private owner surface with its existing access controls.
- Rebuilds after a privacy-policy change invalidate affected derived
  generations and must republish them from raw evidence.
- Credential-like literal searches abstain even when the caller already knows
  the value; the caller must use a label, event, session, or other non-secret
  anchor.
- Conservative opaque-token detection requires negative fixtures so long
  paths, identifiers, hashes, and ordinary status metadata are not erased as
  semantic noise.
- Portable export becomes slower by one bounded tree scan and fails when that
  scan is incomplete.
- Private evidence migration remains a separate owner route; this decision
  does not implement or authorize it through the portable command.

## Boundaries

The privacy projection is not a general secret manager, a credential rotation
service, or proof that an arbitrary byte sequence is non-sensitive. It does
not make raw evidence public, erase a value already exposed outside the owner
boundary, or replace repository and runtime access control.

The public-safety audit proves only the files and budgets named in its packet.
Synthetic regressions do not replace a boolean-only scan of authorized real
derived stores after rebuild. Session-specific coordinates, matched values,
and runtime diagnostics remain in session provenance rather than this public
decision record.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `README.md`
- `INSTALL.md`
- `skills/aoa-session-archive-init/SKILL.md`

## Follow-Up Route

Rebuild every affected projection under the new generation identity, scan the
authorized real search and graph stores without printing matched values, then
run clean portable export, standalone audit, and access-plane parity checks.
Revisit the detection policy when a randomized negative case shows semantic
loss or a reviewed leak shape escapes the shared projection.

## Verification

The owner regression is derived from a manually observed real-session leak but
uses a synthetic credential assembled from fragments. It verifies that raw
and segment evidence retains the value while manifest, index, semantic,
search, graph, preview, evidence-packet, and portable surfaces do not. It also
verifies label recall, credential-literal abstention before raw scanning,
generation identity, portable session rejection before mutation, audit
non-disclosure, safe metadata negatives, and idempotence.

The portable audit is additionally exercised against a clean tree and a
bounded tree containing representative session, diagnostics, database,
private-path, and credential findings. Real post-rebuild and standalone proof
remains required before release closeout.
