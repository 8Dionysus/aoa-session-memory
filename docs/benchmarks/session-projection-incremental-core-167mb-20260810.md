# Incremental projection core: 167 MB live-equivalent fixture

- fixture: `167,337,941 bytes`, `73,161 events`, `295 segments`
- cold four-worker runs: `392.71 s`, `356.42 s`, `382.54 s`
- cold p50: `382.54 s` (`6:23`)
- cold p95: `392.71 s` (`6:33`)
- internal semantic parity: `true`
- one-percent append: `1,700,529 bytes` in `51.32 s`

The append path hashed only the new `1,700,529` bytes, read `1,700,530`
source bytes, and reused the attested `167,337,941`-byte prefix. It reused all
`295` prior raw blocks and published segments, `293` sealed task episodes, and
`294` episode shards. Only `3` raw blocks/segments, `2` classification blocks,
and `4` episode shards were rebuilt. Parent rehydration remained bounded to
`3,917,093` raw bytes and did not materialize a whole-session event list.

The cold SLO is met on this fixture, but the containing systemd cgroup observed
a `314.895 MiB` swap peak. Therefore this receipt deliberately leaves the
no-swap gate open for the isolated 430 MB acceptance run.

This is a synthetic target-host measurement. It is not evidence that an actual
archived source snapshot or every downstream projection is current.
