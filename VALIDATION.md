# Validation routes

Run session-memory checks on demand after source or session-pipeline changes:

```bash
env -u PYTHONDONTWRITEBYTECODE \
  PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-${TMPDIR:-/tmp}/aoa-session-memory-pycache}" \
  python3 -m py_compile scripts/aoa_session_memory.py
env -u PYTHONDONTWRITEBYTECODE \
  PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-${TMPDIR:-/tmp}/aoa-session-memory-pycache}" \
  python3 -m pytest -q -p no:cacheprovider tests/test_session_memory.py
python3 scripts/aoa_session_memory.py validate --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py doctor --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
```

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
