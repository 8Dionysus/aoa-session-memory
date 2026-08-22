# Incremental projection portable proof

Recorded at `2026-08-11T06:37:37Z` from the isolated
`agent/session-memory-incremental-core-20260810` worktree.

## Result

- A clean portable bundle exported successfully with tests included and no
  session archive.
- The bounded public-safety audit scanned 298 files and 14,646,897 bytes with
  zero issues.
- A clean workspace-local install from that exported bundle succeeded without
  writing live user hooks.
- Installed validation passed all 27 end-to-end checks, including committed raw
  capture, raw-block referential integrity, and current session and segment
  projection generations.
- Deep doctor reported `current`, used full SHA-256 rehash mode, and found no
  problems or warnings in the empty installed runtime.
- The standalone portable-bundle audit covered all 17 requirements with no
  remaining items.
- Seven focused tests passed in 29.15 seconds from the installed copy, covering
  end-to-end validation, clean install, the portable artifact manifest, public
  safety, completion audit, manifest-first selective hydration, and the task
  episode CLI route.

## Authority boundary

This is clean export and install portability proof. It does not claim freshness
of a private or live archive, and it carries no private session evidence or host
checkout paths. Exact machine-readable evidence is in
`session-projection-incremental-core-portability-20260810.json`.
