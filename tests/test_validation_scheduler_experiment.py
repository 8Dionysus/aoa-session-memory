from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
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


def test_scheduler_plan_keeps_all_candidates_in_shadow() -> None:
    plan = validation_scheduler_experiment.candidate_plan()
    methods = {item["name"]: item for item in plan["methods"]}

    assert plan["baseline"] == "serial"
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
) -> dict[str, object]:
    return {
        "schema_version": "aoa_session_memory_pytest_scheduler_trial_v1",
        "method": {"name": method},
        "pair_id": pair_id,
        "wall_seconds": wall_seconds,
        "ok": ok,
        "repository_identity": {
            "before": {"identity_sha256": identity},
            "stable": True,
        },
        "environment_identity": {"identity_sha256": "environment"},
        "cache": {"observed_state_before": "disabled"},
        "corpus": {"set_sha256": "corpus"},
        "execution": {"coverage_complete": True},
    }


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
