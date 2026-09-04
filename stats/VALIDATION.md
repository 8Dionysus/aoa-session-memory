# Validation routes

```bash
python3 scripts/validate_local_stats_port.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_session_memory.py -k local_stats
```
