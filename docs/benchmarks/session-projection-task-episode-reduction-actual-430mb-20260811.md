# Task-episode reduction: actual 430 MB snapshot

- source class: stable read-only `429,811,332` byte snapshot
- profiled reduction slice: first `20,000` events across `644` segment ranges
- paired reduction repetitions: `3`
- old reduction median: `11.581046 s`
- single-semantic-pass/binary-range median: `6.586581 s`
- reduction speedup: `1.758x`
- full shard set: `311` episode payloads
- old parent-plus-worker redaction: `95.127284 s`
- single worker redaction: `33.562716 s`
- one-pair shard speedup: `2.834x` (not p95)
- output SHA-256 parity: exact in both measurements
- unchanged generations: raw classification and segment index
- invalidated generations: task-episode source and dependent session index

The reducer now derives semantic text once per event and passes it to its
deterministic consumers. Segment lookup uses the ordered, non-overlapping
source-range contract. A cold episode shard is redacted exactly once in its
worker. When comparison with a prior shard already requires the parent to
derive the expected redacted payload, that exact payload crosses the worker
boundary rather than being scanned again.

No raw text, host path, global semantic cache, or reusable secret value was
persisted. Unattested worker input retains the complete privacy pass. This
receipt proves equivalent component output and bounded local speedups; it does
not prove full cold-projection p95, portable installation, or live deployment.
