# Incremental hot append: actual 430 MB projection

## Result

Four consecutive 17,284-byte appends over the retained event-dense 430 MB
fixture completed in `10.772224..13.478708 s`. Median was `12.557384 s`; the
four-sample linearly interpolated p95 was `13.424337 s`, below the `30 s` hot
overlay gate. This is a bounded benchmark percentile, not a long-horizon
production percentile.

Every sample used the captured-tail scan, read `17,285` source bytes, reused the
430 MB raw prefix, and wrote zero bytes to a monolithic raw target. The session
aggregate used the previously published exact prefix plus summaries from the
new classification tail. The compact classification index fell from
`33,085,064` bytes to `576,042` bytes at migration and contains no duplicated
block summaries.

Privacy reconstruction admitted exact raw-line ranges from 98 historical
candidate blocks. It read `4,338,826` candidate-line bytes instead of the
`93,244,406` bytes covered by those blocks; only the new tail block used a full
scan. No literal values or literal digests were persisted. Measured privacy
time was `310..351 ms` in the steady samples.

Compact umbrella checkpoints omit the stable segment prefix and full raw-block
payload map. Physical output fell from about `72.8 MB` before that change to
`23.6..23.7 MB`. The remaining dominant stage is session-index generation
(`6.466..8.028 s`), which still owns compatibility root serialization and is a
separate componentization follow-up.

## Memory proof

One sample ran in a dedicated user scope with `MemorySwapMax=0`. It completed in
`13.478708 s`, peaked at `1,241,882,624` cgroup bytes, and observed zero swap
current and peak growth. Two shared-scope samples also had zero swap-peak
growth; one shared sample observed 2.14 MB of cgroup swap-peak movement and is
marked contaminated because unrelated background services shared that cgroup.
Process `ru_nswap` deltas were zero in all four runs.

## Authority boundary

Raw capture and immutable raw refs remain evidence authority. Physical input
block counters include executable, filesystem-cache, and spawned-worker reads;
they are retained in the machine receipt but are not presented as exact logical
projection input. Captured-append/full-replay parity, malformed-range fallback,
deep audit, and crash-resume behavior have focused tests. The final source
revision passed all `1,328` source tests in `548.07 s`; fresh portable-export
evidence is recorded separately.

Exact per-sample data is in
`session-projection-incremental-hot-append-actual-430mb-20260811.json`.
