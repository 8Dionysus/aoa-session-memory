from __future__ import annotations

import importlib
import json
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "repo-validation.yml"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

pytest_scheduler_experiment = importlib.import_module("pytest_scheduler_experiment")
validation_scheduler_experiment = importlib.import_module(
    "validation_scheduler_experiment"
)
validation_lanes = importlib.import_module("validation_lanes")


def test_scheduler_targets_follow_current_full_lane() -> None:
    step = next(
        item
        for item in validation_lanes.lane_command_sequence("standalone-full")
        if item.label == "portable source tests"
    )

    prefix = (sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider")
    assert step.command[: len(prefix)] == prefix
    targets = step.command[len(prefix) :]
    assert pytest_scheduler_experiment.source_test_targets() == targets
    assert all(target.startswith("tests/") for target in targets)


def _hosted_workflow_body() -> str:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    return next(
        step["run"]
        for step in workflow["jobs"]["hosted_scheduler_trials"]["steps"]
        if "overall_status" in step.get("run", "")
    )


def test_hosted_scheduler_workflow_is_opt_in_and_preserves_ordinary_route() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = workflow.get("on", workflow.get(True))
    inputs = triggers["workflow_dispatch"]["inputs"]

    assert inputs["scheduler_trials"]["type"] == "boolean"
    assert inputs["scheduler_trials"]["default"] is False
    assert inputs["scheduler_python"]["type"] == "choice"
    assert set(inputs["scheduler_python"]["options"]) == {"3.11", "3.14"}
    assert "push" in triggers and "pull_request" in triggers
    standalone = workflow["jobs"]["standalone"]
    ordinary = next(
        step
        for step in standalone["steps"]
        if step.get("run") == "python scripts/pytest_scheduler_experiment.py --method static2"
    )
    assert ordinary["run"] == "python scripts/pytest_scheduler_experiment.py --method static2"
    hosted = workflow["jobs"]["hosted_scheduler_trials"]
    assert "workflow_dispatch" in hosted["if"]
    upload = next(step for step in hosted["steps"] if "upload-artifact@" in step.get("uses", ""))
    assert upload["if"] == "always()"
    assert upload["with"]["path"].splitlines()[0].startswith("${{ steps.")


def _run_hosted_workflow_body(
    tmp_path: Path, *, failure: str | None = None
) -> tuple[subprocess.CompletedProcess[str], Path, list[dict[str, object]]]:
    trial_root = tmp_path / "pytest-scheduler-trials.abc123"
    (trial_root / "tmp").mkdir(parents=True)
    calls_path = tmp_path / "shim-calls.jsonl"
    real_python = Path(sys.executable)
    shim = tmp_path / "python"
    shim.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import os
            import sys
            from pathlib import Path

            args = sys.argv[1:]
            real_python = os.environ["REAL_PYTHON"]
            if not args or args[0] == "-" or args[0].endswith("validation_scheduler_experiment.py"):
                os.execv(real_python, [real_python, *args])
            if not args[0].endswith("pytest_scheduler_experiment.py"):
                os.execv(real_python, [real_python, *args])

            def value(flag):
                return args[args.index(flag) + 1]

            method = value("--method")
            pair_id = value("--pair-id")
            artifact = Path(value("--artifact-root"))
            receipt = Path(value("--receipt"))
            timing = args[args.index("--timing-receipt") + 1] if "--timing-receipt" in args else None
            record = {
                "method": method,
                "pair_id": pair_id,
                "artifact": str(artifact),
                "timing": timing,
                "artifact_nonempty": artifact.exists() and any(artifact.iterdir()),
                "argv": args,
            }
            with Path(os.environ["SHIM_CALLS"]).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\\n")
            if record["artifact_nonempty"]:
                raise SystemExit("artifact root was not empty")
            failure = os.environ.get("SHIM_FAILURE", "")
            mode = failure.split(":")[-1] if failure.startswith(pair_id + ":" + method + ":") else ""
            if mode == "missing":
                raise SystemExit(23)
            artifact.mkdir(parents=True, exist_ok=True)
            ok = mode != "failed"
            wall = {"serial": 200.0, "static2": 100.0, "static2-balanced": 40.0}[method]
            payload = {
                "schema_version": "aoa_session_memory_pytest_scheduler_trial_v1",
                "method": {"name": method},
                "pair_id": pair_id,
                "trial": int(value("--trial")),
                "wall_seconds": wall,
                "ok": ok,
                "error": None if ok else "injected failure",
                "repository_identity": {"before": {"identity_sha256": "same"}, "stable": True},
                "environment_identity": {"identity_sha256": "environment", "runtime": {"github_actions": True}},
                "cache": {"observed_state_before": "disabled"},
                "corpus": {"set_sha256": "corpus"},
                "execution": {"coverage_complete": True},
                "receipt_path": str(receipt),
            }
            receipt.write_text(json.dumps(payload) + "\\n", encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{tmp_path}{os.pathsep}{environment['PATH']}",
            "REAL_PYTHON": str(real_python),
            "SHIM_CALLS": str(calls_path),
            "SCHEDULER_TRIAL_ROOT": str(trial_root),
            "SCHEDULER_PYTHON": "3.14",
            "TMPDIR": str(trial_root / "tmp"),
        }
    )
    if failure is not None:
        environment["SHIM_FAILURE"] = failure
    result = subprocess.run(
        ["bash", "-c", _hosted_workflow_body()],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    calls = [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines()]
    return result, trial_root, calls


def test_hosted_scheduler_workflow_runs_three_counterbalanced_triplets(tmp_path: Path) -> None:
    result, trial_root, calls = _run_hosted_workflow_body(tmp_path)

    assert result.returncode == 0, result.stderr
    assert len(calls) == 9
    by_pair: dict[str, list[dict[str, object]]] = {}
    for call in calls:
        by_pair.setdefault(str(call["pair_id"]), []).append(call)
        assert call["artifact_nonempty"] is False
    assert len(by_pair) == 3
    orders = []
    for pair_id, pair_calls in sorted(by_pair.items()):
        assert {str(call["method"]) for call in pair_calls} == {
            "serial",
            "static2",
            "static2-balanced",
        }
        assert pair_calls[0]["method"] == "serial"
        balanced = next(call for call in pair_calls if call["method"] == "static2-balanced")
        assert Path(str(balanced["timing"])) == Path(str(pair_calls[0]["artifact"])) / "trial.json"
        orders.append(tuple(str(call["method"]) for call in pair_calls[1:]))
    assert set(orders) == {
        ("static2", "static2-balanced"),
        ("static2-balanced", "static2"),
    }
    assert orders[0] != orders[1] and orders[1] != orders[2]
    comparison = json.loads((trial_root / "comparison.json").read_text(encoding="utf-8"))
    balanced = next(item for item in comparison["candidates"] if item["candidate"] == "static2-balanced")
    assert comparison["receipt_count"] == 9
    assert balanced["resource_evidence_complete"] is False
    assert balanced["admission_ready"] is False


def test_hosted_scheduler_workflow_keeps_failed_trial_evidence_and_fails(
    tmp_path: Path,
) -> None:
    result, trial_root, calls = _run_hosted_workflow_body(
        tmp_path, failure="hosted-py314-p02:static2-balanced:failed"
    )

    assert result.returncode != 0
    assert len(calls) == 9
    failed_root = trial_root / "hosted-py314-p02" / "static2-balanced"
    failed_receipt = json.loads(
        (failed_root / "trial.json").read_text(encoding="utf-8")
    )
    assert failed_receipt["ok"] is False
    status = json.loads((trial_root / "comparison-status.json").read_text())
    assert status["status"] == "skipped"
    assert not (trial_root / "comparison.json").exists()
    failed_status = next(
        line.split("\t")
        for line in (trial_root / "trial-status.tsv").read_text(encoding="utf-8").splitlines()[1:]
        if "hosted-py314-p02\tstatic2-balanced\t" in line
    )
    assert failed_status[2] == "0"
    assert failed_status[3] != "0"
    stderr = trial_root / "invocation-logs" / "hosted-py314-p02" / "static2-balanced" / "runner.stderr.log"
    assert "scheduler trial receipt is not ok" in stderr.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "bad_target",
    (
        "--lf",
        "../tests/outside.py",
        "tests/../outside.py",
        "tests\\inside.py",
        "tests/bad\x00.py",
        "tests/test_session_memory.py",
    ),
)
def test_scheduler_target_binding_rejects_invalid_metadata(
    tmp_path: Path, bad_target: str
) -> None:
    payload = json.loads(validation_lanes.MANIFEST_PATH.read_text(encoding="utf-8"))
    source_step = next(
        item
        for item in payload["command_sequences"]["standalone_full"]
        if item["label"] == "portable source tests"
    )
    source_step["command"].append(bad_target)
    manifest = tmp_path / "validation_lanes.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        pytest_scheduler_experiment.ExperimentError,
        match="only repo-relative tests/ targets",
    ):
        pytest_scheduler_experiment.source_test_targets(manifest)


