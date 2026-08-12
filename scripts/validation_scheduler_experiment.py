#!/usr/bin/env python3
"""Plan and compare non-authoritative aoa-session-memory scheduler trials."""

from __future__ import annotations

import argparse
import copy
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

import pytest_scheduler_experiment
import validation_identity


SCHEMA = "aoa_session_memory_validation_scheduler_comparison_v1"
BASELINE_METHOD = "serial"
MIN_PAIRED_RUNS = 3
MIN_MATERIAL_PAIRS = 2
MIN_PERCENT_REDUCTION = 15.0
MIN_SECONDS_REDUCTION = 60.0


def candidate_plan() -> dict[str, Any]:
    methods = []
    for method in pytest_scheduler_experiment.METHODS.values():
        if method.workers == 1:
            memory_demand_mib = 3800
        elif method.workers == 2:
            memory_demand_mib = 7600
        else:
            memory_demand_mib = 15200
        methods.append(
            {
                "name": method.name,
                "workers": method.workers,
                "scheduler": method.scheduler,
                "assertion_mode": method.assertion_mode,
                "memory_demand_mib": memory_demand_mib,
                "hosted_shadow_preferred": method.workers >= 4,
            }
        )
    return {
        "schema_version": "aoa_session_memory_validation_scheduler_plan_v1",
        "owner_repo": "aoa-session-memory",
        "baseline": BASELINE_METHOD,
        "methods": methods,
        "admission_rule": {
            "paired_runs": MIN_PAIRED_RUNS,
            "material_pairs": MIN_MATERIAL_PAIRS,
            "minimum_percent_reduction": MIN_PERCENT_REDUCTION,
            "minimum_seconds_reduction": MIN_SECONDS_REDUCTION,
            "zero_false_green": True,
            "exact_corpus": True,
            "resource_evidence_required": True,
            "hosted_pairs_required": True,
        },
        "authority_boundary": (
            "experiment plan only; every launch remains subject to host resource admission"
        ),
    }


