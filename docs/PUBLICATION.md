# Public repository posture

## Current verdict

The repository is public and retains its predecessor Git history. This is an
explicit maintainer decision: the known historical path findings do not block
standalone installation or the current public release, and history cleanup is
deferred. The current tracked tree remains subject to a fail-closed public
safety audit.

A current-tree audit and a retained-history inventory answer different
questions. The former protects what users clone and install now. The latter
keeps disclosure debt visible across deleted Git objects, release assets,
Actions logs, issues, pull requests, comments, tags, and refs.

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

The maintainer accepted the historical home-path and session-index path classes
as noncritical for the current public repository. This acceptance does not
reclassify secrets, credentials, private transcript bodies, runtime databases,
or current-tree host leakage. It also does not authorize history rewriting,
ref deletion, release deletion, repository renaming, or replacement.

## Retained-history route

CI inventories reachable history with `--fail-on none`. The JSON result stays
visible as diagnostic evidence, while known historical path debt does not make
unrelated source, package, or installation validation fail. The current tree
continues to run `audit_public_tree.py --fail-on blocking` before and after the
standalone build.

History rewriting is not part of the current release. Any later cleanup must
be a separately reviewed maintenance operation covering Git refs and distinct
GitHub-hosted surfaces; rewriting Git objects alone cannot make claims about
releases, issues, pull requests, Actions logs, caches, or forks.

## Admission gates for the public release

Before a release:

1. integrate the explicit foundation handoff in an isolated checkout;
2. regenerate owner projections and indexes once from that integrated state;
3. pass the full standalone and package test suites;
4. produce byte-identical wheel and sdist in two clean external builds;
5. pass synthetic stdio protocol smoke from installed wheel and sdist;
6. run `scripts/audit_public_tree.py --fail-on blocking` on the release tree;
7. inventory retained history with no skipped object and review any finding
   class not covered by the accepted historical-path debt;
8. review commit identity, repository metadata, workflow permissions, links,
   dependency licenses, and release contents;
9. include the maintainer-approved root `LICENSE`;
10. obtain an explicit maintainer decision for release publication and any
    package-registry upload.

After publication, repeat the current-tree audit and retained-history inventory
against a fresh public clone, verify public wheel/sdist hashes against the
accepted build receipt, and confirm that the live private deployment was not
changed.

## CI boundary

Standalone CI fetches full history. When GitHub reports the repository as
public, CI inventories it without turning accepted legacy-path debt into a
source or installation failure. Current-tree public-safety findings remain a
blocking gate.

Optional ecosystem CI may use private owner repositories through an explicit
token. That lane is not required for standalone installation or public release
admission.