def test_scheduler_cli_allows_ordinary_route_without_experiment_receipts() -> None:
    args = pytest_scheduler_experiment.build_parser().parse_args(
        ["--method", "static2"]
    )

    assert args.artifact_root is None
    assert args.receipt is None
    with pytest.raises(
        pytest_scheduler_experiment.ExperimentError,
        match="--receipt requires --artifact-root",
    ):
        pytest_scheduler_experiment.run_trial(
            pytest_scheduler_experiment.build_parser().parse_args(
                ["--method", "static2", "--receipt", "/tmp/trial.json"]
            )
        )


def test_ordinary_route_uses_fresh_external_bytecode_prefix(tmp_path: Path) -> None:
    pycache_root = tmp_path / "artifact" / "pycache"
    env, cache = pytest_scheduler_experiment._cache_environment(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": "/stale-prefix",
        },
        pycache_root=None,
        ordinary_pycache_root=pycache_root,
        repository={},
        environment={},
        method=pytest_scheduler_experiment.METHODS["static2"],
    )

    assert env["PYTHONPYCACHEPREFIX"] == str(pycache_root.resolve())
    assert "PYTHONDONTWRITEBYTECODE" not in env
    assert cache == {
        "enabled": True,
        "observed_state_before": "fresh-per-invocation",
        "reusable": False,
    }
    assert pycache_root.is_dir()


