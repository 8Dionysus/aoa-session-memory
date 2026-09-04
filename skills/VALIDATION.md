# Validation routes

Use the root [focused regression route](../VALIDATION.md) for the shared
session-memory test module. For the skill projection, run:

```bash
python3 scripts/aoa_session_memory.py doctor \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --check-user-skill
```
