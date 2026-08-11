# Incremental projection portability refresh

The isolated revision `3037682` was exported as a clean standalone bundle with
tests and without session archives.

- public-safety audit: `310` files and `14,845,859` bytes, zero issues;
- standalone validation: all `27` checks passed;
- portable completion audit: green, no remaining or blocked requirements;
- focused standalone tests: `30` passed, `1,099` deselected in `13.01 s`;
- local standalone Git metadata points at the existing public origin;
- canonical checkout, live installation, and GitHub were not mutated.

This refresh covers the task-episode reduction, single-pass shard privacy,
checkpoint/resume, manifest-first readers, deep shard audit, and ordered segment
lookup. It is portability proof for this source revision, not live archive
freshness or cold-projection SLO evidence.
