# Validation routes

Run session-memory checks on demand after source or session-pipeline changes:

```bash
env -u PYTHONDONTWRITEBYTECODE \
  PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-${TMPDIR:-/tmp}/aoa-session-memory-pycache}" \
  python3 -m py_compile scripts/aoa_session_memory.py
python3 scripts/pytest_scheduler_experiment.py --method static2
python3 scripts/aoa_session_memory.py validate --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py doctor --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
```

The ordinary `static2` route reads the current portable source-test targets
from `docs/validation/validation_lanes.json`, collects them once, and runs an
exact two-process partition.  It creates a fresh bytecode prefix inside its
temporary invocation directory, writes no receipt, and does not require
repository or environment identity.  Use `--method serial` as the direct
fallback when process parallelism is unsuitable.  Receipt, artifact, and
identity options remain comparison-only; this local route is feedback and
does not replace the full release or installed-protocol gates.
If a static child fails, its captured pytest tails are emitted when that shard
completes instead of waiting for the sibling; this is an early shard-completion
signal, not per-test streaming or an incremental release verdict.

For a pure predicate edit to a standalone producer sibling, run only the
corresponding focused route before the full suite. Use a fresh bytecode prefix
outside the checkout so a same-size, same-second source edit cannot reuse an
older `.pyc`; these direct tests include interpreter and module startup:

```bash
# Privacy sibling edit:
privacy_core_pycache="$(mktemp -d "${TMPDIR:-/tmp}/aoa-session-memory-privacy.XXXXXX")"
env -u PYTHONDONTWRITEBYTECODE PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPYCACHEPREFIX="$privacy_core_pycache" \
  python3 -m pytest -q -p no:cacheprovider --rootdir=. --confcutdir=. \
    tests/test_session_memory_privacy_core.py
# Outbox sibling edit:
outbox_core_pycache="$(mktemp -d "${TMPDIR:-/tmp}/aoa-session-memory-outbox.XXXXXX")"
env -u PYTHONDONTWRITEBYTECODE PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPYCACHEPREFIX="$outbox_core_pycache" \
  python3 -m pytest -q -p no:cacheprovider --rootdir=. --confcutdir=. \
    tests/test_session_memory_outbox_core.py
```

Use the privacy-core command for privacy edits and the outbox-core command
for outbox edits. When changing the loader, source identity, or wiring around
either sibling, add the monolith identity regression:

```bash
identity_pycache="$(mktemp -d "${TMPDIR:-/tmp}/aoa-session-memory-identity.XXXXXX")"
env -u PYTHONDONTWRITEBYTECODE PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPYCACHEPREFIX="$identity_pycache" \
  python3 -m pytest -q -p no:cacheprovider --rootdir=. --confcutdir=. \
  tests/test_session_memory.py \
  -k 'generation_identity or loaded_producer_source'
```

The real portable CLI/copy/install checks and the full source suite remain
separate integration gates.

The bytecode prefix must remain outside the checkout. Pytest assertion
rewriting remains enabled for diagnostics. Python's default timestamp/size
invalidation normally recompiles when a source or test byte length or recorded
timestamp changes. The standard `.pyc` timestamp has one-second precision, so a
rapid same-size edit within the same timestamp second can reuse stale external
bytecode even when `st_mtime_ns` changes; preserving both stored fields has the
same limit. Rotate or clear the prefix when metadata-preserving or rapid
same-second edits are possible. CI's `runner.temp` prefix is fresh per job.

## Decisions

```bash
python3 scripts/generate_decision_indexes.py
python3 scripts/generate_decision_indexes.py --check
git diff --check
```
