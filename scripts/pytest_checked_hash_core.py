#!/usr/bin/env python3
"""Run one focused producer-core test with a reusable hash-only pycache.

This is an opt-in local feedback route.  The focused test runs once through
``pytest.main`` in this process.  Python bytecode writes are disabled for the
test run, while standard checked-hash bytecode is primed afterwards into a
dedicated external prefix on the first invocation.  Pytest assertion
rewriting stays in memory, so no rewritten assertion cache is reused.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_ROOT_NAME = "aoa-session-memory-checked-hash"

CORE_TARGETS: dict[str, tuple[str, str]] = {
    "privacy": (
        "scripts/aoa_session_memory_privacy.py",
        "tests/test_session_memory_privacy_core.py",
    ),
    "outbox": (
        "scripts/aoa_session_memory_outbox.py",
        "tests/test_session_memory_outbox_core.py",
    ),
    "import": (
        "scripts/aoa_session_memory_import.py",
        "tests/test_session_memory_import_core.py",
    ),
}


class CheckedHashError(RuntimeError):
    """A cache prefix or initialization input is unsafe or invalid."""


class CachePrimeWarning(CheckedHashError):
    """A non-fatal failure while populating the optional warm-cache hint."""


def _external_path(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return resolved
    raise CheckedHashError(f"{label} must be outside the owner checkout: {resolved}")


def _default_cache_prefix() -> Path:
    root = Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
    return root / DEFAULT_CACHE_ROOT_NAME


def _cache_flags(path: Path) -> int:
    try:
        with path.open("rb") as handle:
            header = handle.read(8)
    except OSError as exc:
        raise CheckedHashError(f"cannot read bytecode cache {path}: {exc}") from exc
    if len(header) < 8:
        raise CheckedHashError(f"truncated bytecode cache {path}")
    return int.from_bytes(header[4:8], "little")


def _validate_prefix(prefix: Path, *, allow_empty: bool) -> bool:
    """Validate that *prefix* is empty or contains checked-hash pycs only."""
    if prefix.exists() and not prefix.is_dir():
        raise CheckedHashError(f"cache prefix is not a directory: {prefix}")
    if not prefix.exists():
        if not allow_empty:
            raise CheckedHashError(f"cache prefix disappeared: {prefix}")
        return False
    pycs = sorted(prefix.rglob("*.pyc"))
    if not pycs:
        return False
    rewrite = [path for path in pycs if "-pytest-" in path.name]
    if rewrite:
        raise CheckedHashError(
            "cache prefix contains pytest assertion-rewrite bytecode; "
            f"choose a fresh dedicated prefix: {rewrite[0]}"
        )
    bad = [path for path in pycs if _cache_flags(path) != 3]
    if bad:
        raise CheckedHashError(
            "cache prefix contains non-checked-hash bytecode; "
            f"choose a fresh dedicated prefix: {bad[0]}"
        )
    return True


def _checkout_sources_loaded_before_configuration() -> list[Path]:
    """Return owner-checkout sources imported before the cache was configured."""
    loaded: set[Path] = set()
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if not filename or not str(filename).endswith(".py"):
            continue
        try:
            source = Path(filename).resolve()
        except (OSError, TypeError, ValueError):
            continue
        try:
            source.relative_to(REPO_ROOT)
        except ValueError:
            continue
        if source != Path(__file__).resolve():
            loaded.add(source)
    return sorted(loaded)


def _configure_process(prefix: Path) -> None:
    """Bind the process to a validated prefix before importing pytest."""
    inherited = sys.pycache_prefix
    if inherited is not None:
        try:
            inherited_path = Path(inherited).expanduser().resolve()
        except OSError as exc:
            raise CheckedHashError(
                f"cannot resolve inherited sys.pycache_prefix {inherited}: {exc}"
            ) from exc
        if inherited_path != prefix:
            raise CheckedHashError(
                "inherited sys.pycache_prefix differs from the requested "
                f"dedicated prefix ({inherited_path} != {prefix}); unset "
                "PYTHONPYCACHEPREFIX or pass the matching --cache-prefix"
            )
    preloaded = _checkout_sources_loaded_before_configuration()
    if preloaded:
        raise CheckedHashError(
            "owner-checkout Python sources were imported before cache "
            f"configuration: {preloaded[0]}"
        )
    if any(name == "pytest" or name.startswith("pytest.") for name in sys.modules):
        raise CheckedHashError("pytest was imported before cache configuration")
    prefix.mkdir(parents=True, exist_ok=True)
    sys.dont_write_bytecode = True
    sys.pycache_prefix = str(prefix)


def _pytest_args(target: str) -> list[str]:
    return [
        "-q",
        "-p",
        "no:cacheprovider",
        "--rootdir",
        str(REPO_ROOT),
        "--confcutdir",
        str(REPO_ROOT),
        target,
    ]


def _module_sources() -> set[Path]:
    sources: set[Path] = set()
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if not filename or not str(filename).endswith(".py"):
            continue
        try:
            source = Path(filename).resolve()
        except (OSError, TypeError, ValueError):
            continue
        if source.is_file():
            sources.add(source)
    return sources


def _prime_checked_hash_bytecode(
    *, core_sources: Sequence[Path], selected_test: Path
) -> None:
    """Prime imported sources and dynamic product cores without a subprocess."""
    import py_compile

    sources = _module_sources()
    explicit = [*core_sources, selected_test]
    for source in explicit:
        try:
            source = source.resolve()
        except OSError as exc:
            raise CachePrimeWarning(
                f"cannot resolve explicit source {source}: {exc}"
            ) from exc
        if not source.is_file() or source.suffix != ".py":
            raise CachePrimeWarning(f"explicit source is unavailable: {source}")
        sources.add(source)

    for source in sorted(sources):
        try:
            py_compile.compile(
                str(source),
                doraise=True,
                invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH,
            )
        except (OSError, ValueError, py_compile.PyCompileError) as exc:
            raise CachePrimeWarning(
                f"checked-hash bytecode initialization failed for {source}: {exc}"
            ) from exc

    try:
        ready = _validate_prefix(Path(sys.pycache_prefix), allow_empty=False)
    except (CheckedHashError, OSError) as exc:
        raise CachePrimeWarning(str(exc)) from exc
    if not ready:
        raise CachePrimeWarning(
            f"checked-hash initialization produced no pycs: {sys.pycache_prefix}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one focused producer-core pytest route with a reusable "
            "checked-hash bytecode prefix and python -B."
        )
    )
    parser.add_argument("--core", choices=tuple(CORE_TARGETS), required=True)
    parser.add_argument(
        "--cache-prefix",
        type=Path,
        help=(
            "external dedicated prefix (default: "
            "$TMPDIR/aoa-session-memory-checked-hash)"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source, test = CORE_TARGETS[args.core]
    try:
        prefix = _external_path(
            args.cache_prefix or _default_cache_prefix(), "cache prefix"
        )
        ready = _validate_prefix(prefix, allow_empty=True)
        _configure_process(prefix)
        os.chdir(REPO_ROOT)
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

        import pytest

        result = pytest.main(_pytest_args(test))
        if not ready:
            try:
                _prime_checked_hash_bytecode(
                    core_sources=(REPO_ROOT / source,),
                    selected_test=REPO_ROOT / test,
                )
            except CachePrimeWarning as exc:
                print(
                    f"[checked-hash] warning: cache priming skipped: {exc}",
                    file=sys.stderr,
                )
            else:
                print(f"[checked-hash] initialized {prefix}", file=sys.stderr)
        return int(result)
    except CheckedHashError as exc:
        print(f"pytest_checked_hash_core: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
