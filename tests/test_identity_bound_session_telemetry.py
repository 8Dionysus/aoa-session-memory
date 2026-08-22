from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import identity_bound_session_telemetry as telemetry  # noqa: E402


def field(value: object, source: str = "test-owner") -> dict[str, object]:
    return telemetry.known(value, source=source)


def source_fields() -> dict[str, dict[str, object]]:
    return {
        "raw_sha256": field("a" * 64),
        "raw_bytes": field(100),
        "raw_line_count": field(10),
    }


def identity_fields(**overrides: object) -> dict[str, dict[str, object]]:
    values = {
        name: f"{name}-fixture"
        for name in telemetry.IDENTITY_FIELDS
    }
    values.update(overrides)
    return {name: field(value) for name, value in values.items()}


def trajectory(*, incomplete_step: str | None = None) -> dict[str, object]:
    steps: dict[str, object] = {}
    for name in telemetry.STEP_NAMES:
        if name == incomplete_step:
            steps[name] = {"state": "unknown", "reason": "owner_correlation_not_observed"}
            continue
        steps[name] = {
            "state": "known",
            "reason": "owner_observed",
            "correlation_id": field(f"correlation-{name}"),
            "timestamp": field("2026-08-22T00:00:00Z"),
            "outcome": field("observed"),
            "evidence_refs": [{"kind": "owner-receipt", "value": f"owner:receipt#{name}"}],
        }
    return {"chain_id": field("chain-1"), "steps": steps}


def make_receipt(
    *,
    identity_overrides: dict[str, object] | None = None,
    cache_posture: str = "disabled",
    review_status: str = "reviewed",
    incomplete_step: str | None = None,
) -> dict[str, object]:
    return telemetry.build_owner_telemetry_receipt(
        session_id="s1",
        session_ref="session:s1",
        correlation_id="correlation-chain",
        source=source_fields(),
        identity=identity_fields(**(identity_overrides or {})),
        trajectory=trajectory(incomplete_step=incomplete_step),
        timing={
            name: field(1.0, source="owner-timing",)
            for name in telemetry.TIMING_FIELDS
        },
        cache={
            "posture": field(cache_posture),
            "identity": field("cache-fixture"),
            "observed_state": field("not_used"),
        },
        resource={
            "posture": field("observed"),
            "metrics": {
                "cpu_ms": field(12.0, source="owner-resource"),
                "peak_rss_bytes": field(2048, source="owner-resource"),
                "io_read_bytes": field(4096, source="owner-resource"),
                "io_write_bytes": field(512, source="owner-resource"),
            },
        },
        evidence_refs=[{"kind": "owner-receipt", "value": "owner:receipt#root"}],
        review_status=review_status,
        projection={
            "prefix_identity": "sha256:" + "b" * 64,
            "publish_id": "sha256:" + "c" * 64,
        },
    )


def project(
    receipt: dict[str, object] | None,
    *,
    projection_status: str = "current",
    source: dict[str, object] | None = None,
    prefix_identity: str | None = "sha256:" + "b" * 64,
    publish_id: str | None = "sha256:" + "c" * 64,
) -> dict[str, object]:
    return telemetry.project_identity_bound_packet(
        session_id="s1",
        session_ref="session:s1",
        source=source or {"raw_sha256": "a" * 64, "raw_bytes": 100, "raw_line_count": 10},
        prefix_identity=prefix_identity,
        publish_id=publish_id,
        projection_status=projection_status,
        review_status="provisional",
        profile={"schema_version": "stage_profile_v1", "stage_spans": {}},
        owner_receipt=receipt,
    )


def test_projection_preserves_unknown_missing_and_unobservable_without_owner_receipt() -> None:
    packet = project(None, projection_status="stale-readable", source={})

    assert all(packet["identity"][name]["state"] == "missing" for name in telemetry.IDENTITY_FIELDS)
    assert all(packet["timing"][name]["state"] == "unobservable" for name in telemetry.TIMING_FIELDS)
    assert packet["review"]["status"] == "provisional"
    assert packet["eligibility"]["status"] == "excluded"
    assert packet["authority"]["comparison_verdict"] is None
    assert packet["authority"]["proof"] is False
    telemetry.verify_packet_integrity(packet)


def test_owner_receipt_binds_exact_source_and_yields_admission_only_packet() -> None:
    packet = project(make_receipt())

    assert packet["eligibility"]["status"] == "eligible_identity_packet"
    assert packet["methods"]["owner_receipt_federation"]["status"] == "admitted"
    assert packet["resource"]["metrics"]["peak_rss_bytes"]["value"] == 2048
    assert packet["authority"]["comparison_verdict"] is None
    assert telemetry.compare_identity_packets(packet, packet) == {
        "schema_version": "identity_bound_session_comparison_admission_v1",
        "status": "matched_identity_bound_pair",
        "eligible": True,
        "reasons": [],
        "effect": None,
        "verdict": None,
        "authority": "session-memory-admission-only; validation-owner-and-eval-verdicts-external",
    }


