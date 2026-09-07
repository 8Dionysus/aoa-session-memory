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
# Transcript-import sibling edit:
import_core_pycache="$(mktemp -d "${TMPDIR:-/tmp}/aoa-session-memory-import.XXXXXX")"
env -u PYTHONDONTWRITEBYTECODE PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPYCACHEPREFIX="$import_core_pycache" \
  python3 -m pytest -q -p no:cacheprovider --rootdir=. --confcutdir=. \
    tests/test_session_memory_import_core.py
```

Use the privacy-core command for privacy edits, the outbox-core command for
outbox edits, and the transcript-import command for transcript discovery or
selection edits. When changing the loader, source identity, or wiring around
any sibling, add the monolith identity regression:

```bash
identity_pycache="$(mktemp -d "${TMPDIR:-/tmp}/aoa-session-memory-identity.XXXXXX")"
env -u PYTHONDONTWRITEBYTECODE PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPYCACHEPREFIX="$identity_pycache" \
  python3 -m pytest -q -p no:cacheprovider --rootdir=. --confcutdir=. \
  tests/test_session_memory.py \
  -k 'generation_identity or loaded_producer_source'
```

For repeated local feedback on one focused core, the opt-in checked-hash
runner keeps one dedicated external prefix shared by the three focused cores.
Invoke it with `python3 -B`:

```bash
python3 -B scripts/pytest_checked_hash_core.py --core privacy
python3 -B scripts/pytest_checked_hash_core.py --core outbox
python3 -B scripts/pytest_checked_hash_core.py --core import
```

Each invocation runs exactly one focused test through `pytest.main()` in the
initializer process. On the first invocation, an empty prefix is bound before
pytest is imported; after the test, the runner primes checked-hash bytecode
from sources in `sys.modules` plus the selected product-core source and the
selected test, using Python's bytecode API. The shared prefix is therefore
safe across later core selections even when their source has not been primed:
Python validates an available cache per file and otherwise falls back to
source. Later invocations only run the focused test. `-B` (also enforced
in-process) preserves
pytest assertion rewriting for ordinary failure diagnostics while preventing
a persistent `*-pytest-*.pyc` cache. The runner rejects a prefix containing
timestamp-based or pytest-rewrite bytecode, so do not point it at an ordinary
or previously reused prefix. It disables pytest's result cache and creates
only a local external bytecode cache; it does not install a runtime, change
global configuration, or write a receipt or registry. This is an owner-local
feedback route, not CI, release, installed-protocol, or runtime acceptance
evidence.

The real portable CLI/copy/install checks and the full source suite remain
separate integration gates.

The checked-hash bytecode prefix must remain outside the checkout. Pytest
assertion rewriting remains enabled for diagnostics. The ordinary direct
commands above still use Python's default timestamp/size invalidation; a rapid
same-size edit within one timestamp second can reuse stale bytecode there, so
use a fresh prefix for those commands when needed. The checked-hash runner
validates source contents per file. CI's `runner.temp` prefix is fresh per job.

## Decisions

```bash
python3 scripts/generate_decision_indexes.py
python3 scripts/generate_decision_indexes.py --check
git diff --check
```
