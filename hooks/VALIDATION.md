# Validation routes

Use the root [`validate` and `doctor` route](../VALIDATION.md) for shared
session-memory integrity. For hook-specific status, run:

```bash
python3 scripts/aoa_session_memory.py codex-hooks-status --workspace-root /path/to/workspace --aoa-root /path/to/workspace/.aoa
```
