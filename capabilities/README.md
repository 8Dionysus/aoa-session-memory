# Session-memory capabilities

This directory is the canonical owner-local map of session-memory abilities.
It is a semantic tree plus typed relations, not a physical skill hierarchy.

The shared shape and validator come from `aoa-skills`. This repository owns
the nodes, contracts, bindings, and lifecycle decisions. The deterministic
graph under `generated/` and the router card inside the global route package
are reproducible discovery projections and never replace these sources.

Only `aoa-session-memory-global-route` and
`aoa-session-memory-evidence-route` are globally advertised. Other skill
packages remain deferred owner-local procedures until controlled evidence
justifies a visibility change.

