# Incremental projection: actual 430 MB cold proof

## Cold result

- source: stable read-only `429,811,332` byte snapshot;
- events / segments: `232,706 / 644`;
- six-worker cold wall time: `843.960 s` (`14 min 03.96 s`);
- cold upper gate: `<= 900 s`, met by `56.040 s`;
- CPU time: `2,362.668 s`;
- cgroup memory peak: `6,123,139,072` bytes;
- cgroup swap max/current/peak/growth: `0 / 0 / 0 / 0` bytes;
- classification blocks rebuilt: `455/455`;
- segments rebuilt: `644/644`;
- task-episode shards rebuilt: `311/311`;
- semantic digest: stable within the measured parallel run;
- full source suite: `1,315 passed` in `568.57 s`.

The cold stage built every projection component from the snapshot and published
atomically. Segment workers received immutable classification-block refs and
serialized no raw event slices. The largest phases were parse/classification
(`420.172 s`), session-index generation (`134.694 s`), segment generation
(`131.363 s`), and projection validation (`111.225 s`). This is one actual
cold run, so its reported one-sample p50/p95 fields are not an independent p95
claim.

## Growth diagnostic

The same harness appended `17,284` bytes. Capture plus persistent postings took
`0.110 s`, read zero historical raw bytes, and hashed only the delta. The
stable projection then exposed a remaining large-epoch handoff gap: because
the conventional whole-stream SHA-256 continuation is deliberately deferred,
classification planning fell back to reading all `429,828,616` bytes.

The component DAG still reused `454/455` classification blocks and `643/645`
segments, skipped `1,737,510,575` component bytes, replayed only `33` episode
events, and retained `308` sealed episodes. Even so, `663.814 s` and a full raw
read fail the strict stable-append SLO. This receipt therefore proves the cold
upper bound and delta live capture, while explicitly leaving the stable
projection source-identity handoff open.

## Authority boundary

The snapshot and raw refs remain evidence authority. No live installation,
canonical checkout, or GitHub state was changed. Exact machine-readable facts
are in
`session-projection-incremental-core-actual-430mb-cold-20260811.json`.
