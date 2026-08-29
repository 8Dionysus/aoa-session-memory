from __future__ import annotations

import importlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

pytest_scheduler_experiment = importlib.import_module("pytest_scheduler_experiment")
validation_scheduler_experiment = importlib.import_module(
    "validation_scheduler_experiment"
)


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
