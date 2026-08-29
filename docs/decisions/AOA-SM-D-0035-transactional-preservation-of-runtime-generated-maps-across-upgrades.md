# Transactional Preservation of Runtime-Generated Maps Across Upgrades

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0035
- Original date: 2026-07-28
- Owner surfaces: `scripts/aoa_session_memory.py`, `INSTALL.md`, `docs/decisions/`
- Surface classes: runtime installation, portable kernel upgrade, generated projection preservation, recovery
- Projection layers: atlas indexes, typed map indexes, map entries, projection state, entity registry
- Guard families: authored/generated authority, transactional overlay, last-good rollback, generation freshness, public-safe export
- Posture: accepted

## Context

A portable kernel upgrade must replace authored map templates and remove
authored files that no longer belong to the new version. The previous
overwrite route removed the entire installed `maps/` tree before copying the
new kernel. That also discarded runtime-generated atlas indexes, typed entry
files, projection state, and the entity registry.

Those files are rebuildable and non-authoritative, but losing them
unconditionally turns an ordinary incremental generation catch-up into a
bootstrap rebuild. On a large archive that can create long retrieval
degradation and unnecessary storage or compute pressure immediately after an
otherwise compatible kernel upgrade.

Blindly retaining the old map tree is not acceptable either. It would preserve
obsolete authored templates and could conceal a failed kernel copy or an
incompatible generated projection behind stale files.

## Options Considered

- Delete the whole installed map tree and rebuild every generated projection
  after each upgrade. Rejected because compatible upgrades cause avoidable
  bootstrap loss and a potentially long retrieval outage.
- Keep the old map tree and copy new authored files into it in place. Rejected
  because removed authored files survive, partial failures can expose a mixed
  tree, and ownership between authored and generated files becomes ambiguous.
- Replace authored maps from the new kernel, then transactionally overlay only
  the declared runtime-generated map family; restore the complete previous
  tree if replacement or overlay fails.

## Decision

Runtime installation upgrades distinguish authored map source from declared
runtime-generated map projections.

When overwrite is requested, the installer moves the existing `maps/` tree to
a private sibling preserve path, copies the new authored map tree, and overlays
only the known generated family:

- root atlas indexes;
- atlas projection state;
- entity-registry JSON and Markdown views;
- typed `by-*` indexes and their generated entry directories.

If the authored copy or generated overlay fails, the installer removes the
partial replacement and restores the complete previous map tree. Only after a
successful replacement and overlay is the private preserve path removed. The
install receipt lists which generated paths were restored.

Portable public export retains its existing boundary and does not copy
runtime-generated maps. Preservation is enabled only by the runtime install
route, where the target is an existing owner installation rather than a
public-safe source bundle.

Preserved projections retain their own generation identity and freshness
state. A new schema, producer, classifier, embedding, episode, registry, or
graph generation can still make them stale, incompatible, or dirty and require
catch-up. Preservation prevents loss; it does not admit old rows as current
answer candidates.

## Rationale

The chosen route preserves expensive but reproducible navigation state without
promoting it above authored kernel source, raw sessions, or external owner
evidence. Replacing authored files first ensures the installed kernel exactly
tracks the selected portable version, while the allowlisted overlay keeps the
generated boundary explicit.

Moving the old tree aside creates a concrete last-good rollback target.
Restoring that entire tree on failure is safer than trying to reverse a
partially completed in-place copy. Keeping public export and runtime install as
separate policies also prevents private generated state from entering a
portable release.

## Consequences

- Compatible upgrades preserve generated navigation state and can use bounded
  generation-aware catch-up instead of rebuilding from an empty map tree.
- Removed authored map files do not survive an upgrade merely because the old
  installation contained them.
- An interrupted or rejected overlay leaves the prior complete map tree
  available rather than a mixed authored/generated generation.
- The allowlist must evolve when a new generated map family is introduced;
  an unlisted generated file is intentionally not preserved.
- Preserved data can remain stale or incompatible after upgrade and must be
  reported as such until the owning projection verifies or rebuilds it.

## Boundaries

This decision governs the `maps/` portion of a runtime kernel upgrade. It does
not make generated maps owner truth, guarantee semantic correctness, waive
generation or freshness checks, preserve runtime databases or diagnostics, or
authorize private state in a portable export. It does not replace a declared
migration, full rebuild, privacy audit, or source/portable/runtime parity
check.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `INSTALL.md`

## Follow-Up Route

Run a controlled upgrade from an installed older kernel containing real-shaped
generated map state to the new portable bundle. Seal authored and generated
digests before the upgrade, verify the new authored tree and preserved
allowlisted projections afterward, then require generation-aware freshness and
bounded catch-up. Repeat with an injected overlay failure and verify exact
last-good restoration. Reopen the policy if a generated family is omitted,
authored state is accidentally retained, privacy boundaries regress, or
concurrent-reader evidence exposes a mixed tree.

## Verification

Owner-neutral installation regressions create an existing runtime, add
generated atlas, registry, typed-index, and entry payloads plus an obsolete
authored file, and then perform an overwrite upgrade. They require the
generated payloads to remain byte-identical, the obsolete authored file to
disappear, the new authored template to exist, and the install receipt to name
the restored family.

A failure-injection regression stops the overlay after the new authored tree
has been copied. It requires the prior authored and generated bytes to be
restored and the private preserve path to be absent afterward. Controlled
real-shaped upgrade, portable parity, generation-incompatibility, and
post-upgrade catch-up remain separate runtime gates.
