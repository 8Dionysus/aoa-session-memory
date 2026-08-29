from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

release_check = importlib.import_module("release_check")
validate_release_artifacts = importlib.import_module("validate_release_artifacts")
validation_evidence_graph = importlib.import_module("validation_evidence_graph")
validation_lanes = importlib.import_module("validation_lanes")


def _git(root: Path, *args: str) -> str:
    import subprocess

    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _sdk_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "aoa-sdk"
    runner = root / validation_evidence_graph.SDK_RUNNER_RELATIVE_PATH
    runner.parent.mkdir(parents=True)
    runner.write_text("raise SystemExit(0)\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "validation@example.invalid")
    _git(root, "config", "user.name", "Validation Test")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "fixture")
    monkeypatch.setattr(validation_evidence_graph, "SDK_PIN", _git(root, "rev-parse", "HEAD"))
    return root


def test_validation_lane_manifest_keeps_full_serial_oracle() -> None:
    steps = validation_lanes.lane_command_sequence("standalone-full")

    assert [step.label for step in steps] == [
        "decision index parity",
        "current public tree audit",
        "retained Git history inventory",
        "validation graph contract tests",
        "portable source tests",
        "MCP package release check",
        "reproducible artifacts and installed protocol",
        "post-build public tree audit",
    ]


def test_owner_graph_preserves_serial_leaf_scope() -> None:
    validation_evidence_graph.require_schedule_equivalent_serial_inventory()


def test_public_source_shadow_route_does_not_pull_full_final_fan_in() -> None:
    payload = json.loads(
        validation_evidence_graph.MANIFEST_PATH.read_text(encoding="utf-8")
    )
    route = next(item for item in payload["routes"] if item["id"] == "public-source")

    assert route["claims"] == ["public-source-safety"]
    public_claim = next(
        item for item in payload["claims"] if item["id"] == "public-source-safety"
    )
    assert public_claim["required_evidence"] == ["current-public-tree-audit"]
    history_claim = next(
        item for item in payload["claims"] if item["id"] == "retained-history-safety"
    )
    assert history_claim["required_evidence"] == ["retained-history-inventory"]
    post_claim = next(
        item
        for item in payload["claims"]
        if item["id"] == "validation-side-effect-safety"
    )
    assert post_claim["required_evidence"] == ["post-build-public-tree-audit"]


def test_independent_evidence_nodes_do_not_wait_for_duplicate_preflight() -> None:
    payload = json.loads(
        validation_evidence_graph.MANIFEST_PATH.read_text(encoding="utf-8")
    )
    nodes = {item["id"]: item for item in payload["nodes"]}
    independent = set(nodes) - {
        "validation-graph-contract",
        "post-build-public-source-audit",
    }

    assert all(nodes[node_id]["depends_on"] == [] for node_id in independent)
    assert set(
        nodes["post-build-public-source-audit"]["depends_on"]
    ) == set(nodes) - {"post-build-public-source-audit"}


def test_inventory_guard_reports_an_omitted_serial_obligation(tmp_path: Path) -> None:
    payload = json.loads(validation_evidence_graph.MANIFEST_PATH.read_text(encoding="utf-8"))
    node = next(item for item in payload["nodes"] if item["id"] == "decision-indexes")
    node["steps"].pop()
    manifest = tmp_path / "validation-graph.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(validation_evidence_graph.AdapterError, match="serial leaf scope"):
        validation_evidence_graph.require_schedule_equivalent_serial_inventory(manifest)


def test_inventory_guard_rejects_unreviewed_source_selection(tmp_path: Path) -> None:
    payload = json.loads(validation_evidence_graph.MANIFEST_PATH.read_text(encoding="utf-8"))
    node = next(item for item in payload["nodes"] if item["id"] == "portable-source-tests")
    node["steps"][0]["argv"].append("-k")
    node["steps"][0]["argv"].append("fast")
    manifest = tmp_path / "validation-graph.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(validation_evidence_graph.AdapterError, match="serial leaf scope"):
        validation_evidence_graph.require_schedule_equivalent_serial_inventory(manifest)


def test_sdk_runner_requires_exact_clean_git_top_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sdk_root = _sdk_checkout(tmp_path, monkeypatch)
    runner = validation_evidence_graph.require_pinned_sdk_runner(sdk_root)
    assert runner == sdk_root / validation_evidence_graph.SDK_RUNNER_RELATIVE_PATH

    nested = sdk_root / "nested"
    nested.mkdir()
    with pytest.raises(validation_evidence_graph.AdapterError, match="Git top-level"):
        validation_evidence_graph.require_pinned_sdk_runner(nested)

    runner.write_text("raise SystemExit(1)\n", encoding="utf-8")
    with pytest.raises(validation_evidence_graph.AdapterError, match="must be clean"):
        validation_evidence_graph.require_pinned_sdk_runner(sdk_root)


