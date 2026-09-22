#!/usr/bin/env python3
"""Plan and compare non-authoritative aoa-session-memory scheduler trials."""

from __future__ import annotations

import argparse
import copy
import json
import math
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
INCUMBENT_METHOD = "static2"
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
        "incumbent": INCUMBENT_METHOD,
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
            "incumbent_comparison": {
                "method": INCUMBENT_METHOD,
                "required_for": "methods_other_than_incumbent",
                "strictly_positive_median_benefit": True,
                "uses_existing_paired_run_count": True,
            },
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


def _safe_comparison_key(receipt: Any) -> tuple[str, str, str, str] | None:
    try:
        key = _comparison_key(receipt)
    except (AttributeError, KeyError, TypeError):
        return None
    if not all(isinstance(part, str) and part for part in key):
        return None
    return key


def _finite_nonnegative_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and value >= 0
    )


def _receipt_is_correct(receipt: Any) -> bool:
    if not isinstance(receipt, dict):
        return False
    execution = receipt.get("execution")
    repository = receipt.get("repository_identity")
    before = repository.get("before") if isinstance(repository, dict) else None
    wall_seconds = receipt.get("wall_seconds")
    return bool(
        receipt.get("ok") is True
        and isinstance(execution, dict)
        and execution.get("coverage_complete") is True
        and isinstance(repository, dict)
        and repository.get("stable") is True
        and isinstance(before, dict)
        and isinstance(before.get("identity_sha256"), str)
        and _finite_nonnegative_number(wall_seconds)
        and _safe_comparison_key(receipt) is not None
    )


def _pair_comparison(
    reference: dict[str, Any], contender: dict[str, Any], pair_id: str
) -> dict[str, Any]:
    reference_key = _safe_comparison_key(reference)
    contender_key = _safe_comparison_key(contender)
    comparable = reference_key is not None and reference_key == contender_key
    correctness = _receipt_is_correct(reference) and _receipt_is_correct(contender)
    reference_wall = reference.get("wall_seconds")
    contender_wall = contender.get("wall_seconds")
    valid_wall = all(_finite_nonnegative_number(value) for value in (reference_wall, contender_wall))
    if not valid_wall:
        correctness = False
    reduction_seconds = (
        float(reference_wall) - float(contender_wall) if valid_wall else None
    )
    reduction_percent = (
        reduction_seconds / float(reference_wall) * 100.0
        if reduction_seconds is not None and reference_wall
        else 0.0 if reduction_seconds is not None
        else None
    )
    material = bool(
        reduction_seconds is not None
        and (
            reduction_seconds >= MIN_SECONDS_REDUCTION
            or (reduction_percent is not None and reduction_percent >= MIN_PERCENT_REDUCTION)
        )
    )
    return {
        "pair_id": pair_id,
        "comparable": comparable,
        "correctness": correctness,
        "baseline_wall_seconds": reference_wall if valid_wall else None,
        "candidate_wall_seconds": contender_wall if valid_wall else None,
        "reduction_seconds": round(reduction_seconds, 6) if reduction_seconds is not None else None,
        "reduction_percent": round(reduction_percent, 3) if reduction_percent is not None else None,
        "material": material,
    }


def _hosted_pair(
    pair: dict[str, Any], methods: dict[str, dict[str, Any]], reference_method: str, contender: str
) -> bool:
    if not pair["comparable"] or not pair["correctness"]:
        return False
    reference = methods[pair["pair_id"]][reference_method]
    candidate = methods[pair["pair_id"]][contender]

    def hosted(receipt: dict[str, Any]) -> bool:
        environment = receipt.get("environment_identity")
        runtime = environment.get("runtime") if isinstance(environment, dict) else None
        return isinstance(runtime, dict) and runtime.get("github_actions") is True

    return hosted(reference) and hosted(candidate)


def _resource_pair(
    pair: dict[str, Any], methods: dict[str, dict[str, Any]], reference_method: str, contender: str
) -> bool:
    if not pair["comparable"] or not pair["correctness"]:
        return False
    return all(
        _resource_evidence_is_valid(methods[pair["pair_id"]][method])
        for method in (reference_method, contender)
    )


