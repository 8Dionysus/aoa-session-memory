# Validation routes

Run session-memory checks on demand after source or session-pipeline changes:

```bash
python3 -m py_compile scripts/aoa_session_memory.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_session_memory.py
python3 scripts/aoa_session_memory.py validate --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
python3 scripts/aoa_session_memory.py doctor --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
```

## Decisions

```bash
python3 scripts/generate_decision_indexes.py
python3 scripts/generate_decision_indexes.py --check
git diff --check
```
