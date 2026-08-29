# Session projection validation DAG: actual 7 MB snapshot

- source class: stable read-only `7,323,145` byte snapshot
- events / segments / classification blocks: `3,362 / 44 / 7`
- paired order: optimized, baseline, baseline, optimized
- baseline median: `4.758 s`
- optimized median: `3.8675 s`
- median speedup: `1.230x`
- semantic projection roots: exact parity across all four runs
- process peak: `430.8 MiB`, swap `0 B`

The baseline and optimized variants ran from the same source version and the
same shadow path. The baseline disabled only the three execution shortcuts: a
process-local redaction memo, bounded semantic-hash materialization, and reuse
of an independently versioned raw-bound privacy marker across an incompatible
classification generation. Both variants retained full redaction, canonical
semantic hashing, raw candidate discovery, staged validation, and atomic
publication.

The bounded semantic-hash component comparison matched all `44` roots and
reduced median hashing time from `0.60715 s` to `0.11445 s` (`5.305x`). The
privacy-marker DAG change reduced the measured sensitive-literal phase from
roughly `0.50-0.58 s` to `0.09-0.11 s` during the forced migration.

Rejected variants were also measured. A global field-name LRU was slower
(`0.961x`), an earlier recursive cache lookup was slower (`0.989x`), and
cross-block classification-cache sharing produced only `1.032x`, insufficient
to justify changing worker/checkpoint topology. Four segment workers remained
the default because a prior `1/2/4/6` comparison placed four and six within
noise while six increased concurrency pressure.

This is one paired forced-migration benchmark, not a hot-append or global
AbyssOS SLO. It persists no session identifier, host path, raw text, sensitive
literal, or reversible literal digest.
