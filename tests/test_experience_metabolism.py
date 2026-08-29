from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "experience_metabolism.py"
SPEC = importlib.util.spec_from_file_location("experience_metabolism_test", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PROFILE_SCRIPT = REPO_ROOT / "scripts" / "profile_session_stages.py"
PROFILE_SPEC = importlib.util.spec_from_file_location("profile_session_stages_experience_test", PROFILE_SCRIPT)
assert PROFILE_SPEC and PROFILE_SPEC.loader
PROFILE_MODULE = importlib.util.module_from_spec(PROFILE_SPEC)
PROFILE_SPEC.loader.exec_module(PROFILE_MODULE)


DIGEST = "sha256:" + "a" * 64
SHAPE = "tests_validators:exec_command:" + "a" * 16


def ref(session_id: str, line: int, event: str) -> dict[str, str]:
    return {
        "session": f"session:{session_id}",
        "raw": f"raw:line:{line}",
        "segment": f"session:{session_id}#segment:000",
        "event": event,
    }


def attempt(
    session_id: str,
    line: int,
    *,
    stage: str = "tests_validators",
    result_status: str | None = "succeeded",
    repeat: bool = False,
    rerun_after_fix: bool = False,
    validation_rerun_after_repair: bool = False,
    digest: str = DIGEST,
    shape: str | None = None,
) -> dict[str, object]:
    return {
        "stage": stage,
        "basis": "structured_test_or_validator_call",
        "operation_shape": shape or f"{stage}:exec_command:{digest.removeprefix('sha256:')[:16]}",
        "operation_digest": digest,
        "tool": "exec_command",
        "result_status": result_status,
        "span_seconds": 2.0,
        "repeat_index": 2 if repeat else 1,
        "repeat": repeat,
        "after_failure": rerun_after_fix,
        "rerun_after_fix": rerun_after_fix,
        "validation_rerun_after_repair": validation_rerun_after_repair,
        "call_ref": ref(session_id, line, f"call-{line}"),
        "result_ref": ref(session_id, line + 1, f"result-{line}") if result_status else None,
    }


def session(
    session_id: str,
    attempts: list[dict[str, object]],
    *,
    review_status: str = "reviewed",
    freshness_status: str = "bounded_readable_snapshot",
    source_alignment: str = "count_aligned",
    episode_status: str = "closed",
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "session_ref": f"session:{session_id}",
        "archive_status": "indexed",
        "open_tail_excluded": False,
        "raw_block_statuses": {"sealed": 1},
        "review_status": review_status,
        "scope_status": "usable_closed_episode_slice",
        "freshness": {
            "status": freshness_status,
            "source_alignment": source_alignment,
            "currentness_scope": "bounded_source_snapshot",
            "global_currentness": None,
            "currentness_claimed": False,
            "basis": "fixture generated profile with aligned source coverage",
        },
        "review_binding": {
            "status": review_status,
            "review_ref": f"review:{session_id}" if review_status in MODULE.REVIEWED_STATUSES else None,
        },
        "source_refs": {
            "session_manifest": f"session:{session_id}#session.manifest.json",
            "session_index": f"session:{session_id}#session.index.json",
            "raw_capture": "present",
        },
        "source_identity": {
            "raw_sha256": hashlib.sha256(session_id.encode("utf-8")).hexdigest(),
            "raw_bytes": 200,
            "raw_line_count": 20,
        },
        "coverage": {
            "indexed_event_count": 20,
            "segment_event_count": 20,
            "raw_line_count": 20,
            "closed_episode_count": 1 if episode_status == "closed" else 0,
            "closed_episode_duration_seconds": 12.0 if episode_status == "closed" else None,
            "episode_status_counts": {episode_status: 1},
            "skipped_episode_counts": None,
        },
        "episodes": [
            {
                "episode_id": f"episode-{session_id}",
                "status": episode_status,
                "confidence": "high",
                "duration_seconds": 12.0,
                "boundary_refs": {
                    "start": ref(session_id, 1, "start"),
                    "end": ref(session_id, 20, "end"),
                },
                "stage_spans": {
                    "unknown": {
                        "status": "observed",
                        "span_seconds": 1.0,
                    }
                },
                "attempt_count": len(attempts) or None,
                "attempt_samples": attempts,
                "repeat_evidence_samples": [
                    item for item in attempts
                    if item.get("repeat") is True or item.get("rerun_after_fix") is True
                ],
                "repeat_amplification": {
                    "attempt_count": len(attempts),
                    "repeated_attempt_count": sum(item.get("repeat") is True for item in attempts),
                    "rerun_after_fix_count": sum(item.get("rerun_after_fix") is True for item in attempts),
                },
            }
        ],
    }


def profile(
    sessions: list[dict[str, object]],
    *,
    profiler_version: str = "structured_segment_index_correlated_call_result_v1",
) -> dict[str, object]:
    return {
        "schema_version": "stage_profile_v1",
        "profiler": {
            "version": profiler_version,
            "owner": "aoa-session-memory",
            "mode": "read_only_generated_index_profile",
            "source_surfaces": list(MODULE.PROFILE_SOURCE_SURFACES),
        },
        "sessions": sessions,
    }


def receipt(
    owner: str,
    label: str,
    *,
    integrity: str = "verified",
    kind: str | None = None,
    event_status: str | None = None,
    packet: dict[str, object] | None = None,
    canary_source_binding_refs: list[str] | None = None,
) -> dict[str, object]:
    inferred_kind = kind or (
        "review_verdict" if owner == "reviewer-office" else
        "eval_verdict" if owner == "aoa-evals" else
        "shadow_result" if owner == "abyss-stack" else
        "rollback" if "rollback" in label else
        "reject" if "reject" in label else
        "owner_acceptance"
    )
    candidate_id = (
        str(packet["candidate_id"])
        if packet is not None
        else "experience-candidate:" + "0" * 24
    )
    base_digest = (
        str(packet["lifecycle"]["base_digest"])
        if packet is not None
        else DIGEST
    )
    event_status = event_status or {
        "reject": "rejected",
        "supersede": "superseded",
        "rollback": "rolled_back",
    }.get(inferred_kind, "accepted")
    evidence: dict[str, object] = {}
    if inferred_kind == "review_verdict" and event_status == "accepted":
        evidence = {"independent_reviewer": True}
    elif inferred_kind == "eval_verdict" and event_status == "accepted" and packet is not None:
        groups = MODULE._normalize_comparison_groups(
            comparison_refs(label, packet),
            expected_candidate_id=str(packet["candidate_id"]),
            expected_source_binding_refs=list(packet["recurrence"]["source_binding_refs"]),
        )
        evidence = {
            "comparison_evidence": groups,
            "comparison_refs": MODULE._comparison_ref_map(groups),
        }
    elif inferred_kind == "shadow_result" and event_status == "accepted" and packet is not None:
        measurement = shadow_measurement(packet, label)
        evidence = {
            "measurement": measurement,
            "measurement_refs": {
                "baseline": [measurement["baseline"]["ref"]],
                "shadow": [measurement["shadow"]["ref"]],
                "net_benefit": [measurement["net_benefit"]["ref"]],
            },
        }
    elif inferred_kind == "owner_acceptance" and event_status == "accepted" and packet is not None:
        base = label.removesuffix("-accepted").removesuffix("-x")
        evidence = {
            "acceptance_refs": {
                "owner": [MODULE.safe_logical_ref(ref(base, 2, "owner"))],
                "live_canary": [MODULE.safe_logical_ref(ref(base, 3, "canary"))],
            },
            "canary_evidence": canary_evidence(packet, base, source_binding_refs=canary_source_binding_refs),
        }
    elif inferred_kind == "adoption" and event_status == "accepted":
        evidence = {"adoption_refs": [MODULE.safe_logical_ref(ref("adoption", 2, "adoption"))]}
    elif inferred_kind == "supersede":
        evidence = {"replacement_refs": [MODULE.safe_logical_ref(ref("replacement", 2, "replacement"))]}
    elif inferred_kind == "rollback":
        evidence = {"rollback_refs": [MODULE.safe_logical_ref(ref("rollback", 2, "rollback"))]}
    evidence_digest = MODULE._evidence_digest(evidence)
    object_ref = MODULE.safe_logical_ref({"event": f"receipt:{label}"})
    verification_ref = MODULE.safe_logical_ref({"event": f"verification:{label}"})
    assert object_ref and verification_ref
    digest = MODULE._receipt_unsigned_digest(
        owner_repo=owner,
        receipt_type=MODULE.EXPECTED_RECEIPT_TYPES[inferred_kind],
        candidate_id=candidate_id,
        base_digest=base_digest,
        object_ref=object_ref,
        verification_ref=verification_ref,
        event_kind=inferred_kind,
        event_status=event_status,
        evidence_digest=evidence_digest,
    )
    return {
        "owner_repo": owner,
        "receipt_type": MODULE.EXPECTED_RECEIPT_TYPES[inferred_kind],
        "candidate_id": candidate_id,
        "base_digest": base_digest,
        "object_ref": object_ref,
        "verification_ref": verification_ref,
        "event_kind": inferred_kind,
        "event_status": event_status,
        "evidence_digest": evidence_digest,
        "digest": digest,
        "integrity": integrity,
    }


def comparison_packet(
    kind: str,
    label: str,
    *,
    context_label: str | None = None,
    packet: dict[str, object] | None = None,
    subject_label: str | None = None,
    baseline_profile: dict[str, object] | None = None,
    shadow_profile: dict[str, object] | None = None,
) -> dict[str, object]:
    baseline_ref = ref(f"baseline-{label}", 2, "baseline")
    shadow_ref = ref(f"shadow-{label}", 3, "shadow")
    source_binding_refs = (
        list(packet["recurrence"]["source_binding_refs"])
        if packet is not None
        else [DIGEST]
    )
    if baseline_profile is not None and shadow_profile is not None:
        baseline_binding = MODULE.profile_metrics(baseline_profile)
        shadow_binding = MODULE.profile_metrics(shadow_profile)
        baseline_ref = baseline_binding["profile_ref"]
        shadow_ref = shadow_binding["profile_ref"]
        source_binding_refs = sorted(
            set(baseline_binding["source_binding_refs"]) |
            set(shadow_binding["source_binding_refs"])
        )
    return {
        "comparison_type": kind,
        "candidate_id": (
            str(packet["candidate_id"])
            if packet is not None
            else "experience-candidate:" + "0" * 24
        ),
        "source_binding_refs": source_binding_refs,
        "subject_ref": ref(f"subject-{subject_label or label}", 1, "subject"),
        "baseline_ref": baseline_ref,
        "shadow_ref": shadow_ref,
        "context_ref": ref(f"context-{context_label or label}", 4, "context"),
        "result_ref": ref(f"result-{label}", 5, "comparison"),
        "source_fingerprint": DIGEST,
        "evidence_digest": "sha256:" + MODULE.stable_digest(f"{label}:evidence"),
        "numeric_result": 1.0,
        "result_status": "passed",
    }


def comparison_refs(
    label: str,
    packet: dict[str, object] | None = None,
) -> dict[str, list[dict[str, object]]]:
    subject_label = f"{label}-subject"
    return {
        "paired": [comparison_packet("paired", f"{label}-paired", context_label=label, packet=packet, subject_label=subject_label)],
        "held_out": [comparison_packet("held_out", f"{label}-held-out", context_label=label, packet=packet, subject_label=subject_label)],
        "ablation": [comparison_packet("ablation", f"{label}-ablation", context_label=label, packet=packet, subject_label=subject_label)],
    }


def shadow_measurement(
    packet: dict[str, object],
    label: str,
    *,
    coverage_status: str = "complete",
) -> dict[str, object]:
    baseline_metric_ref = MODULE.safe_logical_ref(ref(f"baseline-metric-{label}", 2, "baseline"))
    shadow_metric_ref = MODULE.safe_logical_ref(ref(f"shadow-metric-{label}", 3, "shadow"))
    baseline_profile_ref = MODULE.safe_logical_ref(ref(f"baseline-profile-{label}", 4, "profile"))
    shadow_profile_ref = MODULE.safe_logical_ref(ref(f"shadow-profile-{label}", 5, "profile"))
    net_ref = MODULE.safe_logical_ref(ref(f"net-{label}", 6, "net-benefit"))
    assert baseline_metric_ref and shadow_metric_ref and baseline_profile_ref and shadow_profile_ref and net_ref
    sources = list(packet["recurrence"]["source_binding_refs"])
    baseline_sources = sources[:1] or sources
    shadow_sources = sources[1:] or sources
    unsigned: dict[str, object] = {
        "schema_version": "experience_shadow_measurement_binding_v1",
        "candidate_id": str(packet["candidate_id"]),
        "candidate_source_binding_refs": list(packet["recurrence"]["source_binding_refs"]),
        "comparison_source_binding_refs": sorted(
            set(packet["recurrence"]["source_binding_refs"])
        ),
        "comparison_mode": "paired",
        "baseline": {
            "ref": baseline_metric_ref,
            "profile_ref": baseline_profile_ref,
            "source_binding_refs": baseline_sources,
            "wall_clock_seconds": 20.0 if coverage_status == "complete" else None,
            "residual_unknown_seconds": 1.0 if coverage_status == "complete" else None,
            "coverage_status": coverage_status,
        },
        "shadow": {
            "ref": shadow_metric_ref,
            "profile_ref": shadow_profile_ref,
            "source_binding_refs": shadow_sources,
            "wall_clock_seconds": 12.0 if coverage_status == "complete" else None,
            "residual_unknown_seconds": 0.5 if coverage_status == "complete" else None,
            "coverage_status": coverage_status,
        },
        "net_benefit": {
            "ref": net_ref,
            "status": "descriptive_directional_delta",
            "claim": "not_established",
            "evidence_digest": DIGEST,
        },
        "trajectory_cost": {
            "baseline_ref": baseline_metric_ref,
            "shadow_ref": shadow_metric_ref,
            "activity_counts_are_not_benefit": True,
        },
        "admission": {
            "comparable": True,
            "accepted_eval": False,
            "owner_acceptance": False,
            "live_canary": False,
        },
    }
    return {
        "measurement_digest": "sha256:" + MODULE.stable_digest(unsigned),
        **unsigned,
    }


def canary_evidence(
    packet: dict[str, object],
    label: str,
    *,
    source_binding_refs: list[str] | None = None,
) -> dict[str, object]:
    measurement = packet["evaluation_requirements"]["shadow_measurement"]
    def logical(line: int, event: str) -> dict[str, str]:
        value = MODULE.safe_logical_ref(ref(label, line, event))
        assert value is not None
        return value
    return {
        "schema_version": "experience_live_canary_binding_v1",
        "candidate_id": str(packet["candidate_id"]),
        "base_digest": str(packet["lifecycle"]["base_digest"]),
        "runtime_ref": logical(1, "runtime"),
        "execution_ref": logical(2, "execution"),
        "treatment_ref": logical(3, "treatment"),
        "baseline_ref": measurement["baseline"]["ref"],
        "shadow_ref": measurement["shadow"]["ref"],
        "result_ref": logical(4, "canary-result"),
        "rollback_ref": logical(5, "rollback"),
        "verification_ref": logical(6, "canary-verification"),
        "source_binding_refs": list(source_binding_refs or packet["recurrence"]["source_binding_refs"]),
        "shadow_measurement_digest": measurement["measurement_digest"],
        "status": "completed",
        "coverage_status": "complete",
    }


def test_reviewed_closed_aligned_gate_excludes_provisional_open_and_stale() -> None:
    report = MODULE.build_report(
        [
            profile([session("good", [attempt("good", 2)])]),
            profile([session("provisional", [attempt("provisional", 2)], review_status="provisional")]),
            profile([session("open", [attempt("open", 2)], episode_status="open")]),
            profile([session("stale", [attempt("stale", 2)], freshness_status="stale-readable")]),
        ],
        minimum_occurrences=1,
    )
    assert report["corpus"]["eligible_reviewed_session_count"] == 1
    reasons = [reason for row in report["session_gates"] for reason in row["reasons"]]
    assert "session_not_reviewed" in reasons
    assert "profile_freshness_not_current" in reasons
    assert report["candidates"]
    assert all(item["recurrence"]["status"] != "review_ready" for item in report["candidates"])
    assert all(item["status"] == "insufficient_evidence" for item in report["candidates"])


def test_review_admission_requires_nonempty_bound_review_reference_and_scope() -> None:
    missing_ref = session("missing-review-ref", [attempt("missing-review-ref", 2)])
    missing_ref["review_binding"]["review_ref"] = ""
    missing_scope = session("missing-currentness-scope", [attempt("missing-currentness-scope", 2)])
    del missing_scope["freshness"]["currentness_scope"]
    report = MODULE.build_report([profile([missing_ref, missing_scope])], minimum_occurrences=1)
    assert report["corpus"]["eligible_reviewed_session_count"] == 0
    reasons = [reason for row in report["session_gates"] for reason in row["reasons"]]
    assert "review_receipt_ref_missing" in reasons
    assert "freshness_scope_invalid" in reasons


def test_same_session_repetition_is_watch_not_cross_session_recurrence() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2, repeat=False), attempt("one", 4, repeat=True)])])],
        minimum_occurrences=2,
    )
    repeated = next(item for item in report["candidates"] if item["motif"]["signal"] == "repeated_operation")
    assert repeated["recurrence"]["distinct_session_count"] == 1
    assert repeated["recurrence"]["status"] == "watch"
    assert repeated["status"] == "insufficient_evidence"
    assert repeated["next_route"] == "aoa-session-memory:manual-review"


