# Validation routes

Run session-memory checks on demand after source or session-pipeline changes:

```bash
env -u PYTHONDONTWRITEBYTECODE \
  PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-${TMPDIR:-/tmp}/aoa-session-memory-pycache}" \
  python3 -m py_compile scripts/aoa_session_memory.py
env -u PYTHONDONTWRITEBYTECODE \
  PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-${TMPDIR:-/tmp}/aoa-session-memory-pycache}" \
  python3 -m pytest -q -p no:cacheprovider \
    tests/test_session_memory.py \
    tests/test_session_memory_privacy_core.py \
    tests/test_session_memory_outbox_core.py \
    tests/test_session_memory_doctor.py \
    tests/test_session_memory_outbox.py \
    tests/test_session_memory_task_lifecycle.py \
    tests/test_session_memory_tool_usage.py \
    tests/test_session_memory_episode_search.py \
    tests/test_session_memory_episode_maintenance.py \
    tests/test_session_memory_episode_temporal.py \
    tests/test_session_memory_capture.py \
    tests/test_session_memory_sweep.py
python3 scripts/aoa_session_memory.py validate --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py doctor --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
```

For a pure predicate edit to a standalone producer sibling, run only the
corresponding focused route before the full suite. Use a fresh bytecode prefix
outside the checkout so a same-size, same-second source edit cannot reuse an
older `.pyc`; these direct tests include interpreter and module startup:

```bash
# Privacy sibling edit:
privacy_core_pycache="$(mktemp -d "${TMPDIR:-/tmp}/aoa-session-memory-privacy.XXXXXX")"
env -u PYTHONDONTWRITEBYTECODE PYTHONPYCACHEPREFIX="$privacy_core_pycache" \
  python3 -m pytest -q -p no:cacheprovider \
    tests/test_session_memory_privacy_core.py
# Outbox sibling edit:
outbox_core_pycache="$(mktemp -d "${TMPDIR:-/tmp}/aoa-session-memory-outbox.XXXXXX")"
env -u PYTHONDONTWRITEBYTECODE PYTHONPYCACHEPREFIX="$outbox_core_pycache" \
  python3 -m pytest -q -p no:cacheprovider \
    tests/test_session_memory_outbox_core.py
```

Use the privacy-core command for privacy edits and the outbox-core command
for outbox edits. When changing the loader, source identity, or wiring around
either sibling, add the monolith identity regression:

```bash
identity_pycache="$(mktemp -d "${TMPDIR:-/tmp}/aoa-session-memory-identity.XXXXXX")"
env -u PYTHONDONTWRITEBYTECODE PYTHONPYCACHEPREFIX="$identity_pycache" \
  python3 -m pytest -q -p no:cacheprovider tests/test_session_memory.py \
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
