"""Focused contract tests for the opt-in checked-hash core runner."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pytest_checked_hash_core_test_source",
    ROOT / "scripts" / "pytest_checked_hash_core.py",
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def _run_runner(
    root: Path, prefix: Path, *, core: str = "import"
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment.pop("PYTHONPYCACHEPREFIX", None)
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return subprocess.run(
        [
            sys.executable,
            "-B",
            str(root / "scripts" / "pytest_checked_hash_core.py"),
            "--core",
            core,
            "--cache-prefix",
            str(prefix),
        ],
        cwd=root,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _write_pyc(path: Path, flags: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * 4 + flags.to_bytes(4, "little") + b"\x00" * 8)


def _mutate_preserving_metadata(path: Path, old: bytes, new: bytes) -> None:
    assert len(old) == len(new)
    before = path.stat()
    assert path.read_bytes() == old
    path.write_bytes(new)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    after = path.stat()
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns


def test_runner_args_keep_assertion_rewrite_and_disable_result_cache() -> None:
    arguments = module._pytest_args("tests/test_session_memory_import_core.py")
    assert arguments[:3] == ["-q", "-p", "no:cacheprovider"]
    assert arguments[-1] == "tests/test_session_memory_import_core.py"
    assert "--assert=plain" not in arguments


def test_validate_prefix_accepts_checked_hash_only(tmp_path: Path) -> None:
    prefix = tmp_path / "hash-only"
    _write_pyc(prefix / "module.cpython-314.pyc", 3)
    assert module._validate_prefix(prefix, allow_empty=False) is True


def test_validate_prefix_rejects_timestamp_or_pytest_rewrite_cache(
    tmp_path: Path,
) -> None:
    timestamp_prefix = tmp_path / "timestamp"
    _write_pyc(timestamp_prefix / "module.cpython-314.pyc", 0)
    with pytest.raises(module.CheckedHashError, match="non-checked-hash"):
        module._validate_prefix(timestamp_prefix, allow_empty=False)

    rewrite_prefix = tmp_path / "rewrite"
    _write_pyc(rewrite_prefix / "test.cpython-314-pytest-9.0.3.pyc", 3)
    with pytest.raises(module.CheckedHashError, match="assertion-rewrite"):
        module._validate_prefix(rewrite_prefix, allow_empty=False)


def test_runner_rejects_unmatched_inherited_prefix(tmp_path: Path) -> None:
    requested = tmp_path / "requested"
    inherited = tmp_path / "inherited"
    environment = dict(os.environ)
    environment["PYTHONPYCACHEPREFIX"] = str(inherited)
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "scripts" / "pytest_checked_hash_core.py"),
            "--core",
            "import",
            "--cache-prefix",
            str(requested),
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 2
    assert "inherited sys.pycache_prefix differs" in result.stdout


def test_runner_reports_checkout_prefix_as_normal_cli_error() -> None:
    result = _run_runner(ROOT, ROOT / ".pytest-checked-hash-inside")
    assert result.returncode == 2
    assert "must be outside the owner checkout" in result.stdout


def test_runner_catches_same_size_same_mtime_product_test_and_auxiliary_mutations(
    tmp_path: Path,
) -> None:
    root = tmp_path / "checkout"
    scripts = root / "scripts"
    tests = root / "tests"
    scripts.mkdir(parents=True)
    tests.mkdir()
    shutil.copy2(
        ROOT / "scripts" / "pytest_checked_hash_core.py",
        scripts / "pytest_checked_hash_core.py",
    )
    for core in ("privacy", "outbox"):
        (scripts / f"aoa_session_memory_{core}.py").write_text(
            'VALUE = "unused"\n', encoding="utf-8"
        )
    product = scripts / "aoa_session_memory_import.py"
    auxiliary = scripts / "auxiliary.py"
    test = tests / "test_session_memory_import_core.py"
    product_old = (
        b'from scripts.auxiliary import VALUE as AUXILIARY_VALUE\nVALUE = "old"\n'
    )
    product_new = (
        b'from scripts.auxiliary import VALUE as AUXILIARY_VALUE\nVALUE = "new"\n'
    )
    auxiliary_old = b'VALUE = "old"\n'
    auxiliary_new = b'VALUE = "new"\n'
    test_old = (
        b"from scripts.aoa_session_memory_import import AUXILIARY_VALUE, VALUE\n"
        b"\n"
        b"def test_values_are_old():\n"
        b'    assert VALUE == "old"\n'
        b'    assert AUXILIARY_VALUE == "old"\n'
    )
    test_new = test_old.replace(b"test_values_are_old", b"test_values_are_new").replace(
        b'VALUE == "old"', b'VALUE == "new"', 1
    )
    for path, content in (
        (product, product_old),
        (auxiliary, auxiliary_old),
        (test, test_old),
    ):
        path.write_bytes(content)

    prefix = tmp_path / "cache"
    initial = _run_runner(root, prefix)
    assert initial.returncode == 0, initial.stdout
    assert list(prefix.rglob("*.pyc"))
    assert not list(prefix.rglob("*-pytest-*.pyc"))

    for path, old, new in (
        (product, product_old, product_new),
        (auxiliary, auxiliary_old, auxiliary_new),
        (test, test_old, test_new),
    ):
        before = path.stat()
        _mutate_preserving_metadata(path, old, new)
        try:
            changed = _run_runner(root, prefix)
            assert changed.returncode == 1, (path, changed.stdout)
        finally:
            path.write_bytes(old)
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        restored = _run_runner(root, prefix)
        assert restored.returncode == 0, (path, restored.stdout)


def test_runner_preserves_pytest_status_when_cache_priming_fails(
    tmp_path: Path,
) -> None:
    root = tmp_path / "checkout"
    scripts = root / "scripts"
    tests = root / "tests"
    scripts.mkdir(parents=True)
    tests.mkdir()
    shutil.copy2(
        ROOT / "scripts" / "pytest_checked_hash_core.py",
        scripts / "pytest_checked_hash_core.py",
    )
    product = scripts / "aoa_session_memory_import.py"
    product.write_text('VALUE = "ok"\n', encoding="utf-8")
    test = tests / "test_session_memory_import_core.py"
    test.write_text(
        "from pathlib import Path\n"
        "from scripts.aoa_session_memory_import import VALUE\n"
        "\n"
        "def test_ok_then_remove_source():\n"
        '    assert VALUE == "ok"\n'
        '    Path(__file__).parents[1].joinpath("scripts", '
        '"aoa_session_memory_import.py").unlink()\n',
        encoding="utf-8",
    )

    result = _run_runner(root, tmp_path / "cache")
    assert result.returncode == 0, result.stdout
    assert "cache priming skipped" in result.stdout