def _load_receipt(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load scheduler receipt {path}: {exc}") from exc
    if payload.get("schema_version") != "aoa_session_memory_pytest_scheduler_trial_v1":
        raise ValueError(f"unsupported scheduler receipt schema: {path}")
    return payload


def _comparison_key(receipt: dict[str, Any]) -> tuple[str, str, str, str]:
    before = receipt["repository_identity"]["before"]
    return (
        before["identity_sha256"],
        receipt["environment_identity"]["identity_sha256"],
        receipt["corpus"]["set_sha256"],
        receipt["cache"]["observed_state_before"],
    )


def bind_resource_envelope(
    trial: dict[str, Any], launch: dict[str, Any]
) -> dict[str, Any]:
    if launch.get("schema") != "abyss_machine_resource_launch_v1":
        raise ValueError("resource evidence is not an abyss-machine launch receipt")
    command = launch.get("request", {}).get("command")
    if not isinstance(command, list):
        raise ValueError("resource launch receipt has no exact command argv")
    expected_method = trial.get("method", {}).get("name")
    try:
        method_index = command.index("--method")
        receipt_index = command.index("--receipt")
    except ValueError as exc:
        raise ValueError("resource launch command is not a scheduler trial") from exc
    if command[method_index + 1] != expected_method:
        raise ValueError("resource launch method does not match scheduler receipt")
    expected_receipt = Path(str(trial.get("receipt_path"))).resolve()
    if Path(command[receipt_index + 1]).resolve() != expected_receipt:
        raise ValueError("resource launch command does not bind the scheduler receipt path")
    execution = launch.get("execution")
    if not isinstance(execution, dict) or not isinstance(execution.get("returncode"), int):
        raise ValueError("resource launch did not execute the scheduler trial")
    if bool(execution["returncode"] == 0) != bool(trial.get("ok")):
        raise ValueError("resource launch exit status disagrees with scheduler receipt")
    peaks = (
        launch.get("startup_admission", {})
        .get("demand_observation", {})
        .get("peaks")
    )
    if not isinstance(peaks, dict) or peaks.get("ok") is not True:
        raise ValueError("resource launch receipt has no measured cgroup peak")
    bound = copy.deepcopy(trial)
    bound["resource_envelope"] = {
        "source_schema": launch["schema"],
        "source_sha256": validation_identity.canonical_sha256(launch),
        "unit": peaks.get("unit"),
        "memory_peak_mib": peaks.get("memory_peak_mib"),
        "memory_swap_peak_mib": peaks.get("memory_swap_peak_mib"),
        "footprint_peak_mib": peaks.get("footprint_peak_mib"),
        "service_runtime": execution.get("systemd", {}).get("service_runtime"),
        "cpu_time_consumed": execution.get("systemd", {}).get("cpu_time_consumed"),
        "requested_demand_mib": launch.get("request", {}).get("memory_demand_mib"),
        "plan_decision": launch.get("plan", {}).get("decision"),
        "forced": launch.get("request", {}).get("force"),
    }
    bound["resource_binding"] = {
        "trial_sha256": validation_identity.canonical_sha256(trial),
        "launch_sha256": validation_identity.canonical_sha256(launch),
    }
    return bound


def compare_receipts(receipts: Sequence[dict[str, Any]]) -> dict[str, Any]:
    blockers: list[str] = []
    pairs: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for receipt in receipts:
        pair_id = receipt.get("pair_id")
        method = receipt.get("method", {}).get("name")
        if not pair_id:
            blockers.append(f"{method or 'unknown'} receipt has no pair_id")
            continue
        if method in pairs[str(pair_id)]:
            blockers.append(f"duplicate {method} receipt in pair {pair_id}")
            continue
        pairs[str(pair_id)][str(method)] = receipt

    candidates = sorted(
        {
            method
            for methods in pairs.values()
            for method in methods
            if method != BASELINE_METHOD
        }
    )
    outcomes: list[dict[str, Any]] = []
    for candidate in candidates:
        paired: list[dict[str, Any]] = []
        for pair_id, methods in sorted(pairs.items()):
            baseline = methods.get(BASELINE_METHOD)
            contender = methods.get(candidate)
            if baseline is None or contender is None:
                continue
            comparable = _comparison_key(baseline) == _comparison_key(contender)
            correctness = bool(
                baseline.get("ok")
                and contender.get("ok")
                and baseline["execution"].get("coverage_complete")
                and contender["execution"].get("coverage_complete")
                and baseline["repository_identity"].get("stable")
                and contender["repository_identity"].get("stable")
            )
            baseline_wall = float(baseline["wall_seconds"])
            candidate_wall = float(contender["wall_seconds"])
            seconds = baseline_wall - candidate_wall
            percent = (seconds / baseline_wall * 100.0) if baseline_wall else 0.0
            material = seconds >= MIN_SECONDS_REDUCTION or percent >= MIN_PERCENT_REDUCTION
            paired.append(
                {
                    "pair_id": pair_id,
                    "comparable": comparable,
                    "correctness": correctness,
                    "baseline_wall_seconds": baseline_wall,
                    "candidate_wall_seconds": candidate_wall,
                    "reduction_seconds": round(seconds, 6),
                    "reduction_percent": round(percent, 3),
                    "material": material,
                }
            )
        valid = [pair for pair in paired if pair["comparable"] and pair["correctness"]]
        valid_pair_ids = {pair["pair_id"] for pair in valid}
        hosted = [
            pair
            for pair in valid
            if pairs[pair["pair_id"]][candidate]
            .get("environment_identity", {})
            .get("runtime", {})
            .get("github_actions")
            is True
            and pairs[pair["pair_id"]][BASELINE_METHOD]
            .get("environment_identity", {})
            .get("runtime", {})
            .get("github_actions")
            is True
        ]
        material_count = sum(bool(pair["material"]) for pair in valid)
        hosted_material_count = sum(bool(pair["material"]) for pair in hosted)
        latency_rule_passed = (
            len(hosted) >= MIN_PAIRED_RUNS
            and hosted_material_count >= MIN_MATERIAL_PAIRS
        )
        resource_pair_count = sum(
            1
            for pair_id in valid_pair_ids
            if pairs[pair_id][candidate].get("resource_envelope")
            and pairs[pair_id][BASELINE_METHOD].get("resource_envelope")
        )
        resource_evidence = resource_pair_count > 0
        source_identities = {
            pairs[pair_id][candidate]["repository_identity"]["before"]["identity_sha256"]
            for pair_id in valid_pair_ids
        }
        one_source = len(source_identities) <= 1
        admission_ready = latency_rule_passed and resource_evidence and one_source
        outcomes.append(
            {
                "candidate": candidate,
                "pairs": paired,
                "valid_pair_count": len(valid),
                "material_pair_count": material_count,
                "hosted_material_pair_count": hosted_material_count,
                "median_baseline_wall_seconds": (
                    round(statistics.median(pair["baseline_wall_seconds"] for pair in valid), 6)
                    if valid
                    else None
                ),
                "median_candidate_wall_seconds": (
                    round(statistics.median(pair["candidate_wall_seconds"] for pair in valid), 6)
                    if valid
                    else None
                ),
                "latency_rule_passed": latency_rule_passed,
                "resource_evidence_complete": resource_evidence,
                "resource_pair_count": resource_pair_count,
                "hosted_pair_count": len(hosted),
                "source_identity_count": len(source_identities),
                "one_source_identity": one_source,
                "admission_ready": admission_ready,
                "decision": "eligible_for_owner_review" if admission_ready else "retain_in_shadow",
            }
        )
    if not candidates:
        blockers.append("no candidate is paired with the serial baseline")
    return {
        "schema_version": SCHEMA,
        "owner_repo": "aoa-session-memory",
        "baseline": BASELINE_METHOD,
        "receipt_count": len(receipts),
        "blockers": blockers,
        "candidates": outcomes,
        "any_admission_ready": any(item["admission_ready"] for item in outcomes),
        "authority_boundary": (
            "comparison evidence only; owner review, hosted proof, graph integration, "
            "serial rollback, PR CI, and postmerge proof remain required"
        ),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan")
    plan.add_argument("--json", action="store_true")
    compare = subparsers.add_parser("compare")
    compare.add_argument("receipts", nargs="+", type=Path)
    compare.add_argument("--output", type=Path)
    bind = subparsers.add_parser("bind-resource")
    bind.add_argument("--trial-receipt", required=True, type=Path)
    bind.add_argument("--launch-receipt", required=True, type=Path)
    bind.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "plan":
        payload = candidate_plan()
    elif args.command == "compare":
        try:
            payload = compare_receipts([_load_receipt(path) for path in args.receipts])
        except (KeyError, TypeError, ValueError) as exc:
            print(f"validation scheduler comparison: {exc}", file=sys.stderr)
            return 2
        if args.output is not None:
            _write_json(args.output, payload)
    else:
        try:
            payload = bind_resource_envelope(
                _load_receipt(args.trial_receipt),
                json.loads(args.launch_receipt.read_text(encoding="utf-8")),
            )
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"validation scheduler resource binding: {exc}", file=sys.stderr)
            return 2
        _write_json(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
