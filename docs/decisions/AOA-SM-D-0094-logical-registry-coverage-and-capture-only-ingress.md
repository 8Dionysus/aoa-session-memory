# Logical Registry Coverage and Capture-Only Ingress Separation

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0094
- Original date: 2026-08-22
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `INSTALL.md`, `docs/PORTABILITY.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: archive registry, raw preservation, freshness, scheduling, installation, systemd contract
- Projection layers: logical session registry, physical archive lineage, capture-watch ingress, resource-gated discovery and stable sweep
- Guard families: logical/physical cardinality separation, explicit identity/path lineage, current-path uniqueness, preserved-duplicate reporting, capture-only topology, resource admission, hook compatibility
- Posture: accepted

## Context

The archive registry has one logical record per `session_id`, while the
filesystem can retain more than one physical archive directory for that same
identity. In particular, `040` and `041` are preserved `raw_unavailable`
archives of one session. The logical registry points to the latest path. A
doctor check that compares logical registry count to physical directory count
turns this evidence-preserving state into a false failure and offers no
lineage report. The correction must preserve the distinction rather than
discarding, merging, or relabeling evidence.

The same boundary applies to ingress scheduling. The fresh-capture service
must advance the hook-observed capture frontier without depending on archive
discovery or stable projection. A separate resource-gated lane owns transcript
discovery and stable sweep work. This keeps the accepted capture/watch contract
from becoming a disguised projection timer.

This decision extends the raw-ledger and live-tail boundary in D-0049 and the
additive repair/fail-closed mismatch boundary in D-0083. It does not replace
either decision's source or evidence authority.

## Options Considered

- Delete or merge the duplicate archive. Rejected because it loses preserved
  raw-unavailable evidence and erases the incident lineage.
- Fabricate a second `session_id`. Rejected because it falsifies logical
  identity to satisfy a physical count.
- Make the registry multi-record per physical directory. Rejected because the
  registry identity remains logical: one current record per `session_id`.
- Compare logical registry count directly to physical directory count.
  Rejected because the comparison conflates coverage with physical lineage.
- Use hooks only and omit reconciliation. Rejected because missed hooks and
  retained external transcripts still need a recovery route.
- Keep capture and discovery/stable sweep in one service. Rejected because
  capture would depend on projection cost and resource availability.
- Explicitly separate logical registry coverage from physical archive
  lineage/cardinality, and run a capture-only timer beside a separate
  resource-gated sweep lane.

## Decision

The session registry continues to admit at most one logical record per
`session_id`. Registry records carry an explicit physical-lineage sidecar with
the logical id, exact current path, all manifest-backed physical paths, and the
identity/path basis used to relate them.

Doctor validates the two cardinalities separately. A preserved same-session
physical duplicate is accepted only when every manifest has a valid
`session_id`, a session label matching its physical directory, a preserved
archive status and incident/diagnostic evidence, and exactly one physical
match for the registry's current path. Accepted duplicates remain visible in
the warning and structured lineage report. Unique unregistered archives,
mismatched manifest and registry ids, malformed manifests, non-explicit
lineage, and missing or ambiguous current paths remain failures.

The rendered fresh-capture service has exactly one `capture-watch` command and
has no dependency on a sweep lane. Discovery and stable projection are rendered
into the separately named, resource-gated
`aoa-session-memory-resource-gated-sweep.service` and timer. Installation and
upgrade may write only these named units when an explicit unit directory is
provided; they never enable, start, or reload systemd. The portable install
continues to preserve runtime archives and hook authority.

## Rationale

The logical registry answers “which session identity is currently navigable?”
The physical lineage report answers “which preserved archive directories carry
that identity?” Keeping both questions explicit allows doctor to report
physical multiplicity without weakening checks for genuinely unowned or
ambiguous evidence. The exact path match prevents a latest-path claim from
silently pointing at the wrong archive, while the manifest id and directory
label preserve a portable, raw-free lineage basis for the existing
`raw_unavailable` archives.

The capture-only unit follows D-0049's bounded frontier: it can recover missed
hook bytes without rediscovering the archive or reading unchanged raw payloads.
The separate resource-gated sweep follows the existing owner resource posture
for expensive discovery and stable work. Explicit rendering and no activation
keep source/install tests independent from live trust and systemd state.

## Consequences

- Positive: preserved same-session duplicates no longer create a false count
  failure, while their paths and multiplicity remain observable.
- Positive: true identity, manifest, registration, and current-path anomalies
  fail closed instead of being hidden by a count-only rule.
- Positive: fresh capture remains lightweight and independent from projection
  availability; discovery/stable work has a visible resource-gated owner lane.
- Tradeoff: duplicate acceptance requires complete manifest/path lineage and
  preserved incident evidence; a malformed or ambiguous archive still blocks
  doctor.
- Tradeoff: resource blocking may delay discovery and stable projection even
  while capture advances, so freshness remains multi-axis.
- Follow-up: a runtime owner must explicitly render/activate the units and
  separately verify live trust, currentness, health, and acceptance.

## Boundaries

This decision does not delete, merge, rewrite, or migrate the existing live
archives. It does not make a registry record proof that every physical archive
is semantically complete, that raw evidence is available, or that a projection
is current. A green unit-render contract is not live systemd activation,
runtime health, source admission, or owner/human acceptance. It does not grant
the portable installer authority over systemd, hooks trust, official bundles,
or artifact registries.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `INSTALL.md`
- `docs/PORTABILITY.md`
- `tests/test_session_memory.py`
- `docs/decisions/AOA-SM-D-0049-append-only-raw-capture-ledger-and-persistent-live-tail-overlay.md`
- `docs/decisions/AOA-SM-D-0083-additive-registry-repair-replaces-full-layer-reconstruction.md`
- `docs/decisions/`

## Follow-Up Route

Use the owner decision index and source/export validation route for future
changes. Use `render-systemd-units --output-dir <explicit-target>` or
`install --systemd-unit-dir <explicit-target>` for a reviewed deployment
handoff, then route enable/reload and live runtime proof to the runtime owner.
Use doctor for separate logical coverage, physical lineage, and current-path
evidence; do not infer capture freshness or human acceptance from it.

## Verification

Focused tests cover preserved duplicate acceptance, lineage reporting,
unregistered/mismatched/malformed/ambiguous failures, one-record registry
rebuilds, capture-only and resource-gated unit contracts, install upgrade
rendering, and native hook/capture compatibility. Decision indexes are
regenerated and checked from this source record. Source compilation, focused
and relevant full tests, validation, clean portable export, and public safety
audit remain required. No canonical/live/systemd activation or external
publication is part of this decision.