def test_cross_session_candidate_keeps_provenance_and_never_claims_causality() -> None:
    reports = [
        profile([session("one", [attempt("one", 2)])]),
        profile([session("two", [attempt("two", 2)])]),
    ]
    report = MODULE.build_report(reports, minimum_occurrences=2)
    candidate = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    assert candidate["status"] == "candidate"
    assert candidate["recurrence"]["status"] == "review_ready"
    assert candidate["evidence_diversity"]["distinct_session_count"] == 2
    assert candidate["causal_attribution"]["status"] == "not_established"
    assert candidate["evaluation_requirements"]["verdict"] is None
    assert candidate["lifecycle"]["adoption_allowed"] is False


@pytest.mark.parametrize("statuses, expected", [
    ([None, None], "unknown"),
    (["succeeded", "failed"], "conflicting"),
])
def test_unknown_or_conflicting_outcomes_block_candidate(statuses: list[str | None], expected: str) -> None:
    reports = [
        profile([session("one", [attempt("one", 2, result_status=statuses[0])])]),
        profile([session("two", [attempt("two", 2, result_status=statuses[1])])]),
    ]
    report = MODULE.build_report(reports, minimum_occurrences=2)
    candidate = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    assert candidate["counterevidence"]["status"] == expected
    assert candidate["status"] == "insufficient_evidence"
    assert candidate["recurrence"]["status"] == "insufficient_evidence"