def test_release_check_defaults_to_graph_and_retains_serial_rollback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []
    serial_calls: list[str] = []
    monkeypatch.delenv(release_check.VALIDATION_MODE_ENV, raising=False)
    monkeypatch.setattr(
        release_check,
        "run_step",
        lambda label, command: calls.append((label, command)) or 0,
    )
    monkeypatch.setattr(
        release_check,
        "run_serial",
        lambda: serial_calls.append("serial") or 0,
    )

    assert release_check.main([]) == 0
    assert calls == [
        (
            "full owner claim/evidence validation graph",
            (sys.executable, release_check.GRAPH_ADAPTER, "--profile", "full"),
        )
    ]

    calls.clear()
    assert release_check.main(["--mode", "serial"]) == 0
    assert calls == []
    assert serial_calls == ["serial"]

    receipt = tmp_path / "receipt.json"
    sdk_root = tmp_path / "sdk"
    assert (
        release_check.main(
            [
                "--receipt",
                str(receipt),
                "--max-workers",
                "2",
                "--sdk-root",
                str(sdk_root),
            ]
        )
        == 0
    )
    assert calls[-1][1] == (
        sys.executable,
        release_check.GRAPH_ADAPTER,
        "--profile",
        "full",
        "--receipt",
        str(receipt),
        "--max-workers",
        "2",
        "--sdk-root",
        str(sdk_root),
    )


def _artifact_step(
    step_id: str,
    argv: list[str] | tuple[str, ...],
    *,
    artifacts: list[dict[str, str]],
) -> dict[str, object]:
    if step_id.startswith("build-"):
        payload: dict[str, object] = {
            "artifacts": artifacts,
            "source_unchanged": True,
        }
    elif step_id == "synthetic-bootstrap":
        payload = {
            "schema": "aoa_session_memory_synthetic_demo_v1",
            "results": {"install_ok": True, "sync_ok": True},
        }
    elif step_id == "installed-stdio-protocol":
        payload = {"schema": "aoa_session_memory_synthetic_mcp_smoke_v1", "ok": True}
    else:
        payload = {}
    stdout = json.dumps(payload)
    return {
        "id": step_id,
        "argv": list(argv),
        "returncode": 0,
        "duration_seconds": 0.01,
        "stdout_sha256": "fixture",
        "stderr_sha256": "fixture",
        "stdout_tail": stdout,
        "stderr_tail": "",
        "_stdout": stdout,
    }


def test_release_artifact_validator_binds_reproduction_and_installed_protocol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "release"
    root.mkdir()
    identity = {
        "git_commit": "a" * 40,
        "git_tree": "b" * 40,
        "status_sha256": "c" * 64,
        "dirty": False,
    }
    artifacts = [
        {"filename": "aoa_session_memory_mcp-0.1.0-py3-none-any.whl", "sha256": "d" * 64},
        {"filename": "aoa_session_memory_mcp-0.1.0.tar.gz", "sha256": "e" * 64},
    ]

    def fake_run(step_id: str, argv: list[str], **_kwargs: object) -> dict[str, object]:
        if step_id == "build-a":
            outdir = Path(argv[argv.index("--outdir") + 1])
            outdir.mkdir(parents=True)
            (outdir / artifacts[0]["filename"]).write_bytes(b"wheel")
        return _artifact_step(step_id, argv, artifacts=artifacts)

    monkeypatch.setattr(validate_release_artifacts.tempfile, "mkdtemp", lambda **_kwargs: str(root))
    monkeypatch.setattr(validate_release_artifacts, "repository_identity", lambda: dict(identity))
    monkeypatch.setattr(validate_release_artifacts, "_run", fake_run)

    payload = validate_release_artifacts.validate_release_artifacts()

    assert payload["ok"] is True
    assert payload["artifact_identity"]["reproducible"] is True
    assert payload["installed_protocol"] == {"bootstrap_ok": True, "protocol_ok": True}
    assert payload["repository_identity"]["stable"] is True
    assert all("_stdout" not in step for step in payload["steps"])


def test_release_artifact_validator_fails_closed_on_artifact_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "release"
    root.mkdir()
    identity = {
        "git_commit": "a" * 40,
        "git_tree": "b" * 40,
        "status_sha256": "c" * 64,
        "dirty": False,
    }

    def fake_run(step_id: str, argv: list[str], **_kwargs: object) -> dict[str, object]:
        digest = "d" * 64 if step_id == "build-a" else "e" * 64
        artifacts = [{"filename": "package.whl", "sha256": digest}]
        if step_id == "build-a":
            outdir = Path(argv[argv.index("--outdir") + 1])
            outdir.mkdir(parents=True)
            (outdir / "package.whl").write_bytes(b"wheel")
        return _artifact_step(step_id, argv, artifacts=artifacts)

    monkeypatch.setattr(validate_release_artifacts.tempfile, "mkdtemp", lambda **_kwargs: str(root))
    monkeypatch.setattr(validate_release_artifacts, "repository_identity", lambda: dict(identity))
    monkeypatch.setattr(validate_release_artifacts, "_run", fake_run)

    payload = validate_release_artifacts.validate_release_artifacts()

    assert payload["ok"] is False
    assert "not byte-reproducible" in payload["error"]
    assert payload["artifact_identity"]["reproducible"] is False
