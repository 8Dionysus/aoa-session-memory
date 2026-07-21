# Publication boundary and clean-seed route

## Current verdict

Do not make the predecessor GitHub repository public.

The committed source candidate and the predecessor repository are different
publication surfaces. A current-tree audit can pass while deleted Git objects,
release assets, Actions logs, issues, pull requests, comments, tags, and refs
remain externally visible after a visibility change.

The bounded 2026-07-21 pre-publication audit established:

- current source tree: no blocking finding;
- all locally fetched refs: 71 refs, 500 commits, 8,231 reachable objects,
  6,425 scanned blob/commit/tag objects, 1,912,305,760 scanned bytes, and no
  skipped object;
- predecessor history: one blocking `personal_home_path` fingerprint with
  4,254 occurrences;
- hosted surfaces: two release assets with 335 archive members in total; one
  blocking home-path fingerprint and two blocking session-index paths;
- Actions: 38 runs, no retained Actions artifact, and no run log still
  downloadable for content review;
- issues and pull requests: 61 issue-or-PR records, 5 issue comments, 41 review
  comments, and 28 pull-review bodies checked without a new blocking class.

Audit receipts expose classes, counts, coordinates, and one-way fingerprints,
not matched values. The receipts remain review evidence and are not committed
runtime or session material.

These results block a direct private-to-public visibility change. They do not
authorize history rewriting, ref deletion, release deletion, repository
renaming, or replacement.

## Recommended route

Publish a clean seed into a new GitHub repository after the source candidate is
final. Preserve the predecessor repository as private evidence. If the desired
public name is already occupied by the predecessor, repository naming or
renaming is a separate maintainer decision.

The clean seed must contain only the final audited tracked tree. It must not
copy the predecessor `.git` directory, refs, tags, releases, issues, pull
requests, comments, Actions logs, custom release assets, caches, build output,
or runtime/session evidence. It starts with a new root commit and a reviewed
public commit identity.

A short provenance record may name the private source commit digest and export
method, but it must not embed private URLs, paths, credentials, transcripts, or
unreviewed metadata. Provenance records lineage; it does not import predecessor
objects.

History rewriting is not the default route. Rewriting Git objects alone would
not remove separate GitHub-hosted surfaces and would make preservation and
cache/fork claims harder to prove.

## Admission gates for the clean seed

Before any public visibility change:

1. integrate the explicit foundation handoff in an isolated checkout;
2. regenerate owner projections and indexes once from that integrated state;
3. pass the full standalone and package test suites;
4. produce byte-identical wheel and sdist in two clean external builds;
5. pass synthetic stdio protocol smoke from installed wheel and sdist;
6. run `scripts/audit_public_tree.py --fail-on blocking` on the exported seed;
7. fetch every seed ref and run
   `scripts/audit_git_history.py --fail-on blocking` with no skipped object;
8. review commit identity, repository metadata, workflow permissions, links,
   dependency licenses, and release contents;
9. add the maintainer-approved root `LICENSE`;
10. obtain an explicit maintainer decision for repository creation, naming,
    visibility, release publication, and any package-registry upload.

After publication, repeat current-tree and full-ref history audits against a
fresh public clone, verify public wheel/sdist hashes against the accepted build
receipt, and confirm that the live private deployment was not changed.

## CI boundary

Standalone CI fetches full history. The blocking history gate runs
automatically when GitHub reports that repository as public. A private seed
still requires the manual pre-publication full-ref audit because the public-only
CI condition has not fired yet.

Optional ecosystem CI may use private owner repositories through an explicit
token. That lane is not required for standalone installation or public release
admission.