@pytest.mark.parametrize(
    ("field_name", "left_value", "right_value"),
    [
        ("candidate_or_source_identity", "candidate-a", "candidate-b"),
        ("environment_id", "environment-a", "environment-b"),
    ],
)
def test_comparison_excludes_wrong_identity(field_name: str, left_value: str, right_value: str) -> None:
    left = project(make_receipt(identity_overrides={field_name: left_value}))
    right = project(make_receipt(identity_overrides={field_name: right_value}))

    result = telemetry.compare_identity_packets(left, right)

    assert result["eligible"] is False
    assert f"identity_mismatch:{field_name}" in result["reasons"]
    assert result["effect"] is None
    assert result["verdict"] is None


def test_stale_projection_is_readable_but_not_pair_current() -> None:
    left = project(make_receipt(), projection_status="stale-readable")
    right = project(make_receipt())

    assert left["eligibility"]["status"] == "eligible_identity_packet"
    result = telemetry.compare_identity_packets(left, right)
    assert result["eligible"] is False
    assert "left_projection_stale-readable" in result["reasons"]


def test_projection_coordinates_are_required_for_owner_receipt_admission() -> None:
    receipt = make_receipt()
    receipt["binding"]["projection"]["publish_id"] = telemetry.missing("projection_publish_not_declared")
    receipt["receipt_id"] = telemetry.canonical_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_id"}
    )
    packet = telemetry.project_identity_bound_packet(
        session_id="s1",
        session_ref="session:s1",
        source={"raw_sha256": "a" * 64, "raw_bytes": 100, "raw_line_count": 10},
        prefix_identity="sha256:" + "b" * 64,
        publish_id="sha256:" + "c" * 64,
        projection_status="current",
        review_status="reviewed",
        owner_receipt=receipt,
    )
    assert packet["methods"]["owner_receipt_federation"]["status"] == "rejected"
    assert packet["methods"]["owner_receipt_federation"]["rejection"] == "projection_identity_missing:publish_id"


def test_partial_cache_and_incomplete_correlation_are_excluded() -> None:
    partial_cache = project(make_receipt(cache_posture="partial"))
    incomplete = project(make_receipt(incomplete_step="repair"))

    assert "cache_posture_partial_unadmitted" in partial_cache["eligibility"]["reasons"]
    assert partial_cache["eligibility"]["status"] == "excluded"
    assert "trajectory_repair_unknown" in incomplete["eligibility"]["reasons"]
    assert incomplete["eligibility"]["status"] == "excluded"


def test_digest_tamper_and_private_fields_fail_closed() -> None:
    receipt = make_receipt()
    tampered = copy.deepcopy(receipt)
    tampered["identity"]["environment_id"]["value"] = "changed"
    with pytest.raises(telemetry.TelemetryError, match="digest_mismatch"):
        telemetry.admit_owner_telemetry_receipt(
            tampered,
            expected_context={
                "session_id": "s1",
                "session_ref": "session:s1",
                "source": {"raw_sha256": "a" * 64, "raw_bytes": 100, "raw_line_count": 10},
            },
        )

    private = copy.deepcopy(receipt)
    private["identity"]["workload_id"] = {"command": "not admitted"}
    private["receipt_id"] = telemetry.canonical_sha256(
        {key: value for key, value in private.items() if key != "receipt_id"}
    )
    with pytest.raises(telemetry.TelemetryError, match="private_field_rejected"):
        telemetry.admit_owner_telemetry_receipt(
            private,
            expected_context={
                "session_id": "s1",
                "session_ref": "session:s1",
                "source": {"raw_sha256": "a" * 64, "raw_bytes": 100, "raw_line_count": 10},
            },
        )


def test_capture_adapter_reads_only_dedicated_facet() -> None:
    receipt = make_receipt()
    events = [
        {"facets": {"operation": "ignored"}},
        {"facets": {"identity_bound_telemetry_receipt": receipt}},
    ]

    captured = telemetry.capture_receipts_from_events(events)

    assert len(captured) == 1
    assert captured[0]["receipt_id"] == receipt["receipt_id"]


def test_receipt_packet_and_comparison_match_portable_schema() -> None:
    schema = json.loads(
        (REPO_ROOT / "schemas" / "identity-bound-session-telemetry.schema.json").read_text(encoding="utf-8")
    )
    packet = project(make_receipt())
    values = [make_receipt(), packet, telemetry.compare_identity_packets(packet, packet)]

    validator = Draft202012Validator(schema)
    for value in values:
        assert list(validator.iter_errors(value)) == []