def test_privacy_packet_does_not_copy_raw_command_or_host_path() -> None:
    reports = [
        profile([session("one", [attempt("one", 2)])]),
        profile([session("two", [attempt("two", 2)])]),
    ]
    report = MODULE.build_report(reports, minimum_occurrences=2)
    encoded = json.dumps(report, ensure_ascii=False)
    assert "pytest -q tests" not in encoded
    private_home = "/home/" + "private-user"
    assert private_home not in encoded
    assert report["privacy"]["raw_transcript_scanned"] is False
    assert report["privacy"]["raw_transcript_emitted"] is False
    assert all("session:one" not in json.dumps(candidate) for candidate in report["candidates"])


def test_shadow_measurement_reports_baseline_net_benefit_vector_and_trajectory_cost() -> None:
    baseline = profile([session("one", [attempt("one", 2), attempt("one", 4)])])
    shadow = profile([session("two", [attempt("two", 2)])])
    measurement = MODULE.build_shadow_measurement(
        baseline,
        shadow,
        comparison_mode="paired",
        comparison_refs=[
            comparison_packet(
                "paired",
                "pair",
                baseline_profile=baseline,
                shadow_profile=shadow,
            )
        ],
    )
    assert measurement["mode"] == "shadow_only"
    assert measurement["net_benefit"]["status"] == "descriptive_directional_delta"
    assert measurement["net_benefit"]["claim"] == "not_established"
    assert measurement["net_benefit"]["scalar"] is None
    assert measurement["trajectory_cost"]["baseline"]["wall_clock_seconds"] == 12.0
    assert measurement["trajectory_cost"]["activity_counts_are_not_benefit"] is True
    assert all(measurement["comparison_refs"])
    schema = json.loads((REPO_ROOT / "schemas" / "experience-metabolism-report.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(measurement)


def test_shadow_builder_requires_complete_profiles_and_profile_bound_comparison() -> None:
    baseline = profile([session("baseline", [attempt("baseline", 2)])])
    shadow = profile([session("shadow", [attempt("shadow", 2)])])
    bad_binding = comparison_packet(
        "paired",
        "bad-binding",
        baseline_profile=baseline,
        shadow_profile=shadow,
    )
    bad_binding["shadow_ref"] = ref("wrong-shadow", 3, "profile")
    with pytest.raises(MODULE.MetabolismError, match="comparison_profile_binding_mismatch"):
        MODULE.build_shadow_measurement(
            baseline,
            shadow,
            comparison_mode="paired",
            comparison_refs=[bad_binding],
        )

    partial = profile([session("partial", [attempt("partial", 2)], episode_status="open")])
    with pytest.raises(MODULE.MetabolismError, match="shadow_profile_coverage_incomplete"):
        MODULE.build_shadow_measurement(partial, shadow)


def test_false_recurrence_flags_and_shape_mismatch_cannot_activate_repeat_motif() -> None:
    inconsistent = attempt("one", 2, repeat=True)
    inconsistent["repeat_index"] = 1
    mismatched_shape = attempt("two", 2)
    mismatched_shape["operation_shape"] = "tests_validators:exec_command:" + "b" * 16
    report = MODULE.build_report(
        [profile([session("one", [inconsistent])]), profile([session("two", [mismatched_shape])])],
        minimum_occurrences=1,
    )
    assert not [item for item in report["candidates"] if item["motif"]["signal"] == "repeated_operation"]
    observed = [item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed"]
    assert observed
    assert all(row["result_status"] == "unknown" for row in observed[0]["evidence_diversity"]["occurrence_rows"])


def test_recurrence_context_requires_real_predecessors_and_a_repair_boundary() -> None:
    forged_single = attempt("single", 2, repeat=True)
    failed_then_forged_rerun = [
        attempt("no-repair", 2, result_status="failed"),
        attempt("no-repair", 4, repeat=True, rerun_after_fix=True),
    ]
    report = MODULE.build_report(
        [
            profile([session("single", [forged_single])]),
            profile([session("no-repair", failed_then_forged_rerun)]),
        ],
        minimum_occurrences=1,
    )
    signals = {item["motif"]["signal"] for item in report["candidates"]}
    assert "repeated_operation" not in signals
    assert "rerun_after_fix" not in signals
    assert "operation_observed" in signals


def test_consumer_rejects_repair_before_failure_and_repair_before_validator() -> None:
    repair_before_failure = [
        attempt("ordered", 2, stage="diagnosis_repair"),
        attempt("ordered", 4, result_status="failed"),
        attempt("ordered", 6, repeat=True, rerun_after_fix=True),
    ]
    contexts = MODULE._recomputed_attempt_context(repair_before_failure)
    assert contexts is not None
    assert contexts[-1]["repeat"] is True
    assert contexts[-1]["rerun_after_fix"] is False

    repair_before_validator = [
        attempt("validator-order", 2, stage="diagnosis_repair"),
        attempt("validator-order", 4, validation_rerun_after_repair=True),
    ]
    contexts = MODULE._recomputed_attempt_context(repair_before_validator)
    assert contexts is not None
    assert contexts[-1]["validation_rerun_after_repair"] is False

    validator_then_repair = [
        attempt("validator-order-ok", 2),
        attempt("validator-order-ok", 4, stage="diagnosis_repair"),
        attempt("validator-order-ok", 6, repeat=True, validation_rerun_after_repair=True),
    ]
    contexts = MODULE._recomputed_attempt_context(validator_then_repair)
    assert contexts is not None
    assert contexts[-1]["validation_rerun_after_repair"] is True


def test_producer_emits_only_ordered_repair_and_validation_context() -> None:
    def make_attempts(specs: list[tuple[str, str]]) -> list[dict[str, object]]:
        events: dict[int, dict[str, object]] = {}
        for index, (stage, outcome) in enumerate(specs):
            call_line = index * 2 + 1
            correlation_id = f"ordered-{index}"
            if stage == "diagnosis_repair":
                event_type = "FILE_WRITE"
                facets = {"command": "apply_patch", "tool_name": "apply_patch", "command_kind": "write"}
            else:
                event_type = "COMMAND"
                facets = {"command": "pytest -q tests", "tool_name": "exec_command", "command_kind": "verification"}
            events[call_line] = {
                "event_id": f"call-{index}",
                "line": call_line,
                "type": event_type,
                "timestamp": f"2026-08-20T10:00:{index * 2:02d}Z",
                "correlation_id": correlation_id,
                "facets": facets,
            }
            events[call_line + 1] = {
                "event_id": f"result-{index}",
                "line": call_line + 1,
                "type": "ERROR" if outcome == "failed" else "TOOL_OUTPUT",
                "timestamp": f"2026-08-20T10:00:{index * 2 + 1:02d}Z",
                "correlation_id": correlation_id,
                "outcome": outcome,
                "facets": {},
            }
        episode = PROFILE_MODULE.profile_episode(
            session_label="ordered-producer",
            episode={"event_range": {"from_line": 1, "to_line": len(events)}},
            events_by_line=events,
        )
        return episode["attempt_samples"]

    repair_first = make_attempts([
        ("diagnosis_repair", "observed"),
        ("tests_validators", "failed"),
        ("tests_validators", "succeeded"),
    ])
    assert repair_first[-1]["rerun_after_fix"] is False

    validator_first = make_attempts([
        ("tests_validators", "succeeded"),
        ("diagnosis_repair", "observed"),
        ("tests_validators", "succeeded"),
    ])
    assert validator_first[-1]["validation_rerun_after_repair"] is True

    repair_without_prior_validator = make_attempts([
        ("diagnosis_repair", "observed"),
        ("tests_validators", "succeeded"),
    ])
    assert repair_without_prior_validator[-1]["validation_rerun_after_repair"] is False


def test_duplicate_result_or_flag_identity_is_not_collapsed() -> None:
    first = profile([session("same-source", [attempt("same-source", 2)])])
    second = json.loads(json.dumps(first))
    second["sessions"][0]["episodes"][0]["attempt_samples"][0]["result_ref"] = ref(
        "same-source", 6, "different-result"
    )
    second["sessions"][0]["episodes"][0]["repeat_evidence_samples"] = []
    report = MODULE.build_report([first, second], minimum_occurrences=1)
    observed = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    assert report["corpus"]["duplicate_occurrence_count"] == 0
    assert observed["recurrence"]["occurrence_count"] == 2
    assert observed["counterevidence"]["status"] == "no_negative_observation"


def test_unknown_stage_is_retained_only_as_unknown_evidence() -> None:
    unknown = attempt("one", 2)
    unknown["stage"] = "unknown"
    unknown["operation_shape"] = "unknown:exec_command:" + "a" * 16
    report = MODULE.build_report([profile([session("one", [unknown])]), profile([session("two", [unknown])])], minimum_occurrences=2)
    assert report["candidates"]
    assert all(item["status"] == "insufficient_evidence" for item in report["candidates"])
    assert all(item["counterevidence"]["status"] == "unknown" for item in report["candidates"])


def test_unsupported_stage_is_normalized_to_unknown_and_cannot_activate_recurrence() -> None:
    unsupported_one = attempt("one", 2)
    unsupported_one["stage"] = "unlisted_stage"
    unsupported_one["operation_shape"] = "unlisted_stage:exec_command:" + "a" * 16
    unsupported_two = attempt("two", 2)
    unsupported_two["stage"] = "unlisted_stage"
    unsupported_two["operation_shape"] = "unlisted_stage:exec_command:" + "a" * 16
    report = MODULE.build_report(
        [profile([session("one", [unsupported_one])]), profile([session("two", [unsupported_two])])],
        minimum_occurrences=2,
    )
    assert report["candidates"]
    assert all(item["motif"]["stage"] == "unknown" for item in report["candidates"])
    assert all(item["status"] == "insufficient_evidence" for item in report["candidates"])
    assert all(item["recurrence"]["status"] != "review_ready" for item in report["candidates"])


def test_nonclosed_episode_with_unknown_omission_status_is_not_admitted() -> None:
    ambiguous = session("ambiguous-open", [attempt("ambiguous-open", 2)], episode_status="open")
    ambiguous["coverage"]["skipped_episode_counts"] = None
    report = MODULE.build_report([profile([ambiguous])], minimum_occurrences=1)
    assert report["corpus"]["eligible_reviewed_session_count"] == 0
    assert "episode_coverage_omitted" in report["session_gates"][0]["reasons"]


def test_declared_episode_status_counts_must_reconcile_with_observed_and_omitted_rows() -> None:
    hidden = session("hidden-open", [attempt("hidden-open", 2)])
    hidden["coverage"]["episode_status_counts"] = {"closed": 1, "open": 1}
    hidden["coverage"]["skipped_episode_counts"] = None
    report = MODULE.build_report([profile([hidden])], minimum_occurrences=1)
    assert report["corpus"]["eligible_reviewed_session_count"] == 0
    assert "episode_status_coverage_mismatch" in report["session_gates"][0]["reasons"]


def test_negative_review_eval_and_shadow_verdicts_close_the_rejection_route() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    candidate = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    review_rejected = MODULE.apply_lifecycle_event(
        candidate,
        {
            "kind": "review_verdict",
            "status": "rejected",
            "receipt": receipt("reviewer-office", "review-rejected", event_status="rejected", packet=candidate),
        },
    )
    assert review_rejected["routes"]["rejection"]["status"] == "rejected"

    reviewed = MODULE.apply_lifecycle_event(
        candidate,
        {
            "kind": "review_verdict",
            "status": "accepted",
            "independent_reviewer": True,
            "receipt": receipt("reviewer-office", "review-accepted-for-negative", packet=candidate),
        },
    )
    eval_rejected = MODULE.apply_lifecycle_event(
        reviewed,
        {
            "kind": "eval_verdict",
            "status": "rejected",
            "receipt": receipt("aoa-evals", "eval-rejected", event_status="rejected", packet=reviewed),
        },
    )
    assert eval_rejected["routes"]["rejection"]["status"] == "rejected"

    evaluated = MODULE.apply_lifecycle_event(
        reviewed,
        {
            "kind": "eval_verdict",
            "status": "accepted",
            "comparisons": {"paired": "passed", "held_out": "passed", "ablation": "passed"},
            "comparison_refs": comparison_refs("negative-shadow-eval", reviewed),
            "receipt": receipt("aoa-evals", "negative-shadow-eval", packet=reviewed),
        },
    )
    shadow_rejected = MODULE.apply_lifecycle_event(
        evaluated,
        {
            "kind": "shadow_result",
            "status": "rejected",
            "receipt": receipt("abyss-stack", "shadow-rejected", event_status="rejected", packet=evaluated),
        },
    )
    assert shadow_rejected["routes"]["rejection"]["status"] == "rejected"


def test_duplicate_profile_reports_are_deduplicated_before_recurrence() -> None:
    first = profile([session("only", [attempt("only", 2, repeat=False)])])
    first["sessions"][0]["episodes"][0]["repeat_evidence_samples"] = []
    duplicate = json.loads(json.dumps(first))
    report = MODULE.build_report([first, duplicate], minimum_occurrences=2)
    observed = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    assert report["corpus"]["duplicate_occurrence_count"] == 1
    assert report["corpus"]["deduplicated_occurrence_count"] == len(report["candidates"])
    assert observed["recurrence"]["occurrence_count"] == 1
    assert observed["recurrence"]["distinct_session_count"] == 1
    assert observed["recurrence"]["status"] == "watch"
    assert observed["status"] == "insufficient_evidence"


def test_duplicate_profile_with_conflicting_result_is_counterevidence_not_deduped() -> None:
    first = profile([session("conflict", [attempt("conflict", 2, repeat=False)])])
    first["sessions"][0]["episodes"][0]["repeat_evidence_samples"] = []
    conflicting = json.loads(json.dumps(first))
    conflicting["sessions"][0]["episodes"][0]["attempt_samples"][0]["result_status"] = "failed"
    report = MODULE.build_report([first, conflicting], minimum_occurrences=1)
    observed = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    assert report["corpus"]["duplicate_occurrence_count"] == 0
    assert observed["recurrence"]["occurrence_count"] == 2
    assert observed["counterevidence"]["status"] == "conflicting"
    assert observed["status"] == "insufficient_evidence"


def test_foreign_or_renamed_event_reference_cannot_enter_admitted_episode() -> None:
    foreign = session("stable", [attempt("stable", 2)])
    foreign["episodes"][0]["attempt_samples"][0]["call_ref"]["session"] = "session:renamed-label"
    report = MODULE.build_report([profile([foreign])], minimum_occurrences=1)
    assert report["corpus"]["eligible_reviewed_session_count"] == 0
    assert not report["candidates"]
    assert "call_ref_not_bound_to_episode" in report["session_gates"][0]["reasons"]


def test_consumer_rejects_inverted_and_out_of_source_order_references() -> None:
    inverted = attempt("inverted", 4)
    inverted["result_ref"] = ref("inverted", 3, "result-4")
    inverted_report = MODULE.build_report([profile([session("inverted", [inverted])])], minimum_occurrences=1)
    assert inverted_report["corpus"]["eligible_reviewed_session_count"] == 0
    assert "call_result_order_invalid" in inverted_report["session_gates"][0]["reasons"]

    out_of_bounds = session("out-of-bounds", [attempt("out-of-bounds", 2)])
    out_of_bounds["source_identity"]["raw_line_count"] = 10
    out_of_bounds["coverage"]["raw_line_count"] = 10
    out_of_bounds["coverage"]["indexed_event_count"] = 10
    out_of_bounds["coverage"]["segment_event_count"] = 10
    out_report = MODULE.build_report([profile([out_of_bounds])], minimum_occurrences=1)
    assert out_report["corpus"]["eligible_reviewed_session_count"] == 0
    assert "episode_boundary_ref_not_bound" in out_report["session_gates"][0]["reasons"]


def test_consumer_rejects_inverted_episode_boundaries() -> None:
    inverted = session("inverted-boundary", [attempt("inverted-boundary", 2)])
    inverted["episodes"][0]["boundary_refs"]["start"], inverted["episodes"][0]["boundary_refs"]["end"] = (
        inverted["episodes"][0]["boundary_refs"]["end"],
        inverted["episodes"][0]["boundary_refs"]["start"],
    )
    report = MODULE.build_report([profile([inverted])], minimum_occurrences=1)
    assert report["corpus"]["eligible_reviewed_session_count"] == 0
    assert "episode_boundary_ref_not_bound" in report["session_gates"][0]["reasons"]


def test_profile_omission_markers_are_counterevidence_not_eligible_input() -> None:
    incomplete = session("incomplete", [attempt("incomplete", 2)])
    incomplete["coverage"]["skipped_episode_counts"] = {"open": 1}
    incomplete["open_tail_excluded"] = True
    incomplete["raw_block_statuses"] = {"open": 1}
    report = MODULE.build_report([profile([incomplete])], minimum_occurrences=1)
    assert report["corpus"]["eligible_reviewed_session_count"] == 0
    row = report["session_gates"][0]
    assert row["eligible"] is False
    assert "episode_coverage_omitted" in row["reasons"]
    assert "open_tail_coverage_not_excluded" in row["reasons"]
    assert "raw_block_coverage_not_sealed" in row["reasons"]


def test_lifecycle_state_is_derived_from_receipted_chain_and_refs_are_retained() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    forged = json.loads(json.dumps(packet))
    forged["lifecycle"]["state"] = "owner_review_pending"
    with pytest.raises(MODULE.MetabolismError, match="lifecycle_state_not_derived_from_history"):
        MODULE.apply_lifecycle_event(forged, {"kind": "reject", "status": "rejected", "receipt": receipt("aoa-session-memory", "reject")})
    reviewed = MODULE.apply_lifecycle_event(
        packet,
        {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": receipt("reviewer-office", "review", packet=packet)},
    )
    evaluated = MODULE.apply_lifecycle_event(
        reviewed,
        {
            "kind": "eval_verdict",
            "status": "accepted",
            "comparisons": {"paired": "passed", "held_out": "passed", "ablation": "passed"},
            "comparison_refs": comparison_refs("eval", reviewed),
            "receipt": receipt("aoa-evals", "eval", packet=reviewed),
        },
    )
    assert evaluated["evaluation_requirements"]["eval_comparison_refs"]["paired"]
    assert evaluated["lifecycle"]["history"][-1]["evidence_refs"]


def test_lifecycle_requires_review_eval_comparisons_shadow_and_owner_canary() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    with pytest.raises(MODULE.MetabolismError, match="eval_event_requires_review"):
        MODULE.apply_lifecycle_event(packet, {"kind": "eval_verdict", "status": "accepted", "receipt": receipt("aoa-evals", "eval-before-review", packet=packet)})
    packet = MODULE.apply_lifecycle_event(
        packet,
        {
            "kind": "review_verdict",
            "status": "accepted",
            "independent_reviewer": True,
            "receipt": receipt("reviewer-office", "review-accepted", packet=packet),
        },
    )
    with pytest.raises(MODULE.MetabolismError, match="paired_held_out_ablation_required"):
        MODULE.apply_lifecycle_event(packet, {"kind": "eval_verdict", "status": "accepted", "receipt": receipt("aoa-evals", "eval-missing", packet=packet)})
    packet = MODULE.apply_lifecycle_event(
        packet,
        {
            "kind": "eval_verdict",
            "status": "accepted",
            "comparisons": {"paired": "passed", "held_out": "passed", "ablation": "passed"},
            "comparison_refs": comparison_refs("eval-accepted", packet),
            "receipt": receipt("aoa-evals", "eval-accepted", packet=packet),
        },
    )
    with pytest.raises(MODULE.MetabolismError, match="shadow_measurement"):
        MODULE.apply_lifecycle_event(packet, {"kind": "shadow_result", "status": "accepted", "receipt": receipt("abyss-stack", "shadow-missing", packet=packet)})
    packet = MODULE.apply_lifecycle_event(
        packet,
        {
            "kind": "shadow_result",
            "status": "accepted",
            "shadow_measurement": shadow_measurement(packet, "shadow-accepted"),
            "receipt": receipt("abyss-stack", "shadow-accepted", packet=packet),
        },
    )
    with pytest.raises(MODULE.MetabolismError, match="owner_and_live_canary"):
        MODULE.apply_lifecycle_event(packet, {"kind": "owner_acceptance", "status": "accepted", "receipt": receipt("aoa-session-memory", "owner-missing", packet=packet)})
    packet = MODULE.apply_lifecycle_event(
        packet,
        {
            "kind": "owner_acceptance",
            "status": "accepted",
            "owner_ref": ref("owner", 2, "owner"),
            "live_canary_ref": ref("owner", 3, "canary"),
            "canary_evidence": canary_evidence(packet, "owner"),
            "receipt": receipt("aoa-session-memory", "owner-accepted", packet=packet),
        },
    )
    assert packet["lifecycle"]["state"] == "accepted"
    assert packet["lifecycle"]["adoption_allowed"] is False
    assert packet["routes"]["adoption"]["status"] == "pending_explicit_adoption"
    schema = json.loads((REPO_ROOT / "schemas" / "experience-metabolism-report.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(packet)
    packet = MODULE.apply_lifecycle_event(
        packet,
        {
            "kind": "adoption",
            "status": "accepted",
            "adoption_ref": ref("adoption", 2, "adoption"),
            "receipt": receipt("aoa-session-memory", "adoption-accepted", kind="adoption", packet=packet),
        },
    )
    assert packet["lifecycle"]["state"] == "adopted"
    assert packet["lifecycle"]["adoption_allowed"] is True
    assert packet["routes"]["adoption"]["status"] == "adopted"
    Draft202012Validator(schema).validate(packet)


def test_compaction_or_interruption_can_resume_only_from_receipted_state_and_rollback_is_explicit() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    with pytest.raises(MODULE.MetabolismError, match="lifecycle_receipt_required"):
        MODULE.apply_lifecycle_event(packet, {"kind": "reject", "status": "rejected"})
    reviewed = MODULE.apply_lifecycle_event(
        packet,
        {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": receipt("reviewer-office", "review-x", packet=packet)},
    )
    evaluated = MODULE.apply_lifecycle_event(
        reviewed,
        {"kind": "eval_verdict", "status": "accepted", "comparisons": {"paired": "passed", "held_out": "passed", "ablation": "passed"}, "comparison_refs": comparison_refs("eval-x", reviewed), "receipt": receipt("aoa-evals", "eval-x", packet=reviewed)},
    )
    shadowed = MODULE.apply_lifecycle_event(
        evaluated,
        {"kind": "shadow_result", "status": "accepted", "shadow_measurement": shadow_measurement(evaluated, "shadow-x"), "receipt": receipt("abyss-stack", "shadow-x", packet=evaluated)},
    )
    accepted = MODULE.apply_lifecycle_event(
        shadowed,
        {"kind": "owner_acceptance", "status": "accepted", "owner_ref": ref("owner", 2, "owner"), "live_canary_ref": ref("owner", 3, "canary"), "canary_evidence": canary_evidence(shadowed, "owner"), "receipt": receipt("aoa-session-memory", "owner-x", packet=shadowed)},
    )
    adopted = MODULE.apply_lifecycle_event(
        accepted,
        {
            "kind": "adoption",
            "status": "accepted",
            "adoption_ref": ref("adoption", 2, "adoption"),
            "receipt": receipt("aoa-session-memory", "adoption-x", kind="adoption", packet=accepted),
        },
    )
    rolled_back = MODULE.apply_lifecycle_event(
        adopted,
        {"kind": "rollback", "status": "rolled_back", "rollback_ref": ref("rollback", 2, "rollback"), "receipt": receipt("aoa-session-memory", "rollback-x", packet=accepted)},
    )
    assert rolled_back["lifecycle"]["state"] == "rolled_back"
    assert rolled_back["lifecycle"]["adoption_allowed"] is False
    assert len(rolled_back["lifecycle"]["history"]) == 6
    schema = json.loads((REPO_ROOT / "schemas" / "experience-metabolism-report.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(rolled_back)

    superseded = MODULE.apply_lifecycle_event(
        adopted,
        {
            "kind": "supersede",
            "status": "superseded",
            "replacement_ref": ref("replacement", 2, "replacement"),
            "receipt": receipt("aoa-session-memory", "supersede-x", kind="supersede", packet=adopted),
        },
    )
    assert superseded["lifecycle"]["state"] == "superseded"
    assert len(superseded["lifecycle"]["history"]) == 6
    Draft202012Validator(schema).validate(superseded)


def test_report_schema_is_valid() -> None:
    schema = json.loads((REPO_ROOT / "schemas" / "experience-metabolism-report.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    Draft202012Validator(schema).validate(report)


def test_writer_and_schema_share_strict_number_and_timestamp_boundaries() -> None:
    assert MODULE.int_value(2.0) == 2
    assert MODULE.int_value(2.5) is None
    assert MODULE.int_value(float("nan")) is None
    assert MODULE.safe_observed_at("2026-08-26T23:59:59Z") == "2026-08-26T23:59:59Z"
    assert MODULE.safe_observed_at("2026-02-30T23:59:59Z") == "unknown"
    assert MODULE.safe_observed_at("2026-08-26T24:00:00Z") == "unknown"
    schema = json.loads((REPO_ROOT / "schemas" / "experience-metabolism-report.schema.json").read_text(encoding="utf-8"))
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])])],
        minimum_occurrences=1,
        observed_at="2026-08-26T24:00:00Z",
    )
    assert report["observed_at"] == "unknown"
    Draft202012Validator(schema).validate(report)


def test_schema_closes_candidate_and_lifecycle_packets() -> None:
    schema = json.loads((REPO_ROOT / "schemas" / "experience-metabolism-report.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    candidate = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    validator.validate(candidate)
    candidate["privacy"]["raw_command"] = "must-not-pass"
    with pytest.raises(Exception):
        validator.validate(candidate)


def test_logical_ref_rejects_endpoint_suffix_injection() -> None:
    malicious = {
        "scheme": MODULE.REF_SCHEME,
        "start": json.dumps(
            {"scheme": MODULE.REF_SCHEME, "event": "event:sha256:" + "a" * 16},
            separators=(",", ":"),
        ) + ";/private/example",
    }
    assert MODULE.safe_logical_ref(malicious) is None


def test_lifecycle_rejects_minimal_packet_and_immutable_base_mutation() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    with pytest.raises(MODULE.MetabolismError, match="candidate_packet_shape_invalid"):
        MODULE.apply_lifecycle_event({"lifecycle": {}}, {"kind": "reject", "status": "rejected", "receipt": receipt("aoa-session-memory", "reject")})
    forged = json.loads(json.dumps(packet))
    forged["alternative_explanations"][0] = "mutated after emission"
    with pytest.raises(MODULE.MetabolismError, match="lifecycle_base_digest_invalid"):
        MODULE.apply_lifecycle_event(forged, {"kind": "reject", "status": "rejected", "receipt": receipt("aoa-session-memory", "reject")})


def test_lifecycle_receipt_owner_integrity_and_type_are_bound_to_event_kind() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    with pytest.raises(MODULE.MetabolismError, match="lifecycle_receipt_owner_invalid"):
        MODULE.apply_lifecycle_event(
            packet,
            {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": receipt("aoa-evals", "wrong-owner", packet=packet)},
        )
    with pytest.raises(MODULE.MetabolismError, match="lifecycle_receipt_invalid"):
        MODULE.apply_lifecycle_event(
            packet,
            {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": receipt("reviewer-office", "rejected-integrity", integrity="rejected", packet=packet)},
        )
    wrong_type = receipt("reviewer-office", "wrong-type", packet=packet)
    wrong_type["receipt_type"] = "eval-verdict-v1"
    with pytest.raises(MODULE.MetabolismError, match="lifecycle_receipt_type_invalid"):
        MODULE.apply_lifecycle_event(
            packet,
            {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": wrong_type},
        )


def test_lifecycle_receipt_cannot_be_reused_for_an_opposite_disposition() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    review_receipt = receipt("reviewer-office", "receipt-reuse", packet=packet)
    with pytest.raises(MODULE.MetabolismError, match="lifecycle_receipt_event_status_mismatch"):
        MODULE.apply_lifecycle_event(
            packet,
            {"kind": "review_verdict", "status": "rejected", "receipt": review_receipt},
        )
    with pytest.raises(MODULE.MetabolismError, match="lifecycle_receipt_owner_invalid"):
        MODULE.apply_lifecycle_event(
            packet,
            {"kind": "reject", "status": "rejected", "receipt": review_receipt},
        )


def test_lifecycle_receipt_digest_and_packet_free_text_are_not_trusted() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    forged_receipt = receipt("reviewer-office", "forged-digest", packet=packet)
    forged_receipt["digest"] = DIGEST
    with pytest.raises(MODULE.MetabolismError, match="lifecycle_receipt_digest_invalid"):
        MODULE.apply_lifecycle_event(
            packet,
            {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": forged_receipt},
        )

    forged_text = json.loads(json.dumps(packet))
    forged_text["alternative_explanations"][0] = "raw transcript text must not become lifecycle data"
    forged_text["lifecycle"]["base_digest"] = MODULE._candidate_base_digest(forged_text)
    with pytest.raises(MODULE.MetabolismError, match="candidate_alternative_explanations_invalid"):
        MODULE.apply_lifecycle_event(
            forged_text,
            {"kind": "reject", "status": "rejected", "receipt": receipt("aoa-session-memory", "forged-text", kind="reject", packet=forged_text)},
        )

    forged_observation = json.loads(json.dumps(packet))
    forged_observation["advisory_observation"]["notes"] = "untrusted notes"
    forged_observation["lifecycle"]["base_digest"] = MODULE._candidate_base_digest(forged_observation)
    with pytest.raises(MODULE.MetabolismError, match="candidate_observation_invalid"):
        MODULE.apply_lifecycle_event(
            forged_observation,
            {"kind": "reject", "status": "rejected", "receipt": receipt("aoa-session-memory", "forged-observation", kind="reject", packet=forged_observation)},
        )


def test_lifecycle_receipts_bind_candidate_and_immutable_base_digest() -> None:
    report = MODULE.build_report(
        [
            profile([session("one", [attempt("one", 2), attempt("one", 4, repeat=True)])]),
            profile([session("two", [attempt("two", 2)])]),
        ],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    other = next(item for item in report["candidates"] if item["motif"]["signal"] == "repeated_operation")
    other_receipt = receipt("reviewer-office", "other-candidate", packet=other)
    with pytest.raises(MODULE.MetabolismError, match="lifecycle_receipt_candidate_mismatch"):
        MODULE.apply_lifecycle_event(
            packet,
            {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": other_receipt},
        )
    stale_receipt = receipt("reviewer-office", "stale-base", packet=packet)
    stale_receipt["base_digest"] = DIGEST
    with pytest.raises(MODULE.MetabolismError, match="lifecycle_receipt_base_digest_mismatch"):
        MODULE.apply_lifecycle_event(
            packet,
            {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": stale_receipt},
        )


def test_eval_rejects_arbitrary_or_mismatched_comparison_packets() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    reviewed = MODULE.apply_lifecycle_event(
        packet,
        {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": receipt("reviewer-office", "review-comparison", packet=packet)},
    )
    arbitrary = {"paired": ["uri://arbitrary"], "held_out": ["uri://arbitrary"], "ablation": ["uri://arbitrary"]}
    with pytest.raises(MODULE.MetabolismError, match="paired_held_out_ablation_required"):
        MODULE.apply_lifecycle_event(
            reviewed,
            {"kind": "eval_verdict", "status": "accepted", "comparisons": {"paired": "passed", "held_out": "passed", "ablation": "passed"}, "comparison_refs": arbitrary, "receipt": receipt("aoa-evals", "arbitrary-comparison", packet=reviewed)},
        )
    mismatched = comparison_refs("mismatch", reviewed)
    mismatched["held_out"][0]["comparison_type"] = "paired"
    with pytest.raises(MODULE.MetabolismError, match="paired_held_out_ablation_required"):
        MODULE.apply_lifecycle_event(
            reviewed,
            {"kind": "eval_verdict", "status": "accepted", "comparisons": {"paired": "passed", "held_out": "passed", "ablation": "passed"}, "comparison_refs": mismatched, "receipt": receipt("aoa-evals", "mismatched-comparison", packet=reviewed)},
        )
    stale = comparison_refs("stale", reviewed)
    stale["ablation"][0]["source_fingerprint"] = "sha256:" + "c" * 64
    with pytest.raises(MODULE.MetabolismError, match="paired_held_out_ablation_required"):
        MODULE.apply_lifecycle_event(
            reviewed,
            {"kind": "eval_verdict", "status": "accepted", "comparisons": {"paired": "passed", "held_out": "passed", "ablation": "passed"}, "comparison_refs": stale, "receipt": receipt("aoa-evals", "stale-comparison", packet=reviewed)},
        )


@pytest.mark.parametrize("mutation", ["subject", "candidate", "source_binding"])
def test_eval_comparisons_bind_subject_candidate_and_source_identity(mutation: str) -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    reviewed = MODULE.apply_lifecycle_event(
        packet,
        {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": receipt("reviewer-office", "review-bound-comparison", packet=packet)},
    )
    groups = comparison_refs("bound", reviewed)
    if mutation == "subject":
        groups["held_out"][0]["subject_ref"] = ref("different-subject", 6, "subject")
    elif mutation == "candidate":
        groups["ablation"][0]["candidate_id"] = "experience-candidate:" + "b" * 24
    else:
        groups["paired"][0]["source_binding_refs"] = ["sha256:" + "b" * 64]
    with pytest.raises(MODULE.MetabolismError, match="paired_held_out_ablation_required"):
        MODULE.apply_lifecycle_event(
            reviewed,
            {
                "kind": "eval_verdict",
                "status": "accepted",
                "comparisons": {"paired": "passed", "held_out": "passed", "ablation": "passed"},
                "comparison_refs": groups,
                "receipt": receipt("aoa-evals", "comparison-binding", packet=reviewed),
            },
        )


@pytest.mark.parametrize("field", ["result_ref", "evidence_digest"])
def test_eval_comparison_evidence_cannot_be_reused_across_modes(field: str) -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    reviewed = MODULE.apply_lifecycle_event(
        packet,
        {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": receipt("reviewer-office", "cross-mode-review", packet=packet)},
    )
    groups = comparison_refs("cross-mode-reuse", reviewed)
    groups["held_out"][0][field] = groups["paired"][0][field]
    with pytest.raises(MODULE.MetabolismError, match="paired_held_out_ablation_required"):
        MODULE.apply_lifecycle_event(
            reviewed,
            {
                "kind": "eval_verdict",
                "status": "accepted",
                "comparisons": {"paired": "passed", "held_out": "passed", "ablation": "passed"},
                "comparison_refs": groups,
                "receipt": receipt("aoa-evals", "cross-mode-reuse", packet=reviewed),
            },
        )


def test_invalid_member_in_lifecycle_reference_list_is_not_discarded() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    reviewed = MODULE.apply_lifecycle_event(
        packet,
        {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": receipt("reviewer-office", "review-strict-refs", packet=packet)},
    )
    evaluated = MODULE.apply_lifecycle_event(
        reviewed,
        {
            "kind": "eval_verdict",
            "status": "accepted",
            "comparisons": {"paired": "passed", "held_out": "passed", "ablation": "passed"},
            "comparison_refs": comparison_refs("strict-refs", reviewed),
            "receipt": receipt("aoa-evals", "strict-refs", packet=reviewed),
        },
    )
    with pytest.raises(MODULE.MetabolismError, match="shadow_measurement"):
        MODULE.apply_lifecycle_event(
            evaluated,
            {
                "kind": "shadow_result",
                "status": "accepted",
                "shadow_measurement": {
                    **shadow_measurement(evaluated, "shadow-strict-refs"),
                    "baseline": {
                        **shadow_measurement(evaluated, "shadow-strict-refs")["baseline"],
                        "ref": [ref("shadow", 2, "baseline"), {"scheme": MODULE.REF_SCHEME, "event": "not-a-valid-logical-ref"}],
                    },
                },
                "receipt": receipt("abyss-stack", "shadow-strict-refs", packet=evaluated),
            },
        )


def test_typed_shadow_measurement_binds_coverage_and_rejects_stale_or_partial_packets() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    reviewed = MODULE.apply_lifecycle_event(
        packet,
        {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": receipt("reviewer-office", "typed-shadow-review", packet=packet)},
    )
    evaluated = MODULE.apply_lifecycle_event(
        reviewed,
        {"kind": "eval_verdict", "status": "accepted", "comparisons": {"paired": "passed", "held_out": "passed", "ablation": "passed"}, "comparison_refs": comparison_refs("typed-shadow-eval", reviewed), "receipt": receipt("aoa-evals", "typed-shadow-eval", packet=reviewed)},
    )
    partial = shadow_measurement(evaluated, "partial-shadow", coverage_status="partial")
    with pytest.raises(MODULE.MetabolismError, match="shadow_coverage_incomplete"):
        MODULE.apply_lifecycle_event(
            evaluated,
            {"kind": "shadow_result", "status": "accepted", "shadow_measurement": partial, "receipt": receipt("abyss-stack", "partial-shadow", packet=evaluated)},
        )
    stale = shadow_measurement(evaluated, "stale-shadow")
    stale["baseline"]["wall_clock_seconds"] = 99.0
    with pytest.raises(MODULE.MetabolismError, match="shadow_measurement"):
        MODULE.apply_lifecycle_event(
            evaluated,
            {"kind": "shadow_result", "status": "accepted", "shadow_measurement": stale, "receipt": receipt("abyss-stack", "stale-shadow", packet=evaluated)},
        )


def test_typed_shadow_binding_keeps_candidate_and_comparison_cohorts_distinct() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    reviewed = MODULE.apply_lifecycle_event(
        packet,
        {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": receipt("reviewer-office", "cohort-review", packet=packet)},
    )
    evaluated = MODULE.apply_lifecycle_event(
        reviewed,
        {"kind": "eval_verdict", "status": "accepted", "comparisons": {"paired": "passed", "held_out": "passed", "ablation": "passed"}, "comparison_refs": comparison_refs("cohort-eval", reviewed), "receipt": receipt("aoa-evals", "cohort-eval", packet=reviewed)},
    )
    measurement = shadow_measurement(evaluated, "later-cohort")
    later_source = "sha256:" + "b" * 64
    measurement["comparison_source_binding_refs"] = [later_source]
    for side in ("baseline", "shadow"):
        measurement[side]["source_binding_refs"] = [later_source]
    unsigned = {key: measurement[key] for key in (
        "schema_version", "candidate_id", "candidate_source_binding_refs", "comparison_source_binding_refs",
        "comparison_mode", "baseline", "shadow", "net_benefit", "trajectory_cost", "admission",
    )}
    measurement["measurement_digest"] = "sha256:" + MODULE.stable_digest(unsigned)
    normalized = MODULE._normalize_shadow_measurement(measurement, candidate=evaluated)
    assert normalized["candidate_source_binding_refs"] == evaluated["recurrence"]["source_binding_refs"]
    assert normalized["comparison_source_binding_refs"] == [later_source]


def test_live_canary_binding_is_required_and_must_match_the_accepted_shadow() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    reviewed = MODULE.apply_lifecycle_event(
        packet,
        {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": receipt("reviewer-office", "canary-review", packet=packet)},
    )
    evaluated = MODULE.apply_lifecycle_event(
        reviewed,
        {"kind": "eval_verdict", "status": "accepted", "comparisons": {"paired": "passed", "held_out": "passed", "ablation": "passed"}, "comparison_refs": comparison_refs("canary-eval", reviewed), "receipt": receipt("aoa-evals", "canary-eval", packet=reviewed)},
    )
    shadowed = MODULE.apply_lifecycle_event(
        evaluated,
        {"kind": "shadow_result", "status": "accepted", "shadow_measurement": shadow_measurement(evaluated, "canary-shadow"), "receipt": receipt("abyss-stack", "canary-shadow", packet=evaluated)},
    )
    bad_canary = canary_evidence(shadowed, "canary-bad")
    bad_canary["baseline_ref"] = ref("different-baseline", 8, "baseline")
    with pytest.raises(MODULE.MetabolismError, match="live_canary_evidence"):
        MODULE.apply_lifecycle_event(
            shadowed,
            {"kind": "owner_acceptance", "status": "accepted", "owner_ref": ref("owner", 2, "owner"), "live_canary_ref": ref("owner", 3, "canary"), "canary_evidence": bad_canary, "receipt": receipt("aoa-session-memory", "canary-bad", packet=shadowed)},
        )


def test_live_canary_rejects_a_foreign_source_cohort() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    packet = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    reviewed = MODULE.apply_lifecycle_event(
        packet,
        {"kind": "review_verdict", "status": "accepted", "independent_reviewer": True, "receipt": receipt("reviewer-office", "foreign-cohort-review", packet=packet)},
    )
    evaluated = MODULE.apply_lifecycle_event(
        reviewed,
        {"kind": "eval_verdict", "status": "accepted", "comparisons": {"paired": "passed", "held_out": "passed", "ablation": "passed"}, "comparison_refs": comparison_refs("foreign-cohort-eval", reviewed), "receipt": receipt("aoa-evals", "foreign-cohort-eval", packet=reviewed)},
    )
    shadowed = MODULE.apply_lifecycle_event(
        evaluated,
        {"kind": "shadow_result", "status": "accepted", "shadow_measurement": shadow_measurement(evaluated, "foreign-cohort-shadow"), "receipt": receipt("abyss-stack", "foreign-cohort-shadow", packet=evaluated)},
    )
    foreign_sources = ["sha256:" + "b" * 64]
    with pytest.raises(MODULE.MetabolismError, match="live_canary_evidence"):
        MODULE.apply_lifecycle_event(
            shadowed,
            {
                "kind": "owner_acceptance",
                "status": "accepted",
                "owner_ref": ref("owner", 2, "owner"),
                "live_canary_ref": ref("owner", 3, "canary"),
                "canary_evidence": canary_evidence(shadowed, "foreign-cohort-canary", source_binding_refs=foreign_sources),
                "receipt": receipt(
                    "aoa-session-memory",
                    "foreign-cohort-canary",
                    packet=shadowed,
                    canary_source_binding_refs=foreign_sources,
                ),
            },
        )


def test_review_provenance_is_emitted_as_hashed_refs_and_nonfinite_numbers_are_unknown() -> None:
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    candidate = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    assert report["session_gates"][0]["review_ref"]["scheme"] == MODULE.REF_SCHEME
    assert candidate["provenance"]["review_refs"]
    assert candidate["provenance"]["review_refs"] == MODULE.safe_evidence_refs(
        row["review_ref"] for row in candidate["evidence_diversity"]["occurrence_rows"]
    )
    assert MODULE.number_value(float("inf")) is None
    assert MODULE.number_value(float("nan")) is None


def test_over_limit_occurrences_emit_coverage_marker_and_omitted_digest() -> None:
    profiles = [profile([session(f"session-{index}", [attempt(f"session-{index}", 2)])]) for index in range(17)]
    report = MODULE.build_report(profiles, minimum_occurrences=17)
    candidate = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    diversity = candidate["evidence_diversity"]
    assert diversity["total_occurrence_count"] == 17
    assert diversity["emitted_occurrence_count"] == MODULE.MAX_EVIDENCE_REFS
    assert diversity["omitted_occurrence_count"] == 1
    assert diversity["truncated"] is True
    assert MODULE.SAFE_DIGEST.fullmatch(diversity["omitted_occurrence_digest"])


def test_report_and_comparison_inputs_fail_closed_at_serialization_bounds() -> None:
    too_many_sessions = [
        profile([session(f"bounded-{index}", [attempt(f"bounded-{index}", 2)])])
        for index in range(257)
    ]
    with pytest.raises(MODULE.MetabolismError, match="session_gate_limit_exceeded"):
        MODULE.build_report(too_many_sessions, minimum_occurrences=1)

    occurrence = {
        "session_ref": "session:sha256:" + "a" * 16,
        "source_binding_ref": DIGEST,
        "episode_ref": ref("bounded", 1, "episode"),
    }
    with pytest.raises(MODULE.MetabolismError, match="recurrence_reference_limit_exceeded"):
        MODULE.recurrence(
            [{**occurrence, "session_ref": f"session:sha256:{index:016x}"} for index in range(257)],
            minimum_sessions=2,
            minimum_occurrences=1,
        )


def test_schema_allows_insufficient_truncation_but_rejects_forged_accepted_state() -> None:
    schema = json.loads((REPO_ROOT / "schemas" / "experience-metabolism-report.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    profiles = [profile([session(f"session-{index}", [attempt(f"session-{index}", 2)])]) for index in range(17)]
    report = MODULE.build_report(profiles, minimum_occurrences=17)
    candidate = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    validator.validate(candidate)
    forged = json.loads(json.dumps(candidate))
    forged["lifecycle"]["state"] = "accepted"
    with pytest.raises(Exception):
        validator.validate(forged)


def test_terminal_lifecycle_schema_is_exhaustive_and_nested_cost_is_validated() -> None:
    schema = json.loads((REPO_ROOT / "schemas" / "experience-metabolism-report.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    report = MODULE.build_report(
        [profile([session("one", [attempt("one", 2)])]), profile([session("two", [attempt("two", 2)])])],
        minimum_occurrences=2,
    )
    candidate = next(item for item in report["candidates"] if item["motif"]["signal"] == "operation_observed")
    rejected = MODULE.apply_lifecycle_event(
        candidate,
        {"kind": "reject", "status": "rejected", "receipt": receipt("aoa-session-memory", "terminal-reject", kind="reject", packet=candidate)},
    )
    validator.validate(rejected)

    forged_terminal = json.loads(json.dumps(candidate))
    forged_terminal["lifecycle"]["state"] = "rejected"
    with pytest.raises(Exception):
        validator.validate(forged_terminal)

    malformed = json.loads(json.dumps(candidate))
    malformed["trajectory_cost"]["proxies"]["repeat_occurrence_count"] = "not-an-integer"
    malformed["lifecycle"]["base_digest"] = MODULE._candidate_base_digest(malformed)
    with pytest.raises(MODULE.MetabolismError, match="candidate_trajectory_cost_invalid"):
        MODULE.apply_lifecycle_event(
            malformed,
            {"kind": "reject", "status": "rejected", "receipt": receipt("aoa-session-memory", "malformed-cost", kind="reject", packet=malformed)},
        )

    null_count = json.loads(json.dumps(candidate))
    null_count["trajectory_cost"]["operation_span_seconds"]["known_occurrence_count"] = None
    null_count["lifecycle"]["base_digest"] = MODULE._candidate_base_digest(null_count)
    with pytest.raises(MODULE.MetabolismError, match="candidate_trajectory_cost_invalid"):
        MODULE.apply_lifecycle_event(
            null_count,
            {"kind": "reject", "status": "rejected", "receipt": receipt("aoa-session-memory", "null-cost", kind="reject", packet=null_count)},
        )

    null_review_count = json.loads(json.dumps(candidate))
    null_review_count["provenance"]["review_ref_count"] = None
    null_review_count["lifecycle"]["base_digest"] = MODULE._candidate_base_digest(null_review_count)
    with pytest.raises(MODULE.MetabolismError, match="candidate_provenance_invalid"):
        MODULE.apply_lifecycle_event(
            null_review_count,
            {"kind": "reject", "status": "rejected", "receipt": receipt("aoa-session-memory", "null-review-count", kind="reject", packet=null_review_count)},
        )


@pytest.mark.parametrize(
    "extra_args",
    [
        ["--event", "event.json"],
        ["--packet", "packet.json"],
        ["--baseline-profile", "baseline.json"],
        ["--shadow-profile", "shadow.json"],
        ["--comparison-ref", "ignored"],
        ["--comparison-packet", "comparison.json"],
        ["--comparison-mode", "paired"],
    ],
)
def test_cli_rejects_partial_or_ignored_mode_inputs(extra_args: list[str]) -> None:
    with pytest.raises(SystemExit):
        MODULE.parse_args(["--profile", "profile.json", *extra_args])


def test_cli_rejects_mixed_or_incomplete_shadow_modes() -> None:
    with pytest.raises(SystemExit):
        MODULE.parse_args([
            "--profile", "profile.json",
            "--baseline-profile", "baseline.json",
            "--shadow-profile", "shadow.json",
            "--comparison-mode", "paired",
            "--comparison-ref", "legacy-ref",
        ])
    with pytest.raises(SystemExit):
        MODULE.parse_args([
            "--profile", "profile.json",
            "--baseline-profile", "baseline.json",
            "--shadow-profile", "shadow.json",
            "--comparison-mode", "paired",
        ])
