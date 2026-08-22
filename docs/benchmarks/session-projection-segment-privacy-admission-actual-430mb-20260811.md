# Generation-bound segment privacy admission: actual 430 MB snapshot

- source class: stable read-only `429,811,332` byte snapshot
- measured segment: `1,610` events
- paired repetitions: `3`
- ordinary full-pass median: `3.883127 s`
- generation-bound admission median: `1.067364 s`
- median speedup: `3.638x`
- emitted index SHA-256 parity: exact
- classification generation: unchanged
- segment generation: changed

The classification cache already excludes raw and parsed payloads and redacts
its metadata under the ephemeral whole-session literal policy. After its exact
generation, block identity, artifact receipt, and raw block digest are
validated, a segment worker reuses that privacy proof instead of rescanning the
same event metadata. Token observations freshly derived from parsed raw are
still redacted before admission. Context-sensitive facet maps still receive
the established complete policy pass. A caller without the cache proof retains
the ordinary full pass.

This paired component receipt proves equivalent segment-index output and a
bounded optimization on one event-dense real segment. It does not prove the
complete cold-projection SLO, portable installation, or live deployment.