@pytest.mark.parametrize("failed_step", (None, "shard-1"))
def test_ephemeral_scheduler_binds_and_reclaims_each_pytest_temp_root(
    monkeypatch: pytest.MonkeyPatch,
    failed_step: str | None,
) -> None:
    nodeids = ("tests/test_example.py::test_one", "tests/test_example.py::test_two")
    calls: list[tuple[str, Path, Path]] = []
    artifact_roots: list[Path] = []
    fixture_was_created: list[bool] = []

    def fake_run_process(
        step_id: str,
        argv: list[str],
        *,
        env: dict[str, str],
        artifact_root: Path,
        timeout_seconds: float,
    ) -> dict[str, object]:
        del timeout_seconds
        basetemp = Path(argv[argv.index("--basetemp") + 1])
        assert basetemp.parent.is_dir()
        basetemp.mkdir()
        fixture_path = basetemp / "fixture-marker"
        fixture_path.mkdir()
        probe_path = Path(env[pytest_scheduler_experiment.PROBE_LOG_ENV])
        probe_path.parent.mkdir(parents=True, exist_ok=True)
        if step_id == "collection":
            events = [{"event": "collection", "worker": "controller", "nodeids": list(nodeids)}]
        else:
            junit_index = argv.index("--junitxml")
            selected = argv[junit_index + 2 :]
            events = [
                {
                    "event": "report",
                    "nodeid": nodeid,
                    "when": "call",
                    "outcome": "passed",
                    "duration_seconds": 0.001,
                }
                for nodeid in selected
            ]
        probe_path.write_text(
            "".join(json.dumps(event) + "\n" for event in events),
            encoding="utf-8",
        )
        artifact_roots.append(artifact_root)
        calls.append((step_id, basetemp, fixture_path))
        fixture_was_created.append(fixture_path.is_dir())
        return {
            "id": step_id,
            "returncode": 1 if step_id == failed_step else 0,
            "timed_out": False,
            "stdout": {"path": str(artifact_root / f"{step_id}.stdout"), "tail": ""},
            "stderr": {"path": str(artifact_root / f"{step_id}.stderr"), "tail": ""},
        }

    monkeypatch.setattr(pytest_scheduler_experiment, "source_test_targets", lambda: nodeids)
    monkeypatch.setattr(pytest_scheduler_experiment, "_run_process", fake_run_process)
    args = pytest_scheduler_experiment.build_parser().parse_args(["--method", "static2"])

    result = pytest_scheduler_experiment.run_trial(args)

    assert result["ok"] is (failed_step is None)
    assert {step_id for step_id, _, _ in calls} == {"collection", "shard-1", "shard-2"}
    assert len({basetemp for _, basetemp, _ in calls}) == 3
    artifact_root = artifact_roots[0]
    assert all(
        basetemp.is_relative_to(artifact_root / "pytest-basetemp")
        for _, basetemp, _ in calls
    )
    assert all(fixture_was_created)
    assert artifact_roots and not artifact_roots[0].exists()


