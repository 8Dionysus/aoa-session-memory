# Independent Skill Interface Delivery

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0102
- Original date: 2026-09-08
- Owner surfaces: `skills/`, `capabilities/`, `generated/`, `scripts/install_skill_interface.py`, `INSTALL.md`, `tests/`
- Surface classes: installation, skill routing, portability, source lineage
- Projection layers: capability graph, skill router, component install receipt
- Guard families: bounded mutation, package provenance, source authority, rollback, kernel preservation
- Posture: accepted component delivery boundary

## Context

The capability home and its skill packages can evolve independently of an
active capture and retrieval kernel. The full portable installer replaces
kernel source and records its provenance. Using that route solely to deliver
skill instructions couples two independently owned changes and can overwrite
an intentionally different active kernel. Copying only the entrypoint has the
opposite defect: manifests, references, and generated routing retain old
package identities.

## Options Considered

- Always reinstall the portable kernel. Rejected for an interface-only change
  because it replaces unrelated executable source and its install provenance.
- Copy or redirect the two user entrypoints. Rejected because this detaches
  active-root ownership or leaves the capability graph inconsistent.
- Deliver the complete selected skill interface as a separately reversible
  owner operation, anchored to the existing kernel profile. Accepted.

## Decision

`scripts/install_skill_interface.py` owns a bounded interface overlay. Its
default selection is the two advertised routers; additional skill packages
must be explicitly selected from the owner capability graph. The fixed shared
closure contains capability declarations, the skill home manifest and owner
guidance, generated graph/readout, and the global router card. Selected skill
directories move as complete packages.

Source admission requires a clean Git identity and validation through an
explicitly selected `aoa-skills` contract checkout. Every unselected skill
package referenced by the new graph must already match the target. Kernel
source equality is not a prerequisite: the valid existing kernel install
profile is a preservation anchor, not provenance for the new interface.

The operation checks source and target identity before replacement, preserves
a durable bounded backup, and publishes its component receipt last. Failures
before mutation preserve concurrent changes. Recovery restores only the
operation's admitted component; changed or unverifiable rollback evidence
blocks restoration. A later full install changes the base-profile anchor and
makes an older component receipt stale.

User-skill links continue to target the active owner root. Their aggregate
profile receipt is checked and refreshed by the existing profile assembler.
The component installer does not own that receipt or the user's catalog.

## Rationale

Separate provenance allows a current interface to coexist honestly with a
different active kernel. Full package and graph parity preserves D-0018's
source/read-model boundary, while the unchanged kernel profile preserves the
executable lineage established by D-0097. Explicit contract binding makes
shared schema drift visible without substituting a nearby checkout.

## Consequences

- Interface changes can be delivered and reversed without a kernel restart.
- A component receipt describes selected bytes and their source identity;
  kernel provenance remains in the full install profile.
- Shared graph changes may require selecting additional affected packages;
  the operation must not silently broaden its selection.
- Recovery retains bounded backup storage until its disposition is chosen.

## Boundaries

This route does not alter sessions, raw evidence, capture hooks, runtime maps,
search stores, system services, or model configuration. It grants no exposure,
publication, execution, or promotion authority. Valid source and receipt data
do not prove prompt selection, successful invocation, runtime health, or
cross-host portability.

## Source Surfaces

- `scripts/install_skill_interface.py`
- `INSTALL.md`
- `capabilities/port.manifest.json`
- `skills/port.manifest.json`
- `tests/test_install_skill_interface.py`

## Follow-Up Route

Apply the owner component check/install/rollback path, then the profile
assembler and a fresh consumer read. Keep source validation, merge, selected
delivery, catalog visibility, and observed behavior as separate claims.

## Verification

Focused fixtures cover complete selected package delivery, unselected skill
parity, kernel/profile and archive preservation, stale identities, source and
target changes before commit, failed replacement recovery, and exact rollback
evidence. Run capability generated parity and portable export checks through
their owners. Live delivery and rollback evidence belongs to the bounded
operation record, not this durable decision.
