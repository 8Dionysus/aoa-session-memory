# Event-driven hot no-op benchmark

- runs: `21`
- wall p50: `0.031403 s`
- wall p95: `0.053686 s`
- wall max: `0.062020 s`
- acceptance SLO: `p95 <= 2 s`
- SLO met: `true`
- archive manifest scans: `0`
- raw payload reads: `0`
- outbox raw bytes read: `0`

Every run selected the empty `event_driven_hot_ready_queues` path. This is an
isolated target-host measurement of ordinary no-op scheduling. It is not a
claim that every search, episode, entity, or graph projection is globally
current.