def test_scheduler_plan_keeps_all_candidates_in_shadow() -> None:
    plan = validation_scheduler_experiment.candidate_plan()
    methods = {item["name"]: item for item in plan["methods"]}

    assert plan["baseline"] == "serial"
    assert plan["incumbent"] == "static2"
    assert {
        "serial-plain",
        "xdist2-loadfile",
        "xdist2-load",
        "xdist2-worksteal",
        "xdist4-loadfile",
        "xdist4-load",
        "xdist4-worksteal",
        "static2",
        "static2-plain",
        "static2-balanced",
        "static2-balanced-plain",
        "static4",
        "static4-plain",
        "static4-balanced",
        "static4-balanced-plain",
    } <= methods.keys()
    assert methods["xdist4-worksteal"]["hosted_shadow_preferred"] is True
    assert plan["admission_rule"]["zero_false_green"] is True


def test_static_shards_are_exact_disjoint_and_deterministic() -> None:
    nodeids = [f"tests/test_example.py::test_case[{index}]" for index in range(11)]

    first = pytest_scheduler_experiment.static_shards(nodeids, 4)
    second = pytest_scheduler_experiment.static_shards(nodeids, 4)

    assert first == second
    assert set().union(*map(set, first)) == set(nodeids)
    assert sum(len(shard) for shard in first) == len(nodeids)
    assert all(set(left).isdisjoint(right) for i, left in enumerate(first) for right in first[i + 1 :])


def test_duration_balanced_shards_preserve_corpus_and_balance_heavy_cases() -> None:
    nodeids = [f"tests/test_example.py::test_case_{index}" for index in range(6)]
    durations = {
        nodeids[0]: 10.0,
        nodeids[1]: 9.0,
        nodeids[2]: 2.0,
        nodeids[3]: 2.0,
        nodeids[4]: 1.0,
        nodeids[5]: 1.0,
    }

    shards, projected = pytest_scheduler_experiment.duration_balanced_static_shards(
        nodeids, 2, durations
    )

    assert set().union(*map(set, shards)) == set(nodeids)
    assert sum(len(shard) for shard in shards) == len(nodeids)
    assert max(projected) - min(projected) <= 1.0


def test_duration_balanced_shards_keep_cases_without_hints() -> None:
    nodeids = [f"tests/test_example.py::test_case_{index}" for index in range(5)]

    shards, _ = pytest_scheduler_experiment.duration_balanced_static_shards(
        nodeids,
        2,
        {nodeids[0]: 10.0},
    )

    assert set().union(*map(set, shards)) == set(nodeids)
    assert sum(len(shard) for shard in shards) == len(nodeids)


def _receipt(
    method: str,
    pair_id: str,
    wall_seconds: float,
    *,
    ok: bool = True,
    identity: str = "same",
    hosted: bool = False,
    resource: bool = False,
) -> dict[str, object]:
    environment: dict[str, object] = {"identity_sha256": "environment"}
    if hosted:
        environment["runtime"] = {"github_actions": True}
    payload: dict[str, object] = {
        "schema_version": "aoa_session_memory_pytest_scheduler_trial_v1",
        "method": {"name": method},
        "pair_id": pair_id,
        "wall_seconds": wall_seconds,
        "ok": ok,
        "repository_identity": {
            "before": {"identity_sha256": identity},
            "stable": True,
        },
        "environment_identity": environment,
        "cache": {"observed_state_before": "disabled"},
        "corpus": {"set_sha256": "corpus"},
        "execution": {"coverage_complete": True},
    }
    if not resource:
        return payload
    receipt_path = Path(f"/tmp/aoa-{pair_id}-{method}.json")
    payload["receipt_path"] = str(receipt_path)
    launch = {
        "schema": "abyss_machine_resource_launch_v1",
        "request": {
            "command": [
                "python",
                "scripts/pytest_scheduler_experiment.py",
                "--method",
                method,
                "--receipt",
                str(receipt_path),
            ],
            "memory_demand_mib": 1,
            "force": False,
        },
        "plan": {"decision": "allow"},
        "execution": {
            "returncode": 0 if ok else 1,
            "systemd": {"service_runtime": "1s", "cpu_time_consumed": "1s"},
        },
        "startup_admission": {
            "demand_observation": {
                "peaks": {
                    "ok": True,
                    "unit": "trial.service",
                    "memory_peak_mib": 1.0,
                    "memory_swap_peak_mib": 0.0,
                    "footprint_peak_mib": 1.0,
                }
            }
        },
    }
    return validation_scheduler_experiment.bind_resource_envelope(payload, launch)


