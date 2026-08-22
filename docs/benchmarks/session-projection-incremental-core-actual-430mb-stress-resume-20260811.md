# Incremental projection stress-resume: actual 430 MB snapshot

- source class: stable read-only `429,811,332` byte snapshot
- events / segments: `232,706` / `644`
- wall time: `912.742 s` (`15 min 12.7 s`)
- concurrent load: independent canonical session-memory catch-up for the full run
- classification blocks reused / rebuilt: `455 / 0`
- segment generation: `153.141 s`
- session-index generation: `364.712 s`
- projection validation: `122.788 s`
- memory peak: `6,754,246,656 bytes`
- cgroup swap peak and growth: `0 / 0 bytes`
- atomic publish: successful; raw snapshot unchanged

The producer change opened a new stage work directory, then admitted every
classification block from the previous exact generation by metadata receipt.
No block was reclassified. The segment stage rebuilt all `644` indexes in
`153.141 s` with six spawned workers and without serializing raw event slices.
Validation admitted receipts for all `644` raw blocks and `311` task-episode
shards; it performed no per-component fallback rehash.

The complete run exceeded the strict 900-second cold upper bound by
`12.742 s`. It ran without an exclusive heavy lane while an independent
canonical catch-up competed throughout, so this is useful stress and resume
evidence, not a clean cold-p95 claim. The next measured bottleneck is session
indexing: task-episode reduction took `227.763 s` and shard generation another
`123.624 s`.
