from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = (
    REPO_ROOT
    / "evals"
    / "cases"
    / "session-memory-skill-behavior.v1.json"
)
SOURCE_GUARD_PATHS = (
    REPO_ROOT / "capabilities",
    REPO_ROOT / "config",
    REPO_ROOT / "evals",
    REPO_ROOT / "skills",
    REPO_ROOT / "scripts" / "aoa_session_memory.py",
)
REQUIRED_CRITICAL_BRANCHES = {
    "session-memory.use.route",
    "session-memory.use.query",
    "session-memory.stewardship.capture",
    "session-memory.stewardship.project",
    "session-memory.stewardship.curate",
    "session-memory.stewardship.name",
    "session-memory.stewardship.assure",
    "session-memory.adapters.codex",
}


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


legacy = _load_module(
    "aoa_session_memory_behavioral_source_tests",
    REPO_ROOT / "tests" / "test_session_memory.py",
)


def corpus() -> dict[str, Any]:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == (
        "aoa_session_memory_skill_behavior_cases_v1"
    )
    assert payload["owner_repo"] == "aoa-session-memory"
    assert payload["authority"] is False
    assert payload["cases"]
    return payload


def _source_snapshot() -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for root in SOURCE_GUARD_PATHS:
        paths = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in paths:
            if (
                not path.is_file()
                or path.is_symlink()
                or "__pycache__" in path.parts
                or path.suffix == ".pyc"
            ):
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


@pytest.fixture(scope="module", autouse=True)
def owner_source_remains_read_only() -> Any:
    before = _source_snapshot()
    yield
    assert _source_snapshot() == before


def aoa_skills_root() -> Path:
    candidates = [
        Path(os.environ["AOA_SKILLS_ROOT"]).expanduser()
        if os.environ.get("AOA_SKILLS_ROOT")
        else None,
        REPO_ROOT / ".deps" / "aoa-skills",
        REPO_ROOT.parent / "aoa-skills",
    ]
    for candidate in candidates:
        if candidate is not None and (
            candidate / "scripts" / "capability_home.py"
        ).is_file():
            return candidate.resolve()
    raise AssertionError(
        "aoa-skills owner runtime is unavailable; set AOA_SKILLS_ROOT or "
        "checkout it under .deps/aoa-skills"
    )


def run_global_route_case() -> None:
    environment = os.environ.copy()
    environment["AOA_SKILLS_ROOT"] = str(aoa_skills_root())
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "capability_route.py"),
            "discover",
            ".aoa session memory compaction hooks validation",
            "--limit",
            "4",
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["owner_admitted"] is True
    compact_ids = [
        row["id"]
        for row in payload["candidate_selection"]["candidates"]
    ]
    assert compact_ids[0] == "skill.aoa-session-memory-global-route"


def run_legacy_case(
    name: str,
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    function = getattr(legacy, name)
    parameters = inspect.signature(function).parameters
    unsupported = set(parameters) - {"tmp_path", "monkeypatch"}
    assert not unsupported, f"{name} requires unsupported fixtures: {unsupported}"
    kwargs: dict[str, Any] = {}
    if "tmp_path" in parameters:
        kwargs["tmp_path"] = tmp_path
    if "monkeypatch" in parameters:
        kwargs["monkeypatch"] = monkeypatch
    function(**kwargs)


def test_behavior_corpus_covers_every_critical_branch_and_pressure_kind() -> None:
    payload = corpus()
    cases = payload["cases"]
    assert set(payload["critical_branches"]) == REQUIRED_CRITICAL_BRANCHES
    assert {case["critical_branch"] for case in cases} == (
        REQUIRED_CRITICAL_BRANCHES
    )
    kinds = {case["scenario_kind"] for case in cases}
    assert {
        "positive",
        "positive-effect",
        "preview-apply",
        "preview-apply-replay",
        "preview-apply-postcondition",
        "recovery",
        "negative-attribution",
        "negative-interface",
        "prompt-data-injection",
        "path-injection",
    } <= kinds
    assert all(
        case["skill_ids"] or case.get("capability_ids")
        for case in cases
    )
    assert all(case["expected_effects"] for case in cases)
    assert all(case["acceptance"] for case in cases)


@pytest.mark.parametrize(
    "case",
    corpus()["cases"],
    ids=lambda case: str(case["id"]),
)
def test_controlled_skill_behavior_case(
    case: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox_home = tmp_path / "home"
    sandbox_home.mkdir()
    monkeypatch.setenv("HOME", str(sandbox_home))
    monkeypatch.setenv("CODEX_HOME", str(sandbox_home / ".codex"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(sandbox_home / ".cache"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(sandbox_home / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(sandbox_home / ".local/share"))

    def reject_network(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError(
            f"{case['id']}: behavioral sandbox forbids network access"
        )

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    monkeypatch.setattr(socket, "create_connection", reject_network)

    runner = str(case["runner"])
    if runner == "local:capability-route":
        run_global_route_case()
    else:
        prefix = "legacy:"
        assert runner.startswith(prefix)
        run_legacy_case(
            runner.removeprefix(prefix),
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
        )

    assert sandbox_home.is_dir()