def test_comparison_never_promotes_from_one_fast_pair() -> None:
    result = validation_scheduler_experiment.compare_receipts(
        [_receipt("serial", "pair-1", 100), _receipt("static2", "pair-1", 40)]
    )

    candidate = result["candidates"][0]
    assert candidate["latency_rule_passed"] is False
    assert candidate["admission_ready"] is False
    assert candidate["decision"] == "retain_in_shadow"


def test_comparison_rejects_incomparable_or_red_pairs() -> None:
    result = validation_scheduler_experiment.compare_receipts(
        [
            _receipt("serial", "pair-1", 100),
            _receipt("static2", "pair-1", 40, identity="different"),
            _receipt("serial", "pair-2", 100),
            _receipt("static2", "pair-2", 40, ok=False),
        ]
    )

    candidate = result["candidates"][0]
    assert candidate["valid_pair_count"] == 0
    assert candidate["admission_ready"] is False


def test_static2_keeps_serial_admission_without_self_comparison() -> None:
    receipts = [
        receipt
        for pair_id in ("pair-1", "pair-2", "pair-3")
        for receipt in (
            _receipt("serial", pair_id, 100, hosted=True, resource=True),
            _receipt("static2", pair_id, 40, hosted=True, resource=True),
        )
    ]

    result = validation_scheduler_experiment.compare_receipts(receipts)
    static2 = next(item for item in result["candidates"] if item["candidate"] == "static2")

    assert static2["incumbent_comparison_required"] is False
    assert static2["incumbent_comparison_complete"] is True
    assert static2["admission_ready"] is True


def test_contender_requires_positive_paired_median_benefit_over_static2() -> None:
    receipts = [
        receipt
        for pair_id in ("pair-1", "pair-2", "pair-3")
        for receipt in (
            _receipt("serial", pair_id, 200, hosted=True, resource=True),
            _receipt("static2", pair_id, 100, hosted=True, resource=True),
            _receipt("static2-balanced", pair_id, 110, hosted=True, resource=True),
        )
    ]

    result = validation_scheduler_experiment.compare_receipts(receipts)
    contender = next(
        item for item in result["candidates"] if item["candidate"] == "static2-balanced"
    )

    assert contender["latency_rule_passed"] is True
    assert contender["incumbent_comparison_complete"] is True
    assert contender["incumbent_benefit_seconds"] == -10.0
    assert contender["incumbent_benefit_positive"] is False
    assert contender["admission_ready"] is False
    assert any("positive median benefit" in item for item in contender["incumbent_blockers"])


def test_contender_reports_complete_static2_comparison_before_admission() -> None:
    receipts = [
        receipt
        for pair_id in ("pair-1", "pair-2", "pair-3")
        for receipt in (
            _receipt("serial", pair_id, 200, hosted=True, resource=True),
            _receipt("static2", pair_id, 100, hosted=True, resource=True),
            _receipt("static2-balanced", pair_id, 40, hosted=True, resource=True),
        )
    ]

    result = validation_scheduler_experiment.compare_receipts(receipts)
    contender = next(
        item for item in result["candidates"] if item["candidate"] == "static2-balanced"
    )

    assert contender["incumbent"] == "static2"
    assert contender["incumbent_valid_pair_count"] == 3
    assert contender["incumbent_hosted_pair_count"] == 3
    assert contender["incumbent_comparison_complete"] is True
    assert contender["incumbent_benefit_seconds"] == 60.0
    assert contender["resource_evidence_complete"] is True
    assert contender["admission_ready"] is True


