# Session-memory statistics

This directory is the owner-local stats port for `aoa-session-memory`. It
publishes bounded revision-level measurements whose domain meaning belongs to
the portable session-memory kernel and hands their contracts to `aoa-stats`.

The port does not read live archives, score sessions or people, infer memory
quality, decide readiness, or replace raw, segment, manifest, scenario, or
review authority.

## Current question

`aoa-session-memory/portable-scenario-fixture-coverage-ratio` asks what
fraction of the currently declared live-scenario corpus cases can execute in a
clean portable bundle from a reviewed privacy-safe source fixture, without a
runtime session archive.

The executable corpus inventory and the durable readiness model expose this
distinction. It prevents an allowed skip from being presented as executed
portable proof while leaving live-archive scenarios visible in the population.

## Reference derivation

The denominator is every case declared in
`config/live-scenario-regression-corpus.json`. The numerator is the subset for
which the owner corpus inventory reports
`evidence_origin=reviewed_synthetic_fixture_archive`; that state requires a
contained source fixture and complete case review metadata.

The reference packet owns the revision-bound numerator, denominator, and source
revision; this README does not duplicate that changing snapshot. The packet is
a source-revision census, not live telemetry. An invalid, escaping, missing, or
unreviewed fixture remains in the denominator and is not counted as portable
fixture coverage.

## Authority

The ratio measures only source-owned portable fixture coverage. It does not
establish that a covered case passes, that a skipped case fails, that the live
archive is healthy, that retrieval is correct, or that session evidence has
become reviewed memory.

## Owner routes

- `port.manifest.json` owns the local question and measurement contract.
- `packets/` contains the revision-bound public reference packet.
- `config/live-scenario-regression-corpus.json` owns the case population.
- `config/fixtures/skill-candidate-semantics.json` is the current reviewed
  privacy-safe fixture.
- `live_scenario_corpus_inventory` in `scripts/aoa_session_memory.py` owns the
  executable derivation.
- `READINESS.md` explains how portable scenario coverage differs from live
  readiness.