def _resource_evidence_is_valid(receipt: Any) -> bool:
    if not isinstance(receipt, dict):
        return False
    envelope = receipt.get("resource_envelope")
    binding = receipt.get("resource_binding")
    if not isinstance(envelope, dict) or not isinstance(binding, dict):
        return False
    if envelope.get("source_schema") != "abyss_machine_resource_launch_v1":
        return False
    if not isinstance(envelope.get("source_sha256"), str) or not envelope["source_sha256"]:
        return False
    if not isinstance(envelope.get("unit"), str) or not envelope["unit"]:
        return False
    if not isinstance(envelope.get("plan_decision"), str) or not envelope["plan_decision"]:
        return False
    if not _finite_nonnegative_number(envelope.get("footprint_peak_mib")):
        return False
    for key in ("memory_peak_mib", "memory_swap_peak_mib", "requested_demand_mib"):
        if key in envelope and not _finite_nonnegative_number(envelope[key]):
            return False
    if "forced" in envelope and not isinstance(envelope["forced"], bool):
        return False
    return all(
        isinstance(binding.get(key), str) and bool(binding[key])
        for key in ("trial_sha256", "launch_sha256")
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
        if not isinstance(receipt, dict):
            blockers.append("non-object scheduler receipt")
            continue
        pair_id = receipt.get("pair_id")
        method_payload = receipt.get("method")
        method = method_payload.get("name") if isinstance(method_payload, dict) else None
        if not isinstance(pair_id, str) or not pair_id:
            blockers.append(f"{method or 'unknown'} receipt has no pair_id")
            continue
        if not isinstance(method, str) or not method:
            blockers.append(f"receipt in pair {pair_id} has no method name")
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
        incumbent_paired: list[dict[str, Any]] = []
        for pair_id, methods in sorted(pairs.items()):
            baseline = methods.get(BASELINE_METHOD)
            contender = methods.get(candidate)
            if baseline is not None and contender is not None:
                comparison = _pair_comparison(baseline, contender, pair_id)
                comparison["reference_method"] = BASELINE_METHOD
                paired.append(comparison)
            if candidate != INCUMBENT_METHOD:
                incumbent = methods.get(INCUMBENT_METHOD)
                if incumbent is not None and contender is not None:
                    comparison = _pair_comparison(incumbent, contender, pair_id)
                    comparison["reference_method"] = INCUMBENT_METHOD
                    incumbent_paired.append(comparison)
        candidate_pair_ids = {
            pair_id for pair_id, methods in pairs.items() if candidate in methods
        }
        valid = [pair for pair in paired if pair["comparable"] and pair["correctness"]]
        valid_pair_ids = {pair["pair_id"] for pair in valid}
        serial_pair_ids = {pair["pair_id"] for pair in paired}
        serial_comparison_complete = (
            bool(candidate_pair_ids)
            and serial_pair_ids == candidate_pair_ids
            and valid_pair_ids == candidate_pair_ids
        )
        hosted = [pair for pair in valid if _hosted_pair(pair, pairs, BASELINE_METHOD, candidate)]
        hosted_pair_ids = {pair["pair_id"] for pair in hosted}
        material_count = sum(bool(pair["material"]) for pair in valid)
        hosted_material_count = sum(bool(pair["material"]) for pair in hosted)
        latency_rule_passed = (
            len(hosted) >= MIN_PAIRED_RUNS
            and hosted_material_count >= MIN_MATERIAL_PAIRS
        )
        resource_pair_count_all = sum(
            1 for pair in valid if _resource_pair(pair, pairs, BASELINE_METHOD, candidate)
        )
        resource_pair_count = sum(
            1 for pair in hosted if _resource_pair(pair, pairs, BASELINE_METHOD, candidate)
        )

        incumbent_required = candidate != INCUMBENT_METHOD
        incumbent_valid = [
            pair
            for pair in incumbent_paired
            if pair["pair_id"] in candidate_pair_ids
            and pair["comparable"]
            and pair["correctness"]
        ]
        incumbent_valid_pair_ids = {pair["pair_id"] for pair in incumbent_valid}
        incumbent_comparison_complete = (
            not incumbent_required
            or (
                serial_comparison_complete
                and incumbent_valid_pair_ids == candidate_pair_ids
                and {pair["pair_id"] for pair in incumbent_paired} == candidate_pair_ids
            )
        )
        incumbent_hosted = [
            pair
            for pair in incumbent_valid
            if pair["pair_id"] in hosted_pair_ids
            and _hosted_pair(pair, pairs, INCUMBENT_METHOD, candidate)
        ]
        incumbent_resource_pair_count_all = sum(
            1
            for pair in incumbent_valid
            if _resource_pair(pair, pairs, INCUMBENT_METHOD, candidate)
        )
        incumbent_resource_pair_count = sum(
            1
            for pair in incumbent_hosted
            if _resource_pair(pair, pairs, INCUMBENT_METHOD, candidate)
        )
        incumbent_all_median = (
            statistics.median(
                pair["baseline_wall_seconds"] for pair in incumbent_valid
            )
            if incumbent_valid
            else None
        )
        candidate_incumbent_all_median = (
            statistics.median(
                pair["candidate_wall_seconds"] for pair in incumbent_valid
            )
            if incumbent_valid
            else None
        )
        incumbent_median = (
            statistics.median(
                pair["baseline_wall_seconds"] for pair in incumbent_hosted
            )
            if incumbent_hosted
            else None
        )
        candidate_incumbent_median = (
            statistics.median(
                pair["candidate_wall_seconds"] for pair in incumbent_hosted
            )
            if incumbent_hosted
            else None
        )
        incumbent_benefit_seconds = (
            incumbent_median - candidate_incumbent_median
            if incumbent_median is not None and candidate_incumbent_median is not None
            else None
        )
        incumbent_benefit_positive = (
            None
            if not incumbent_required
            else (
                serial_comparison_complete
                and incumbent_comparison_complete
                and len(incumbent_hosted) >= MIN_PAIRED_RUNS
                and incumbent_benefit_seconds is not None
                and incumbent_benefit_seconds > 0
            )
        )
        candidate_comparison_complete = (
            serial_comparison_complete
            and (not incumbent_required or incumbent_comparison_complete)
        )
        candidate_blockers: list[str] = []
        if not candidate_comparison_complete:
            candidate_blockers.append(
                "candidate trials do not all have complete, valid reference counterparts"
            )
        incumbent_blockers: list[str] = []
        if incumbent_required and not incumbent_comparison_complete:
            incumbent_blockers.append(
                "static2 comparison is missing, incomparable, red, or has a different pair set"
            )
        if incumbent_required and len(incumbent_hosted) < MIN_PAIRED_RUNS:
            incumbent_blockers.append(
                f"static2 comparison has fewer than {MIN_PAIRED_RUNS} hosted pairs"
            )
        if incumbent_required and incumbent_resource_pair_count == 0:
            incumbent_blockers.append("static2 comparison has no paired resource evidence")
        if incumbent_required and not incumbent_benefit_positive:
            incumbent_blockers.append(
                "candidate has no strictly positive median benefit over static2"
            )
        incumbent_gate_passed = not incumbent_required or bool(incumbent_benefit_positive)
        resource_evidence = resource_pair_count > 0 and (
            not incumbent_required or incumbent_resource_pair_count > 0
        )
        source_identities = {
            pairs[pair_id][candidate]["repository_identity"]["before"]["identity_sha256"]
            for pair_id in valid_pair_ids
        }
        source_identities.update(
            pairs[pair_id][INCUMBENT_METHOD]["repository_identity"]["before"]["identity_sha256"]
            for pair_id in incumbent_valid_pair_ids
            if INCUMBENT_METHOD in pairs[pair_id]
        )
        one_source = len(source_identities) <= 1
        admission_ready = (
            latency_rule_passed
            and resource_evidence
            and one_source
            and candidate_comparison_complete
            and incumbent_gate_passed
            and not blockers
        )
        outcomes.append(
            {
                "candidate": candidate,
                "incumbent": INCUMBENT_METHOD,
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
                "resource_pair_count_all_pairs": resource_pair_count_all,
                "candidate_trial_count": len(candidate_pair_ids),
                "candidate_comparison_complete": candidate_comparison_complete,
                "candidate_blockers": candidate_blockers,
                "incumbent_comparison_required": incumbent_required,
                "incumbent_pairs": incumbent_paired,
                "incumbent_valid_pair_count": len(incumbent_valid),
                "incumbent_hosted_pair_count": len(incumbent_hosted),
                "incumbent_local_pair_count": len(incumbent_valid) - len(incumbent_hosted),
                "incumbent_resource_pair_count": incumbent_resource_pair_count,
                "incumbent_resource_pair_count_all_pairs": incumbent_resource_pair_count_all,
                "incumbent_comparison_complete": incumbent_comparison_complete,
                "incumbent_median_wall_seconds": (
                    round(incumbent_median, 6) if incumbent_median is not None else None
                ),
                "median_candidate_vs_incumbent_wall_seconds": (
                    round(candidate_incumbent_median, 6)
                    if candidate_incumbent_median is not None
                    else None
                ),
                "incumbent_all_pair_median_wall_seconds": (
                    round(incumbent_all_median, 6)
                    if incumbent_all_median is not None
                    else None
                ),
                "median_candidate_vs_incumbent_all_pair_wall_seconds": (
                    round(candidate_incumbent_all_median, 6)
                    if candidate_incumbent_all_median is not None
                    else None
                ),
                "incumbent_benefit_seconds": (
                    round(incumbent_benefit_seconds, 6)
                    if incumbent_benefit_seconds is not None
                    else None
                ),
                "incumbent_benefit_positive": incumbent_benefit_positive,
                "incumbent_blockers": incumbent_blockers,
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
        "incumbent": INCUMBENT_METHOD,
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