def _balanced_triplet(
    pair_id: str,
    serial_wall: float,
    incumbent_wall: float,
    contender_wall: float,
    *,
    hosted: bool,
    contender_ok: bool = True,
    resource: bool = True,
) -> tuple[dict[str, object], ...]:
    return (
        _receipt("serial", pair_id, serial_wall, hosted=hosted, resource=resource),
        _receipt("static2", pair_id, incumbent_wall, hosted=hosted, resource=resource),
        _receipt(
            "static2-balanced",
            pair_id,
            contender_wall,
            ok=contender_ok,
            hosted=hosted,
            resource=resource,
        ),
    )


@pytest.mark.parametrize("failure_kind", ("candidate_failure", "nonfinite_incumbent"))
def test_all_supplied_candidate_trials_stay_in_the_admission_denominator(
    failure_kind: str,
) -> None:
    receipts = [
        receipt
        for pair_id in ("pair-1", "pair-2", "pair-3")
        for receipt in _balanced_triplet(
            pair_id, 200, 100, 40, hosted=True
        )
    ]
    if failure_kind == "candidate_failure":
        receipts.extend(_balanced_triplet("pair-4", 200, 100, 40, hosted=True, contender_ok=False))
    else:
        extra = list(_balanced_triplet("pair-4", 200, 100, 40, hosted=True))
        extra[1]["wall_seconds"] = float("inf")
        receipts.extend(extra)

    result = validation_scheduler_experiment.compare_receipts(receipts)
    contender = next(
        item for item in result["candidates"] if item["candidate"] == "static2-balanced"
    )

    assert contender["candidate_trial_count"] == 4
    assert contender["candidate_comparison_complete"] is False
    assert contender["admission_ready"] is False


def test_incumbent_benefit_uses_hosted_cohort_and_reports_local_separately() -> None:
    receipts = [
        receipt
        for pair_id in ("hosted-1", "hosted-2", "hosted-3")
        for receipt in _balanced_triplet(
            pair_id, 200, 100, 110, hosted=True
        )
    ]
    receipts.extend(
        receipt
        for pair_id in ("local-1", "local-2", "local-3")
        for receipt in _balanced_triplet(
            pair_id, 200, 180, 1, hosted=False
        )
    )

    result = validation_scheduler_experiment.compare_receipts(receipts)
    contender = next(
        item for item in result["candidates"] if item["candidate"] == "static2-balanced"
    )

    assert contender["incumbent_hosted_pair_count"] == 3
    assert contender["incumbent_local_pair_count"] == 3
    assert contender["incumbent_benefit_seconds"] == -10.0
    assert contender["incumbent_benefit_positive"] is False
    assert contender["admission_ready"] is False


def test_incumbent_benefit_uses_median_of_paired_deltas() -> None:
    receipts = [
        receipt
        for pair_id, values in (
            ("pair-1", (500, 10, 11)),
            ("pair-2", (500, 100, 99)),
            ("pair-3", (500, 101, 102)),
        )
        for receipt in _balanced_triplet(pair_id, *values, hosted=True)
    ]

    result = validation_scheduler_experiment.compare_receipts(receipts)
    contender = next(
        item for item in result["candidates"] if item["candidate"] == "static2-balanced"
    )

    assert contender["incumbent_median_wall_seconds"] == 100.0
    assert contender["median_candidate_vs_incumbent_wall_seconds"] == 99.0
    assert contender["incumbent_benefit_seconds"] == -1.0
    assert contender["incumbent_benefit_basis"] == "median_of_paired_deltas"
    assert contender["incumbent_benefit_positive"] is False
    assert contender["admission_ready"] is False


