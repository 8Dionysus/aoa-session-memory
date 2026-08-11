# Incremental live route: 430 MB read-only snapshot

- fixture: `429,811,332 bytes`, stable read-only source snapshot
- initial capture plus bounded live bootstrap: `19.800305 s`
- initial postings coverage: recent `8,383,575 bytes`, `4,528` entries, `5` shards
- immutable capture blocks: `103`
- bounded historical bytes read for exact bootstrap line coordinates: `1,997,357`
- live append probes: `21`
- live capture p95: `0.080133 s`
- verified event availability p95: `0.089903 s`
- live query p95: `0.012052 s`
- maximum posting shards read for append/query: `1` / `1`
- inner cgroup memory peak: `999,038,976 bytes`
- inner cgroup swap peak and growth: `0` / `0 bytes`

The first large capture computed an exact conventional SHA-256 natively during
the required delta pass and did not reread history to construct portable
continuation state. The live layer deliberately indexed a bounded recent
complete-line window and read `1,997,357` bytes from one bounded capture block
to recover its exact starting line. Its manifest records `421,427,757` omitted
bytes and `228,178` omitted lines, so it cannot be mistaken for exhaustive history.
Raw remains complete authority and stable projection remains responsible for
older navigation.

Every probe appended one complete event, updated at most one open immutable
posting shard, selected at most one shard, and reverified the result against
its exact raw byte range. The full capture-only benchmark service completed in
`22.147 s` with `MemorySwapMax=0`.

This receipt proves initial capture/bootstrap and verified live-route latency
on one actual read-only source snapshot. It does not by itself prove the cold
stable-projection SLO or freshness of every downstream projection.