def test_local_resource_cohort_can_support_hosted_latency_admission() -> None:
    receipts = [
        receipt
        for pair_id in ("hosted-1", "hosted-2", "hosted-3")
        for receipt in _balanced_triplet(
            pair_id, 200, 100, 40, hosted=True, resource=False
        )
    ]
    receipts.extend(
        receipt
        for pair_id in ("local-1", "local-2", "local-3")
        for receipt in _balanced_triplet(
            pair_id, 200, 100, 40, hosted=False, resource=True
        )
    )

    result = validation_scheduler_experiment.compare_receipts(receipts)
    contender = next(
        item for item in result["candidates"] if item["candidate"] == "static2-balanced"
    )

    assert contender["hosted_pair_count"] == 3
    assert contender["resource_pair_count"] == 3
    assert contender["resource_hosted_pair_count"] == 0
    assert contender["resource_evidence_complete"] is True
    assert contender["admission_ready"] is True


def test_truthy_non_resource_shape_is_not_resource_evidence() -> None:
    receipts = [
        receipt
        for pair_id in ("pair-1", "pair-2", "pair-3")
        for receipt in _balanced_triplet(
            pair_id, 200, 100, 40, hosted=True
        )
    ]
    for receipt in receipts:
        if receipt["method"]["name"] != "serial":
            receipt["resource_envelope"] = "present-but-not-a-binding"

    result = validation_scheduler_experiment.compare_receipts(receipts)
    contender = next(
        item for item in result["candidates"] if item["candidate"] == "static2-balanced"
    )

    assert contender["resource_evidence_complete"] is False
    assert contender["admission_ready"] is False


def test_generated_resource_binding_rejects_tampered_trial() -> None:
    bound = _receipt("static2", "pair-1", 100, resource=True)

    assert validation_scheduler_experiment._resource_evidence_is_valid(bound) is True
    bound["wall_seconds"] = 101
    assert validation_scheduler_experiment._resource_evidence_is_valid(bound) is False


def test_contender_missing_static2_pair_fails_closed() -> None:
    receipts = [
        receipt
        for pair_id in ("pair-1", "pair-2", "pair-3")
        for receipt in (
            _receipt("serial", pair_id, 200, hosted=True, resource=True),
            _receipt("static2-balanced", pair_id, 40, hosted=True, resource=True),
        )
    ]

    result = validation_scheduler_experiment.compare_receipts(receipts)
    contender = next(
        item for item in result["candidates"] if item["candidate"] == "static2-balanced"
    )

    assert contender["incumbent_comparison_complete"] is False
    assert contender["incumbent_benefit_positive"] is False
    assert contender["admission_ready"] is False
    assert any("static2 comparison is missing" in item for item in contender["incumbent_blockers"])


def test_malformed_duplicate_receipt_blocks_admission() -> None:
    receipts = [
        receipt
        for pair_id in ("pair-1", "pair-2", "pair-3")
        for receipt in (
            _receipt("serial", pair_id, 200, hosted=True, resource=True),
            _receipt("static2", pair_id, 100, hosted=True, resource=True),
            _receipt("static2-balanced", pair_id, 40, hosted=True, resource=True),
        )
    ]
    receipts.append({"pair_id": "pair-1", "method": {"name": "serial"}})

    result = validation_scheduler_experiment.compare_receipts(receipts)

    assert any("duplicate serial" in blocker for blocker in result["blockers"])
    assert result["any_admission_ready"] is False


def test_resource_binding_requires_exact_method_and_receipt_path(tmp_path: Path) -> None:
    receipt_path = tmp_path / "trial.json"
    trial = _receipt("static2", "pair-1", 40)
    trial["receipt_path"] = str(receipt_path)
    launch = {
        "schema": "abyss_machine_resource_launch_v1",
        "request": {
            "command": [
                "python",
                "scripts/pytest_scheduler_experiment.py",
                "--method",
                "static2",
                "--receipt",
                str(receipt_path),
            ],
            "memory_demand_mib": 7600,
            "force": False,
        },
        "plan": {"decision": "allow"},
        "execution": {
            "returncode": 0,
            "systemd": {
                "service_runtime": "40s",
                "cpu_time_consumed": "70s",
            },
        },
        "startup_admission": {
            "demand_observation": {
                "peaks": {
                    "ok": True,
                    "unit": "trial.service",
                    "memory_peak_mib": 5000.0,
                    "memory_swap_peak_mib": 0.0,
                    "footprint_peak_mib": 5000.0,
                }
            }
        },
    }

    bound = validation_scheduler_experiment.bind_resource_envelope(trial, launch)

    assert bound["resource_envelope"]["footprint_peak_mib"] == 5000.0
    assert bound["resource_envelope"]["forced"] is False
