from __future__ import annotations

import copy
import hmac
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

import pytest
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import identity_bound_session_telemetry as telemetry  # noqa: E402


def field(value: object, source: str = "test-owner") -> dict[str, object]:
    return telemetry.known(value, source=source)


def source_fields(
    *,
    raw_sha256: str = "a" * 64,
    raw_bytes: int = 100,
    raw_line_count: int = 10,
) -> dict[str, dict[str, object]]:
    return {
        "raw_sha256": field(raw_sha256),
        "raw_bytes": field(raw_bytes),
        "raw_line_count": field(raw_line_count),
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
    session_id: str = "s1",
    session_ref: str = "session:s1",
    raw_sha256: str = "a" * 64,
    raw_bytes: int = 100,
    raw_line_count: int = 10,
    unobservable_timing: str | None = None,
) -> dict[str, object]:
    timing = {
        name: field(1.0, source="owner-timing")
        for name in telemetry.TIMING_FIELDS
    }
    if unobservable_timing:
        timing[unobservable_timing] = telemetry.unobservable(
            "owner_timing_not_observable", unit="seconds"
        )
    return telemetry.build_owner_telemetry_receipt(
        session_id=session_id,
        session_ref=session_ref,
        correlation_id="correlation-chain",
        source=source_fields(
            raw_sha256=raw_sha256,
            raw_bytes=raw_bytes,
            raw_line_count=raw_line_count,
        ),
        identity=identity_fields(**(identity_overrides or {})),
        trajectory=trajectory(incomplete_step=incomplete_step),
        timing=timing,
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
    session_id: str = "s1",
    session_ref: str = "session:s1",
) -> dict[str, object]:
    return telemetry.project_identity_bound_packet(
        session_id=session_id,
        session_ref=session_ref,
        source=source or {"raw_sha256": "a" * 64, "raw_bytes": 100, "raw_line_count": 10},
        prefix_identity=prefix_identity,
        publish_id=publish_id,
        projection_status=projection_status,
        review_status="provisional",
        profile={"schema_version": "stage_profile_v1", "stage_spans": {}},
        owner_receipt=receipt,
    )


def strict_episode_binding(
    *,
    session_id: str = "s1",
    session_ref: str = "session:s1",
    episode_id: str = "task-0001",
    from_line: int = 3,
    to_line: int = 10,
    raw_line_count: int = 10,
) -> dict[str, object]:
    component_ref = "session-index-shards/task-episodes/task-0001.json"
    component_range = {"from_line": from_line, "to_line": to_line}
    binding: dict[str, object] = {
        "episode_id": episode_id,
        "episode_ref": {
            "kind": "task-episode",
            "value": f"{session_ref}#task-episode:{episode_id}",
            "basis": "generated-task-episode-index",
        },
        "episode_component_ref": {
            "kind": "task-episode-component",
            "value": f"{session_ref}#component:{component_ref.replace('/', '%2F')}",
            "basis": "generated-task-episode-component-manifest",
        },
        "session_id": session_id,
        "session_ref": session_ref,
        "source": {"raw_sha256": "a" * 64, "raw_bytes": 100, "raw_line_count": raw_line_count},
        "component_identity": {
            "component": "task_episodes",
            "artifact_sha256": "d" * 64,
            "payload_sha256": "e" * 64,
            "task_episode_generation_id": "f" * 64,
            "episode_source_sha256": "1" * 64,
            "event_range": component_range,
            "privacy_policy_version": 1,
            "redaction_policy_version": 1,
        },
        "manifest_admission": {
            "manifest_ref": {
                "kind": "task-episode-component-manifest",
                "value": f"{session_ref}#session-index-shards/manifest.json",
                "basis": "generated-task-episode-component-manifest",
            },
            "manifest_sha256": "2" * 64,
            "component_ref": component_ref,
        },
        "event_range": component_range,
        "binding_status": "exact_episode_range",
        "owner_validation": {
            "profile": telemetry.OWNER_VALIDATION_PROFILE,
            "status": "validated",
            "validator": telemetry.OWNER_VALIDATION_REF,
            "ordered_range": "checked",
        },
    }
    binding["portable_witness"] = telemetry._build_episode_admission_witness(binding)
    return binding


def write_test_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def owner_root_witness(root: Path) -> telemetry.OwnerRootWitness:
    return alias_owner_root_witness(root)


def alias_owner_root_witness(root: Path) -> telemetry.OwnerRootWitness:
    root.mkdir(parents=True, exist_ok=True)
    owner_dir = root / ".owner"
    owner_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(b"synthetic-owner-alias-fixture").digest()
    signer = hashlib.sha256(b"synthetic-owner-admission-signer").digest()
    anchor_ref = "owner:synthetic-admission-anchor"

    def verify(message_digest: str, signature: str) -> bool:
        expected = "sha256:" + hmac.new(
            signer,
            message_digest.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    telemetry._provision_owner_alias_trust_anchor(
        anchor_ref,
        verify,
        token=telemetry._OWNER_ALIAS_TRUST_ANCHOR_PROVISION_TOKEN,
    )
    key_path = owner_dir / "session-alias.key"
    key_path.write_bytes(key)
    root_sha256 = telemetry._owner_root_identity_digest(
        telemetry._owner_directory_identity_snapshot(root)
    )
    contract = {
        "schema_version": telemetry.OWNER_ALIAS_SOURCE_SCHEMA_VERSION,
        "issuer": "aoa-session-memory",
        "source_ref": "owner:fixture-alias-source",
        "trust_anchor_ref": anchor_ref,
        "key_path": telemetry.OWNER_ALIAS_SOURCE_KEY_RELATIVE_PATH,
        "key_sha256": hashlib.sha256(key).hexdigest(),
        "root_sha256": root_sha256,
    }
    contract["epoch_sha256"] = telemetry._owner_alias_epoch_digest(
        root_sha256=root_sha256,
        source_ref=contract["source_ref"],
        trust_anchor_ref=contract["trust_anchor_ref"],
        key_sha256=contract["key_sha256"],
    )
    contract["admission_signature"] = "sha256:" + hmac.new(
        signer,
        telemetry._owner_alias_admission_message(contract).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    contract["contract_sha256"] = telemetry.canonical_sha256(contract)
    write_test_json(owner_dir / "session-alias-source.json", contract)
    return telemetry._owner_root_witness_for_root(root)


def attach_event_source_evidence(
    event: dict[str, object],
    *,
    source_ref: str,
    source_path: Path | None = None,
) -> telemetry.OwnerCapturedEvent:
    return telemetry._attach_owner_source_evidence(
        event,
        source_ref=source_ref,
        source_path=source_path,
        owner_root_witness=(
            owner_root_witness(source_path.parents[3]) if source_path is not None else None
        ),
    )


def component_admission(
    binding: dict[str, object],
    tmp_path: Path,
) -> telemetry.EpisodeComponentAdmission:
    session_dir = tmp_path / "owner-root" / "sessions" / "owner-session"
    component_ref = str(binding["manifest_admission"]["component_ref"])
    component_path = session_dir / component_ref
    session_manifest_path = session_dir / "session.manifest.json"
    manifest_path = session_dir / "session-index-shards" / "manifest.json"
    payload = {
        "episode_id": str(binding["episode_id"]),
        "status": "closed",
        "event_range": copy.deepcopy(binding["event_range"]),
    }
    component_identity = binding["component_identity"]
    episode_source_sha256 = telemetry.canonical_episode_source_sha256(payload)
    payload_sha256 = telemetry._canonical_component_payload_sha256(payload)
    envelope = {
        "schema_version": 1,
        "artifact_type": "session_index_component_shard",
        "component": "task_episodes",
        "component_key": "0000:task-0001",
        "source_identity": {
            "task_episode_generation_id": component_identity["task_episode_generation_id"],
            "episode_source_sha256": episode_source_sha256,
            "event_range": copy.deepcopy(binding["event_range"]),
            "privacy_policy_version": component_identity["privacy_policy_version"],
            "redaction_policy_version": component_identity["redaction_policy_version"],
        },
        "payload_sha256": payload_sha256,
        "payload": payload,
    }
    write_test_json(component_path, envelope)
    artifact_sha256 = hashlib.sha256(component_path.read_bytes()).hexdigest()
    expected_projection = {"owner": "test-current-projection", "generation": "f" * 64}
    expected_generation_context = {
        "task_episode_generation": str(component_identity["task_episode_generation_id"]),
        "segment_generation": "b" * 64,
        "session_generation": "c" * 64,
    }
    source = copy.deepcopy(binding["source"])
    write_test_json(
        session_manifest_path,
        {
            "session_id": binding["session_id"],
            "session_label": session_dir.name,
            "archive_status": "indexed",
            "raw": {
                "sha256": source["raw_sha256"],
                "bytes": source["raw_bytes"],
                "line_count": source["raw_line_count"],
            },
            "index_schema": {
                "projection_publish": expected_projection,
                "session_index_generation_id": expected_generation_context["session_generation"],
                "segment_index_generation_id": expected_generation_context["segment_generation"],
            },
        },
    )
    write_test_json(
        manifest_path,
        {
            "projection_publish": expected_projection,
            "source_identity": {
                **source,
                "task_episode_generation_id": component_identity["task_episode_generation_id"],
            },
            "components": {
                "task_episodes": [
                    {
                        "component_key": "0000:task-0001",
                        "ref": component_ref,
                        "artifact_sha256": artifact_sha256,
                        "payload_sha256": payload_sha256,
                    }
                ]
            },
            "component_counts": {"task_episodes": 1},
            "component_order": {"task_episodes": [component_ref]},
        },
    )
    write_test_json(
        session_dir.parents[1] / "session-registry.json",
        {
            "schema_version": 1,
            "sessions": [
                {
                    "session_id": str(binding["session_id"]),
                    "session_label": session_dir.name,
                    "path": str(session_dir),
                    "archive_status": "indexed",
                    "segment_count": 0,
                }
            ],
        },
    )
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    component_identity.update(
        {
            "artifact_sha256": artifact_sha256,
            "payload_sha256": payload_sha256,
            "episode_source_sha256": episode_source_sha256,
        }
    )
    binding["manifest_admission"]["manifest_sha256"] = manifest_sha256
    binding["portable_witness"] = telemetry._build_episode_admission_witness(binding)
    root_witness = owner_root_witness(session_dir.parents[1])
    owner_membership = telemetry._owner_episode_component_membership(
        session_dir=session_dir,
        component_ref=str(binding["manifest_admission"]["component_ref"]),
        component_path=component_path,
        owner_root_witness=root_witness,
    )
    return telemetry._issue_episode_component_admission(
        session_id=str(binding["session_id"]),
        session_ref=str(binding["session_ref"]),
        episode_id=str(binding["episode_id"]),
        component_ref=str(binding["manifest_admission"]["component_ref"]),
        manifest_sha256=str(binding["manifest_admission"]["manifest_sha256"]),
        source=binding["source"],
        component_identity=binding["component_identity"],
        artifact_sha256=str(binding["component_identity"]["artifact_sha256"]),
        payload_sha256=str(binding["component_identity"]["payload_sha256"]),
        manifest_path=manifest_path,
        component_path=component_path,
        session_manifest_path=session_manifest_path,
        expected_projection=expected_projection,
        expected_task_episode_generation=str(component_identity["task_episode_generation_id"]),
        expected_generation_context=expected_generation_context,
        owner_membership=owner_membership,
    )


def event_artifact(tmp_path: Path, event: dict[str, object], name: str) -> Path:
    session_dir = tmp_path / "event-owner" / "sessions" / "fixture-session"
    path = session_dir / "segments" / f"{name}.segment.json"
    write_test_json(path, {"segment_id": name, "events": [event]})
    manifest_path = session_dir / "session.manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "session_id": "fixture-session",
            "session_label": session_dir.name,
            "archive_status": "indexed",
            "segments": [],
        }
    segments = manifest.setdefault("segments", [])
    segments[:] = [
        item
        for item in segments
        if not isinstance(item, dict) or str(item.get("index") or "") != str(path)
    ]
    stat = path.stat()
    segments.append(
        {
            "segment_id": name,
            "role": name,
            "index": str(path),
            "artifact_receipts": {
                "index": {
                    "bytes": stat.st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            },
        }
    )
    write_test_json(manifest_path, manifest)
    write_test_json(
        session_dir.parents[1] / "session-registry.json",
        {
            "schema_version": 1,
            "sessions": [
                {
                    "session_id": "fixture-session",
                    "session_label": session_dir.name,
                    "path": str(session_dir),
                    "archive_status": "indexed",
                    "segment_count": len(segments),
                }
            ],
        },
    )
    alias_owner_root_witness(session_dir.parents[1])
    return path


def carrying_event_witness(
    receipt: dict[str, object],
    *,
    tmp_path: Path,
    line: int = 3,
    event_id: str = "event-3",
) -> telemetry.CarryingEventWitness:
    event_value = {
        "line": line,
        "event_id": event_id,
        "correlation_id": "correlation-chain",
        "facets": {"identity_bound_telemetry_receipt": receipt},
    }
    event = attach_event_source_evidence(
        event_value,
        source_ref=f"owner:segment:{event_id}",
        source_path=event_artifact(tmp_path, event_value, event_id),
    )
    captured = telemetry.capture_receipt_facets(
        [event]
    )
    assert captured[0]["status"] == "admitted"
    witness = captured[0]["witness"]
    assert isinstance(witness, telemetry.CarryingEventWitness)
    return witness


def paired_contract() -> dict[str, object]:
    return telemetry.build_comparison_contract(
        design="paired",
        required_equal_identity_fields=list(telemetry.IDENTITY_FIELDS),
        allowed_identity_differences=[],
        required_equal_scope_fields=list(telemetry.COMPARISON_SCOPE_FIELDS),
        allowed_scope_differences=[],
        left_role_value="route_or_treatment_identity-fixture",
        right_role_value="route_or_treatment_identity-fixture",
    )


def test_projection_preserves_unknown_missing_and_unobservable_without_owner_receipt() -> None:
    packet = project(None, projection_status="stale-readable", source={})

    assert all(packet["identity"][name]["state"] == "missing" for name in telemetry.IDENTITY_FIELDS)
    assert all(packet["timing"][name]["state"] == "unobservable" for name in telemetry.TIMING_FIELDS)
    assert packet["review"]["status"] == "provisional"
    assert packet["eligibility"]["status"] == "missing"
    assert packet["authority"]["comparison_verdict"] is None
    assert packet["authority"]["proof"] is False
    telemetry.verify_packet_integrity(packet)


def test_owner_receipt_binds_exact_source_and_yields_admission_only_packet() -> None:
    packet = project(make_receipt())

    assert packet["eligibility"]["status"] == "eligible_identity_packet"
    assert packet["methods"]["owner_receipt_federation"]["status"] == "admitted"
    assert packet["resource"]["metrics"]["peak_rss_bytes"]["value"] == 2048
    assert packet["authority"]["comparison_verdict"] is None
    assert telemetry.compare_identity_packets(packet, packet, comparison_contract=paired_contract()) == {
        "schema_version": "identity_bound_session_comparison_admission_v1",
        "status": "matched_identity_bound_pair",
        "eligible": True,
        "reasons": [],
        "comparison_contract": paired_contract(),
        "effect": None,
        "verdict": None,
        "proof": False,
        "acceptance": False,
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

    result = telemetry.compare_identity_packets(left, right, comparison_contract=paired_contract())

    assert result["eligible"] is False
    assert f"identity_mismatch:{field_name}" in result["reasons"]
    assert result["effect"] is None
    assert result["verdict"] is None


def test_stale_projection_is_readable_but_not_pair_current() -> None:
    left = project(make_receipt(), projection_status="stale-readable")
    right = project(make_receipt())

    assert left["eligibility"]["status"] == "eligible_identity_packet"
    result = telemetry.compare_identity_packets(left, right, comparison_contract=paired_contract())
    assert result["eligible"] is False
    assert "left_projection_stale-readable" in result["reasons"]


def test_comparison_contract_rejects_vacuous_anchors_and_binds_typed_roles() -> None:
    with pytest.raises(telemetry.TelemetryError, match="non_vacuous_identity_anchor_required"):
        telemetry.build_comparison_contract(
            design="paired",
            required_equal_identity_fields=[],
            allowed_identity_differences=list(telemetry.IDENTITY_FIELDS),
            required_equal_scope_fields=[],
            allowed_scope_differences=list(telemetry.COMPARISON_SCOPE_FIELDS),
            left_role_value="left-value",
            right_role_value="right-value",
        )

    left = project(make_receipt(identity_overrides={"route_or_treatment_identity": "control"}))
    right = project(make_receipt(identity_overrides={"route_or_treatment_identity": "treatment"}))
    contract = telemetry.build_comparison_contract(
        design="treatment_control",
        required_equal_identity_fields=[
            name for name in telemetry.IDENTITY_FIELDS if name != "route_or_treatment_identity"
        ],
        allowed_identity_differences=["route_or_treatment_identity"],
        required_equal_scope_fields=["projection"],
        allowed_scope_differences=["session_id", "session_ref", "source", "episode_binding"],
    )
    result = telemetry.compare_identity_packets(left, right, comparison_contract=contract)
    assert result["eligible"] is True
    wrong_role = project(make_receipt(identity_overrides={"route_or_treatment_identity": "not-treatment"}))
    rejected = telemetry.compare_identity_packets(left, wrong_role, comparison_contract=contract)
    assert rejected["eligible"] is False
    assert "right_role_binding_mismatch:route_or_treatment_identity" in rejected["reasons"]


def test_comparison_excludes_unobservable_packet_even_when_integrity_is_valid() -> None:
    left = project(make_receipt(unobservable_timing="repair_latency_seconds"))
    right = project(make_receipt())
    assert left["eligibility"]["status"] == "unobservable"
    telemetry.verify_packet_integrity(left)
    result = telemetry.compare_identity_packets(left, right, comparison_contract=paired_contract())
    assert result["eligible"] is False
    assert "left_eligibility_unobservable" in result["reasons"]


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
    assert incomplete["eligibility"]["status"] == "unknown"


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


def test_capture_adapter_reads_only_dedicated_facet(tmp_path: Path) -> None:
    receipt = make_receipt()
    event = attach_event_source_evidence(
        {
            "line": 3,
            "event_id": "event-3",
            "correlation_id": "correlation-chain",
            "facets": {"identity_bound_telemetry_receipt": receipt},
        },
        source_ref="owner:test-event:event-3",
        source_path=event_artifact(tmp_path, {
            "line": 3,
            "event_id": "event-3",
            "correlation_id": "correlation-chain",
            "facets": {"identity_bound_telemetry_receipt": receipt},
        }, "capture-adapter"),
    )
    events = [
        {"facets": {"operation": "ignored"}},
        event,
    ]

    captured = telemetry.capture_receipts_from_events(events)

    assert len(captured) == 1
    assert captured[0]["receipt_id"] == receipt["receipt_id"]


def test_capture_requires_persistent_owner_event_evidence_and_rejects_boundary_downgrade(tmp_path: Path) -> None:
    receipt = make_receipt()
    event_value = {
        "line": 3,
        "event_id": "event-3",
        "correlation_id": "correlation-chain",
        "facets": {"identity_bound_telemetry_receipt": receipt},
    }

    process_local = telemetry._attach_owner_source_evidence(
        event_value,
        source_ref="owner:test-event:process-local",
    )
    rejected = telemetry.capture_receipt_facets([process_local])
    assert rejected[0]["status"] == "rejected"
    assert rejected[0]["rejection"] == "owner_event_source_evidence_not_persistent"

    persistent = attach_event_source_evidence(
        event_value,
        source_ref="owner:test-event:persistent",
        source_path=event_artifact(tmp_path, event_value, "persistent"),
    )
    serialized = json.loads(json.dumps(persistent, ensure_ascii=False))
    boundary_rejected = telemetry.capture_receipt_facets([serialized])
    assert boundary_rejected[0]["status"] == "rejected"
    assert boundary_rejected[0]["rejection"] == "owner_event_source_evidence_missing"

    tampered = attach_event_source_evidence(
        event_value,
        source_ref="owner:test-event:tampered",
        source_path=event_artifact(tmp_path, event_value, "tampered"),
    )
    tampered["facets"]["identity_bound_telemetry_receipt"] = copy.deepcopy(receipt)
    tampered["facets"]["identity_bound_telemetry_receipt"]["receipt_id"] = "sha256:" + "0" * 64
    tampered_result = telemetry.capture_receipt_facets([tampered])
    assert tampered_result[0]["status"] == "rejected"
    assert tampered_result[0]["rejection"] == "owner_event_source_evidence_mismatch"


def test_persistent_event_evidence_rejects_source_replacement_and_arbitrary_pairing(tmp_path: Path) -> None:
    receipt = make_receipt()
    event = {
        "line": 3,
        "event_id": "event-3",
        "correlation_id": "correlation-chain",
        "facets": {"identity_bound_telemetry_receipt": receipt},
    }
    source_path = event_artifact(tmp_path, event, "replacement")
    captured_event = attach_event_source_evidence(
        event,
        source_ref="owner:segment:replacement",
        source_path=source_path,
    )
    replacement = dict(event)
    replacement["event_id"] = "event-replaced"
    write_test_json(source_path, {"events": [replacement]})
    rejected = telemetry.capture_receipt_facets([captured_event])
    assert rejected[0]["status"] == "rejected"
    assert rejected[0]["rejection"] == "owner_event_source_evidence_mismatch"

    unrelated_path = event_artifact(tmp_path, event, "unrelated")
    with pytest.raises(telemetry.TelemetryAdmissionError, match="owner_event_source_semantic_mismatch"):
        attach_event_source_evidence(
            {**event, "event_id": "caller-minted"},
            source_ref="owner:segment:unrelated",
            source_path=unrelated_path,
        )

    plain_event = {"line": 4, "event_id": "event-4", "kind": "plain"}
    plain_path = event_artifact(tmp_path, plain_event, "plain")
    with pytest.raises(telemetry.TelemetryAdmissionError, match="owner_event_source_semantic_mismatch"):
        attach_event_source_evidence(
            {**plain_event, "kind": "caller-minted"},
            source_ref="owner:segment:plain",
            source_path=plain_path,
        )

    final_path = event_artifact(tmp_path, event, "final-admission")
    final_event = attach_event_source_evidence(
        event,
        source_ref="owner:segment:final-admission",
        source_path=final_path,
    )
    captured = telemetry.capture_receipt_facets([final_event])
    assert captured[0]["status"] == "admitted"
    binding = strict_episode_binding()
    packet = telemetry.project_identity_bound_episode_packet(
        session_id="s1",
        session_ref="session:s1",
        source=binding["source"],
        prefix_identity="sha256:" + "b" * 64,
        publish_id="sha256:" + "c" * 64,
        projection_status="current",
        review_status="reviewed",
        profile={"schema_version": "stage_profile_v1", "stage_spans": {}},
        owner_receipt=receipt,
        episode_binding=binding,
        component_admission=component_admission(binding, tmp_path),
        receipt_carrying_event_witness=captured[0]["witness"],
    )
    write_test_json(final_path, {"events": [{**event, "event_id": "replaced-after-packet"}]})
    with pytest.raises(telemetry.TelemetryAdmissionError, match="packet_carrying_event_owner_source_not_current"):
        telemetry.verify_packet_integrity(packet)


@pytest.mark.parametrize("mutation", ["symlink", "hardlink", "nonregular", "atomic_replace"])
def test_persistent_event_evidence_rejects_path_identity_substitution(
    tmp_path: Path,
    mutation: str,
) -> None:
    case_dir = tmp_path / mutation
    case_dir.mkdir()
    receipt = make_receipt()
    event = {
        "line": 3,
        "event_id": "event-3",
        "correlation_id": "correlation-chain",
        "facets": {"identity_bound_telemetry_receipt": receipt},
    }
    source_path = event_artifact(case_dir, event, mutation)
    captured = attach_event_source_evidence(
        event,
        source_ref=f"owner:segment:{mutation}",
        source_path=source_path,
    )
    original = source_path.read_bytes()
    if mutation == "symlink":
        target = case_dir / "same-bytes-target.json"
        target.write_bytes(original)
        source_path.unlink()
        source_path.symlink_to(target)
    elif mutation == "hardlink":
        target = case_dir / "same-bytes-target.json"
        target.write_bytes(original)
        source_path.unlink()
        os.link(target, source_path)
    elif mutation == "nonregular":
        source_path.unlink()
        source_path.mkdir()
    else:
        replacement = case_dir / "atomic-replacement.json"
        replacement.write_bytes(original)
        os.replace(replacement, source_path)

    rejected = telemetry.capture_receipt_facets([captured])
    assert rejected[0]["status"] == "rejected"
    assert rejected[0]["rejection"] == "owner_event_source_evidence_mismatch"


def test_persistent_event_evidence_rejects_parent_symlink_substitution(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    receipt = make_receipt()
    event = {
        "line": 3,
        "event_id": "event-3",
        "correlation_id": "correlation-chain",
        "facets": {"identity_bound_telemetry_receipt": receipt},
    }
    source_path = event_artifact(parent, event, "parent-symlink")
    captured = attach_event_source_evidence(
        event,
        source_ref="owner:segment:parent-symlink",
        source_path=source_path,
    )
    real_parent = tmp_path / "parent-real"
    parent.rename(real_parent)
    parent.symlink_to(real_parent, target_is_directory=True)

    rejected = telemetry.capture_receipt_facets([captured])
    assert rejected[0]["status"] == "rejected"
    assert rejected[0]["rejection"] == "owner_event_source_evidence_mismatch"


def test_receipt_packet_and_comparison_match_portable_schema() -> None:
    schema = json.loads(
        (REPO_ROOT / "schemas" / "identity-bound-session-telemetry.schema.json").read_text(encoding="utf-8")
    )
    packet = project(make_receipt())
    values = [make_receipt(), packet, telemetry.compare_identity_packets(packet, packet, comparison_contract=paired_contract())]

    validator = Draft202012Validator(schema)
    for value in values:
        assert list(validator.iter_errors(value)) == []


def test_episode_binding_is_exact_and_public_safe(tmp_path: Path) -> None:
    binding = strict_episode_binding()
    admission = component_admission(binding, tmp_path)
    receipt = make_receipt()
    packet = telemetry.project_identity_bound_episode_packet(
        session_id="s1",
        session_ref="session:s1",
        source={"raw_sha256": "a" * 64, "raw_bytes": 100, "raw_line_count": 10},
        prefix_identity="sha256:" + "b" * 64,
        publish_id="sha256:" + "c" * 64,
        projection_status="current",
        review_status="reviewed",
        profile={"schema_version": "stage_profile_v1", "stage_spans": {}},
        owner_receipt=receipt,
        component_admission=admission,
        receipt_carrying_event_witness=carrying_event_witness(receipt, tmp_path=tmp_path),
        episode_binding=binding,
    )

    assert packet["schema_version"] == telemetry.EPISODE_PACKET_SCHEMA_VERSION
    assert packet["episode_binding"]["binding_status"] == "exact_episode_range"
    assert packet["episode_binding"]["event_range"] == {"from_line": 3, "to_line": 10}
    assert "episode_binding" in json.dumps(packet, ensure_ascii=False)
    schema = json.loads(
        (REPO_ROOT / "schemas" / "identity-bound-session-telemetry.schema.json").read_text(encoding="utf-8")
    )
    assert list(Draft202012Validator(schema).iter_errors(packet)) == []


def test_pair_revalidates_scope_source_and_public_receipt_binding() -> None:
    left = project(make_receipt())
    right = project(
        make_receipt(
            session_id="s2",
            session_ref="session:s2",
            raw_sha256="b" * 64,
        ),
        session_id="s2",
        session_ref="session:s2",
        source={"raw_sha256": "b" * 64, "raw_bytes": 100, "raw_line_count": 10},
    )

    result = telemetry.compare_identity_packets(left, right, comparison_contract=paired_contract())

    assert result["eligible"] is False
    assert "scope_session_id_mismatch" in result["reasons"]
    assert "scope_session_ref_mismatch" in result["reasons"]
    assert "source_identity_mismatch:raw_sha256" in result["reasons"]
    assert result["effect"] is None
    assert result["verdict"] is None


def test_pair_rejects_stale_receipt_binding_even_after_packet_digest_recomputed() -> None:
    left = project(make_receipt())
    stale = copy.deepcopy(left)
    stale["scope"]["session_id"] = "s2"
    stale["packet_id"] = telemetry.canonical_sha256(
        {key: value for key, value in stale.items() if key != "packet_id"}
    )

    result = telemetry.compare_identity_packets(left, stale, comparison_contract=paired_contract())

    assert result["eligible"] is False
    assert "scope_session_id_mismatch" in result["reasons"]
    assert any("packet_receipt_binding_session_id_mismatch" in reason for reason in result["reasons"])


def test_episode_route_requires_exact_binding_and_rejects_foreign_or_bad_ranges(tmp_path: Path) -> None:
    binding = strict_episode_binding()
    receipt = make_receipt()
    packet = telemetry.project_identity_bound_episode_packet(
        session_id="s1",
        session_ref="session:s1",
        source={"raw_sha256": "a" * 64, "raw_bytes": 100, "raw_line_count": 10},
        prefix_identity="sha256:" + "b" * 64,
        publish_id="sha256:" + "c" * 64,
        projection_status="current",
        review_status="reviewed",
        profile={"schema_version": "stage_profile_v1", "stage_spans": {}},
        owner_receipt=receipt,
        episode_binding=binding,
        component_admission=component_admission(binding, tmp_path),
        receipt_carrying_event_witness=carrying_event_witness(receipt, tmp_path=tmp_path),
    )
    assert packet["artifact_type"] == telemetry.EPISODE_PACKET_ARTIFACT
    telemetry.verify_packet_integrity(packet)
    public_packet = json.loads(json.dumps(packet, ensure_ascii=False))
    with pytest.raises(telemetry.TelemetryError, match="episode_component_admission_required"):
        telemetry.verify_packet_integrity(public_packet)

    with pytest.raises(telemetry.TelemetryAdmissionError, match="episode_component_admission_required"):
        telemetry.validate_episode_binding(binding)

    foreign = copy.deepcopy(packet)
    foreign["episode_binding"]["session_ref"] = "session:foreign"
    foreign["packet_id"] = telemetry.canonical_sha256(
        {key: value for key, value in foreign.items() if key != "packet_id"}
    )
    result = telemetry.compare_identity_packets(packet, foreign, comparison_contract=paired_contract())
    assert result["eligible"] is False
    assert any(
        "episode_binding_" in reason and ("foreign" in reason or "mismatch" in reason)
        for reason in result["reasons"]
    )

    with pytest.raises(telemetry.TelemetryError, match="event_range_out_of_source"):
        telemetry.validate_episode_binding(
            strict_episode_binding(to_line=11, raw_line_count=10)
        )
    with pytest.raises(telemetry.TelemetryError, match="event_range_invalid"):
        telemetry.validate_episode_binding(strict_episode_binding(from_line=8, to_line=3))


def test_receipt_provenance_rejects_self_redigested_arbitrary_receipt_id() -> None:
    packet = project(make_receipt())
    forged = copy.deepcopy(dict(packet))
    arbitrary_id = "sha256:" + "0" * 64
    federation = forged["methods"]["owner_receipt_federation"]
    federation["receipt_id"] = arbitrary_id
    federation["receipt_provenance"]["receipt_id"] = arbitrary_id
    federation["receipt_provenance"]["receipt_payload_sha256"] = arbitrary_id
    provenance = federation["receipt_provenance"]
    provenance["chain_sha256"] = telemetry.canonical_sha256(
        {key: value for key, value in provenance.items() if key != "chain_sha256"}
    )
    forged["integrity"]["receipt_id"] = arbitrary_id
    forged["packet_id"] = telemetry.canonical_sha256(
        {key: value for key, value in forged.items() if key != "packet_id"}
    )
    with pytest.raises(telemetry.TelemetryError, match="receipt_provenance_witness_required"):
        telemetry.verify_packet_integrity(forged)

    in_memory = copy.deepcopy(packet)
    in_memory_federation = in_memory["methods"]["owner_receipt_federation"]
    in_memory_federation["receipt_id"] = arbitrary_id
    in_memory_federation["receipt_provenance"]["receipt_id"] = arbitrary_id
    in_memory_federation["receipt_provenance"]["receipt_payload_sha256"] = arbitrary_id
    in_memory_provenance = in_memory_federation["receipt_provenance"]
    in_memory_provenance["chain_sha256"] = telemetry.canonical_sha256(
        {key: value for key, value in in_memory_provenance.items() if key != "chain_sha256"}
    )
    in_memory["integrity"]["receipt_id"] = arbitrary_id
    in_memory["packet_id"] = telemetry.canonical_sha256(
        {key: value for key, value in in_memory.items() if key != "packet_id"}
    )
    with pytest.raises(telemetry.TelemetryError, match="receipt_provenance_witness_mismatch"):
        telemetry.verify_packet_integrity(in_memory)


def test_strict_episode_route_cannot_be_downgraded_after_redigest(tmp_path: Path) -> None:
    binding = strict_episode_binding()
    receipt = make_receipt()
    packet = telemetry.project_identity_bound_episode_packet(
        session_id="s1",
        session_ref="session:s1",
        source={"raw_sha256": "a" * 64, "raw_bytes": 100, "raw_line_count": 10},
        prefix_identity="sha256:" + "b" * 64,
        publish_id="sha256:" + "c" * 64,
        projection_status="current",
        review_status="reviewed",
        owner_receipt=receipt,
        episode_binding=binding,
        component_admission=component_admission(binding, tmp_path),
        receipt_carrying_event_witness=carrying_event_witness(receipt, tmp_path=tmp_path),
    )
    downgraded = copy.deepcopy(dict(packet))
    downgraded["schema_version"] = telemetry.SCHEMA_VERSION
    downgraded["artifact_type"] = telemetry.PACKET_ARTIFACT
    downgraded.pop("episode_binding")
    downgraded["route_admission"] = telemetry._build_route_admission("generic")
    downgraded["packet_id"] = telemetry.canonical_sha256(
        {key: value for key, value in downgraded.items() if key != "packet_id"}
    )
    with pytest.raises(telemetry.TelemetryError, match="route_floor_mismatch"):
        telemetry.verify_packet_integrity(downgraded)

    import profile_session_stages as module

    cohort = module.identity_episode_cohort([downgraded])
    assert cohort["eligible_count"] == 0
    assert cohort["excluded_count"] == 1
    assert cohort["admission_cardinality"]["status"] == "rejected"


def test_carrying_event_and_multilingual_public_ref_contract(tmp_path: Path) -> None:
    receipt = make_receipt()
    mismatched_event = attach_event_source_evidence(
        {
            "line": 7,
            "event_id": "event-7",
            "correlation_id": "different-call",
            "facets": {"identity_bound_telemetry_receipt": receipt},
        },
        source_ref="owner:test-event:event-7-mismatch",
        source_path=event_artifact(tmp_path, {
            "line": 7,
            "event_id": "event-7",
            "correlation_id": "different-call",
            "facets": {"identity_bound_telemetry_receipt": receipt},
        }, "mismatch"),
    )
    rejected = telemetry.capture_receipt_facets(
        [mismatched_event]
    )
    assert rejected[0]["status"] == "rejected"
    assert rejected[0]["rejection"] == "carrying_event_correlation_mismatch"

    admitted = telemetry.capture_receipt_facets(
        [
            attach_event_source_evidence(
                {
                    "line": 7,
                    "event_id": "event-7",
                    "correlation_id": "correlation-chain",
                    "facets": {"identity_bound_telemetry_receipt": receipt},
                },
                source_ref="owner:test-event:event-7",
                source_path=event_artifact(tmp_path, {
                    "line": 7,
                    "event_id": "event-7",
                    "correlation_id": "correlation-chain",
                    "facets": {"identity_bound_telemetry_receipt": receipt},
                }, "admitted"),
            )
        ]
    )
    assert admitted[0]["status"] == "admitted"
    assert admitted[0]["carrying_event"]["line"] == 7
    assert admitted[0]["carrying_event"]["event_id"] == "event-7"
    assert admitted[0]["carrying_event"]["correlation_id"] == "correlation-chain"
    assert admitted[0]["carrying_event"]["receipt_id"] == receipt["receipt_id"]
    assert admitted[0]["carrying_event"]["facet_sha256"].startswith("sha256:")
    assert isinstance(admitted[0]["witness"], telemetry.CarryingEventWitness)

    witness = alias_owner_root_witness(tmp_path / "alias-public-ref")
    public_ref = telemetry.public_session_ref(
        "Сессия/é/会议",
        owner_root_witness=witness,
    )
    assert "Сессия" not in public_ref
    assert "会议" not in public_ref
    assert "%" not in public_ref
    assert public_ref.startswith("session:alias-")
    assert len(public_ref.rsplit("-", 1)[-1]) == 64
    dictionary_digest = "session:alias-" + hashlib.sha256("Сессия/é/会议".encode("utf-8")).hexdigest()
    assert public_ref != dictionary_digest
    with pytest.raises(telemetry.TelemetryError, match="explicit_key_not_owner_controlled"):
        telemetry.public_session_ref(
            "0",
            alias_key="owner-held-test-key-1234567890abcdef",
            owner_root_witness=witness,
        )


def test_strict_episode_route_rejects_caller_metadata_and_manifest_forgery(tmp_path: Path) -> None:
    binding = strict_episode_binding()
    receipt = make_receipt()
    with pytest.raises(telemetry.TelemetryError, match="component_admission_required"):
        telemetry.project_identity_bound_episode_packet(
            session_id="s1",
            session_ref="session:s1",
            source={"raw_sha256": "a" * 64, "raw_bytes": 100, "raw_line_count": 10},
            prefix_identity="sha256:" + "b" * 64,
            publish_id="sha256:" + "c" * 64,
            projection_status="current",
            review_status="reviewed",
            owner_receipt=receipt,
            episode_binding=binding,
            receipt_carrying_event={"line": 3, "event_id": "event-3", "correlation_id": "correlation-chain"},
        )

    forged = copy.deepcopy(binding)
    forged["component_identity"]["artifact_sha256"] = "0" * 64
    with pytest.raises(telemetry.TelemetryError, match="portable_witness_binding_mismatch"):
        telemetry.project_identity_bound_episode_packet(
            session_id="s1",
            session_ref="session:s1",
            source={"raw_sha256": "a" * 64, "raw_bytes": 100, "raw_line_count": 10},
            prefix_identity="sha256:" + "b" * 64,
            publish_id="sha256:" + "c" * 64,
            projection_status="current",
            review_status="reviewed",
            owner_receipt=receipt,
            episode_binding=forged,
            component_admission=component_admission(binding, tmp_path),
            receipt_carrying_event_witness=carrying_event_witness(receipt, tmp_path=tmp_path),
        )


def test_strict_episode_route_joins_capture_event_to_range_and_source(tmp_path: Path) -> None:
    binding = strict_episode_binding()
    receipt = make_receipt()
    with pytest.raises(telemetry.TelemetryError, match="outside_episode_range"):
        telemetry.project_identity_bound_episode_packet(
            session_id="s1",
            session_ref="session:s1",
            source={"raw_sha256": "a" * 64, "raw_bytes": 100, "raw_line_count": 10},
            prefix_identity="sha256:" + "b" * 64,
            publish_id="sha256:" + "c" * 64,
            projection_status="current",
            review_status="reviewed",
            owner_receipt=receipt,
            episode_binding=binding,
            component_admission=component_admission(binding, tmp_path),
            receipt_carrying_event_witness=carrying_event_witness(
                receipt, tmp_path=tmp_path, line=999, event_id="event-999"
            ),
        )


def test_strict_episode_component_admission_rejects_process_local_and_substituted_context(
    tmp_path: Path,
) -> None:
    binding = strict_episode_binding()
    with pytest.raises(telemetry.TelemetryAdmissionError, match="owner_artifacts_required"):
        telemetry._issue_episode_component_admission(
            session_id="s1",
            session_ref="session:s1",
            episode_id="task-0001",
            component_ref=str(binding["manifest_admission"]["component_ref"]),
            manifest_sha256=str(binding["manifest_admission"]["manifest_sha256"]),
            source=binding["source"],
            component_identity=binding["component_identity"],
            artifact_sha256=str(binding["component_identity"]["artifact_sha256"]),
            payload_sha256=str(binding["component_identity"]["payload_sha256"]),
        )

    admission = component_admission(binding, tmp_path)
    session_dir = tmp_path / "owner-root" / "sessions" / "owner-session"
    component_path = session_dir / str(binding["manifest_admission"]["component_ref"])
    manifest_path = session_dir / "session-index-shards" / "manifest.json"
    session_manifest_path = session_dir / "session.manifest.json"
    owner_membership = telemetry._owner_episode_component_membership(
        session_dir=session_dir,
        component_ref=str(binding["manifest_admission"]["component_ref"]),
        component_path=component_path,
        owner_root_witness=owner_root_witness(session_dir.parents[1]),
    )
    with pytest.raises(
        telemetry.TelemetryAdmissionError,
        match="episode_component_owner_membership_required",
    ):
        telemetry._issue_episode_component_admission(
            session_id="s1",
            session_ref="session:s1",
            episode_id="task-0001",
            component_ref=str(binding["manifest_admission"]["component_ref"]),
            manifest_sha256=str(binding["manifest_admission"]["manifest_sha256"]),
            source=binding["source"],
            component_identity=binding["component_identity"],
            artifact_sha256=str(binding["component_identity"]["artifact_sha256"]),
            payload_sha256=str(binding["component_identity"]["payload_sha256"]),
            manifest_path=manifest_path,
            component_path=component_path,
            session_manifest_path=session_manifest_path,
            expected_projection={"owner": "test-current-projection", "generation": "f" * 64},
            expected_task_episode_generation=str(binding["component_identity"]["task_episode_generation_id"]),
            expected_generation_context={
                "task_episode_generation": str(binding["component_identity"]["task_episode_generation_id"]),
                "segment_generation": "b" * 64,
                "session_generation": "c" * 64,
            },
        )
    forged_source = copy.deepcopy(binding["source"])
    forged_source["raw_sha256"] = "b" * 64
    with pytest.raises(telemetry.TelemetryAdmissionError, match="session_source_mismatch:raw_sha256"):
        telemetry._issue_episode_component_admission(
            session_id="s1",
            session_ref="session:s1",
            episode_id="task-0001",
            component_ref=str(binding["manifest_admission"]["component_ref"]),
            manifest_sha256=str(binding["manifest_admission"]["manifest_sha256"]),
            source=forged_source,
            component_identity=binding["component_identity"],
            artifact_sha256=str(binding["component_identity"]["artifact_sha256"]),
            payload_sha256=str(binding["component_identity"]["payload_sha256"]),
            manifest_path=manifest_path,
            component_path=component_path,
            session_manifest_path=session_manifest_path,
            expected_projection={"owner": "test-current-projection", "generation": "f" * 64},
            expected_task_episode_generation=str(binding["component_identity"]["task_episode_generation_id"]),
            expected_generation_context={
                "task_episode_generation": str(binding["component_identity"]["task_episode_generation_id"]),
                "segment_generation": "b" * 64,
                "session_generation": "c" * 64,
            },
            owner_membership=owner_membership,
        )
    assert admission.verify_current() is True


def test_owner_source_evidence_rejects_external_same_byte_segment_direct_loader(
    tmp_path: Path,
) -> None:
    event = {
        "line": 1,
        "event_id": "event-direct-external",
        "correlation_id": "correlation-chain",
        "facets": {},
    }
    canonical_path = event_artifact(tmp_path, event, "canonical")
    external_path = (
        tmp_path
        / "owner-root-sibling"
        / "sessions"
        / "fixture-session"
        / "segments"
        / "external-same-byte.segment.json"
    )
    external_path.parent.mkdir(parents=True, exist_ok=True)
    external_path.write_bytes(canonical_path.read_bytes())
    with pytest.raises(
        telemetry.TelemetryAdmissionError,
        match="owner_event_source_membership_required",
    ):
        telemetry._attach_owner_source_evidence(
            event,
            source_ref="owner:segment:external-same-byte",
            source_path=external_path,
        )


def test_owner_root_witness_rejects_foreign_self_consistent_same_byte_root(
    tmp_path: Path,
) -> None:
    event = {
        "line": 1,
        "event_id": "event-foreign-root",
        "correlation_id": "correlation-chain",
        "facets": {},
    }
    canonical_path = event_artifact(tmp_path, event, "canonical")
    foreign_path = event_artifact(tmp_path / "foreign", event, "canonical")
    assert foreign_path.read_bytes() == canonical_path.read_bytes()
    canonical_witness = owner_root_witness(canonical_path.parents[3])
    with pytest.raises(
        telemetry.TelemetryAdmissionError,
        match="owner_event_source_membership_required",
    ):
        telemetry._attach_owner_source_evidence(
            event,
            source_ref="owner:segment:foreign-root",
            source_path=foreign_path,
            owner_root_witness=canonical_witness,
        )


def test_owner_membership_witness_is_nonportable_and_mapping_is_not_admitted(
    tmp_path: Path,
) -> None:
    binding = strict_episode_binding()
    admission = component_admission(binding, tmp_path)
    membership = admission._owner_source_evidence._membership
    assert isinstance(membership, telemetry.OwnerMembershipWitness)
    with pytest.raises(TypeError):
        json.dumps(membership)
    with pytest.raises(telemetry.TelemetryAdmissionError, match="witness_required"):
        telemetry._issue_episode_component_admission(
            session_id="s1",
            session_ref="session:s1",
            episode_id="task-0001",
            component_ref=str(binding["manifest_admission"]["component_ref"]),
            manifest_sha256=str(binding["manifest_admission"]["manifest_sha256"]),
            source=binding["source"],
            component_identity=binding["component_identity"],
            artifact_sha256=str(binding["component_identity"]["artifact_sha256"]),
            payload_sha256=str(binding["component_identity"]["payload_sha256"]),
            manifest_path=tmp_path / "owner-root/sessions/owner-session/session-index-shards/manifest.json",
            component_path=tmp_path / "owner-root/sessions/owner-session/session-index-shards/task-episodes/task-0001.json",
            session_manifest_path=tmp_path / "owner-root/sessions/owner-session/session.manifest.json",
            expected_projection={"owner": "test-current-projection", "generation": "f" * 64},
            expected_task_episode_generation=str(binding["component_identity"]["task_episode_generation_id"]),
            expected_generation_context={
                "task_episode_generation": str(binding["component_identity"]["task_episode_generation_id"]),
                "segment_generation": "b" * 64,
                "session_generation": "c" * 64,
            },
            owner_membership=copy.deepcopy(membership._record),
        )


def test_owner_membership_witness_rejects_concurrent_component_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = strict_episode_binding()
    admission = component_admission(binding, tmp_path)
    membership = admission._owner_source_evidence._membership
    assert isinstance(membership, telemetry.OwnerMembershipWitness)
    component_path = tmp_path / "owner-root" / "sessions" / "owner-session" / str(
        binding["manifest_admission"]["component_ref"]
    )
    original_reader = telemetry._read_regular_file
    replaced = threading.Event()
    armed = True

    def racing_reader(path: Path, **kwargs: object) -> tuple[bytes, dict[str, object]]:
        nonlocal armed
        data, identity = original_reader(path, **kwargs)
        if armed and Path(path) == component_path:
            armed = False
            replacement = component_path.with_name("race-replacement.json")

            def replace_path() -> None:
                replacement.write_bytes(data)
                os.replace(replacement, component_path)
                replaced.set()

            worker = threading.Thread(target=replace_path)
            worker.start()
            worker.join()
        return data, identity

    monkeypatch.setattr(telemetry, "_read_regular_file", racing_reader)
    assert membership.verify_current() is False
    assert replaced.is_set()


def test_owner_alias_source_contract_is_authenticated_current_and_private(
    tmp_path: Path,
) -> None:
    root = tmp_path / "alias-owner"
    witness = alias_owner_root_witness(root)
    public_contract = witness.public_alias_contract()
    assert public_contract is not None
    assert set(public_contract) == {
        "schema_version",
        "issuer",
        "source_ref",
        "trust_anchor_ref",
        "root_sha256",
        "epoch_sha256",
        "contract_sha256",
    }
    assert "session-alias.key" not in json.dumps(public_contract)
    assert not hasattr(witness, "current_alias_key")
    assert witness._alias_source is not None
    assert not hasattr(witness._alias_source, "current_key")
    before = telemetry.public_session_ref("fixture", owner_root_witness=witness)
    contract_path = root / telemetry.OWNER_ALIAS_SOURCE_CONTRACT_RELATIVE_PATH
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["source_ref"] = "owner:replaced-alias-source"
    write_test_json(contract_path, contract)
    assert witness.verify_current() is False
    with pytest.raises(telemetry.TelemetryAdmissionError, match="not_current"):
        telemetry.public_session_ref("fixture", owner_root_witness=witness)
    assert before.startswith("session:alias-")


def test_owner_alias_source_rejects_callback_construction() -> None:
    with pytest.raises(TypeError):
        telemetry.OwnerAliasSource(
            source_ref="owner:caller-callback",
            key_sha256="a" * 64,
            contract_sha256="sha256:" + "b" * 64,
            key_reader=lambda: b"synthetic",
            contract_current=lambda: True,
            token=telemetry._OWNER_ALIAS_SOURCE_TOKEN,
        )


def test_owner_root_and_alias_witnesses_reject_copy_and_deepcopy(
    tmp_path: Path,
) -> None:
    witness = alias_owner_root_witness(tmp_path / "copy-owner")
    assert witness._alias_source is not None
    for value in (witness, witness._alias_source, witness.currentness_receipt()):
        with pytest.raises(TypeError, match="not_copyable"):
            copy.copy(value)
        with pytest.raises(TypeError, match="not_copyable"):
            copy.deepcopy(value)


def test_owner_root_witness_rejects_cross_root_alias_source_transfer(
    tmp_path: Path,
) -> None:
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    witness_a = alias_owner_root_witness(root_a)
    alias_owner_root_witness(root_b)
    assert witness_a._alias_source is not None
    with pytest.raises(
        telemetry.TelemetryAdmissionError,
        match="owner_root_alias_source_root_mismatch",
    ):
        telemetry._issue_owner_root_witness(
            root_b,
            alias_source=witness_a._alias_source,
        )


def test_owner_root_witness_rejects_wrong_root_session_reuse(
    tmp_path: Path,
) -> None:
    root = tmp_path / "canonical-root"
    witness = alias_owner_root_witness(root)
    wrong_session = tmp_path / "foreign-root" / "sessions" / "session"
    wrong_session.mkdir(parents=True, exist_ok=True)
    with pytest.raises(
        telemetry.TelemetryAdmissionError,
        match="owner_session_root_identity_mismatch",
    ):
        witness.assert_session_dir(wrong_session)


def test_owner_root_witness_rejects_same_byte_foreign_root_contract(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "canonical-root"
    alias_owner_root_witness(canonical)
    foreign = tmp_path / "foreign-root"
    foreign_owner = foreign / ".owner"
    foreign_owner.mkdir(parents=True, exist_ok=True)
    foreign_owner.joinpath("session-alias.key").write_bytes(
        canonical.joinpath(".owner/session-alias.key").read_bytes()
    )
    foreign_owner.joinpath("session-alias-source.json").write_bytes(
        canonical.joinpath(".owner/session-alias-source.json").read_bytes()
    )
    with pytest.raises(
        telemetry.TelemetryAdmissionError,
        match="session_alias_owner_admission_invalid",
    ):
        telemetry._owner_root_witness_for_root(foreign)


def test_owner_root_witness_rejects_stale_admission_epoch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "epoch-owner"
    witness = alias_owner_root_witness(root)
    contract_path = root / telemetry.OWNER_ALIAS_SOURCE_CONTRACT_RELATIVE_PATH
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["epoch_sha256"] = "sha256:" + "0" * 64
    write_test_json(contract_path, contract)
    assert witness.verify_current() is False
    with pytest.raises(telemetry.TelemetryAdmissionError, match="not_current"):
        telemetry.public_session_ref("fixture", owner_root_witness=witness)


def test_owner_admission_transaction_reuses_snapshot_and_keeps_final_reread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admission = component_admission(strict_episode_binding(), tmp_path)
    counts = {"root_snapshots": 0, "file_reads": 0}
    original_root = telemetry._owner_directory_identity_snapshot
    original_read = telemetry._read_regular_file

    def count_root(*args: object, **kwargs: object) -> object:
        counts["root_snapshots"] += 1
        return original_root(*args, **kwargs)

    def count_read(*args: object, **kwargs: object) -> object:
        counts["file_reads"] += 1
        return original_read(*args, **kwargs)

    monkeypatch.setattr(telemetry, "_owner_directory_identity_snapshot", count_root)
    monkeypatch.setattr(telemetry, "_read_regular_file", count_read)
    assert admission.verify_current() is True
    assert counts == {"root_snapshots": 4, "file_reads": 27}


def test_episode_admission_and_source_evidence_reject_copy_and_deepcopy(
    tmp_path: Path,
) -> None:
    admission = component_admission(strict_episode_binding(), tmp_path)
    evidence = admission._owner_source_evidence
    for value in (admission, evidence):
        with pytest.raises(TypeError, match="not_copyable"):
            copy.copy(value)
        with pytest.raises(TypeError, match="not_copyable"):
            copy.deepcopy(value)


def test_owner_alias_key_replacement_invalidates_witness(tmp_path: Path) -> None:
    root = tmp_path / "alias-key-owner"
    witness = alias_owner_root_witness(root)
    key_path = root / telemetry.OWNER_ALIAS_SOURCE_KEY_RELATIVE_PATH
    key_path.write_bytes(hashlib.sha256(b"replaced-owner-alias-fixture").digest())
    assert witness.verify_current() is False
    with pytest.raises(telemetry.TelemetryAdmissionError, match="not_current"):
        telemetry.public_session_ref("fixture", owner_root_witness=witness)


def test_owner_root_witness_requires_owner_alias_contract(tmp_path: Path) -> None:
    root = tmp_path / "missing-owner-contract"
    root.mkdir()
    with pytest.raises(telemetry.TelemetryAdmissionError, match="owner_contract"):
        telemetry._owner_root_witness_for_root(root)


@pytest.mark.parametrize("mutation", ["symlink", "hardlink", "nonregular", "atomic_replace"])
def test_episode_component_admission_rejects_path_identity_substitution(
    tmp_path: Path,
    mutation: str,
) -> None:
    case_dir = tmp_path / mutation
    case_dir.mkdir()
    binding = strict_episode_binding()
    admission = component_admission(binding, case_dir)
    session_dir = case_dir / "owner-root" / "sessions" / "owner-session"
    component_path = session_dir / str(binding["manifest_admission"]["component_ref"])
    original = component_path.read_bytes()
    if mutation == "symlink":
        target = case_dir / "same-bytes-target.json"
        target.write_bytes(original)
        component_path.unlink()
        component_path.symlink_to(target)
    elif mutation == "hardlink":
        target = case_dir / "same-bytes-target.json"
        target.write_bytes(original)
        component_path.unlink()
        os.link(target, component_path)
    elif mutation == "nonregular":
        component_path.unlink()
        component_path.mkdir()
    else:
        replacement = case_dir / "atomic-replacement.json"
        replacement.write_bytes(original)
        os.replace(replacement, component_path)

    assert admission.verify_current() is False


def test_episode_component_admission_rejects_parent_symlink_and_context_drift(tmp_path: Path) -> None:
    binding = strict_episode_binding()
    admission = component_admission(binding, tmp_path / "parent-symlink")
    owner_session = tmp_path / "parent-symlink" / "owner-root" / "sessions" / "owner-session"
    real_owner_session = (
        tmp_path
        / "parent-symlink"
        / "owner-root"
        / "sessions"
        / "owner-session-real"
    )
    owner_session.rename(real_owner_session)
    owner_session.symlink_to(real_owner_session, target_is_directory=True)
    assert admission.verify_current() is False

    binding = strict_episode_binding()
    context_dir = tmp_path / "context-drift"
    admission = component_admission(binding, context_dir)
    session_manifest_path = (
        context_dir
        / "owner-root"
        / "sessions"
        / "owner-session"
        / "session.manifest.json"
    )
    session_manifest = json.loads(session_manifest_path.read_text(encoding="utf-8"))
    session_manifest["index_schema"]["projection_publish"]["owner"] = "drifted-owner"
    write_test_json(session_manifest_path, session_manifest)
    assert admission.verify_current() is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("session_index_generation_id", "0" * 64),
        ("segment_index_generation_id", "0" * 64),
    ],
)
def test_episode_component_admission_rejects_session_generation_context_drift(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    case_dir = tmp_path / field
    binding = strict_episode_binding()
    admission = component_admission(binding, case_dir)
    session_manifest_path = (
        case_dir
        / "owner-root"
        / "sessions"
        / "owner-session"
        / "session.manifest.json"
    )
    session_manifest = json.loads(session_manifest_path.read_text(encoding="utf-8"))
    session_manifest["index_schema"][field] = value
    write_test_json(session_manifest_path, session_manifest)
    assert admission.verify_current() is False


def test_episode_component_admission_pins_nested_inputs_and_not_their_later_mutation(tmp_path: Path) -> None:
    binding = strict_episode_binding()
    admission = component_admission(binding, tmp_path)
    binding["source"]["raw_sha256"] = "0" * 64
    binding["component_identity"]["event_range"]["to_line"] = 1
    binding["manifest_admission"]["component_ref"] = "session-index-shards/task-episodes/forged.json"
    assert admission.verify_current() is True


def test_episode_component_admission_is_not_restored_by_cross_process_json_roundtrip(tmp_path: Path) -> None:
    binding = strict_episode_binding()
    admission = component_admission(binding, tmp_path)
    public_binding = json.loads(json.dumps(admission.public_binding(), ensure_ascii=False))
    with pytest.raises(telemetry.TelemetryAdmissionError, match="episode_component_admission_required"):
        telemetry.validate_episode_binding(public_binding)


def test_comparison_contract_allows_designed_cohort_differences_without_effect() -> None:
    left = project(
        make_receipt(
            session_id="s1",
            session_ref="session:s1",
            identity_overrides={"route_or_treatment_identity": "control"},
        )
    )
    right = project(
        make_receipt(
            session_id="s2",
            session_ref="session:s2",
            raw_sha256="b" * 64,
            identity_overrides={"route_or_treatment_identity": "treatment"},
        ),
        session_id="s2",
        session_ref="session:s2",
        source={"raw_sha256": "b" * 64, "raw_bytes": 100, "raw_line_count": 10},
    )
    contract = telemetry.build_comparison_contract(
        design="treatment_control",
        required_equal_identity_fields=[
            name for name in telemetry.IDENTITY_FIELDS if name != "route_or_treatment_identity"
        ],
        allowed_identity_differences=["route_or_treatment_identity"],
        required_equal_scope_fields=["projection"],
        allowed_scope_differences=["session_id", "session_ref", "source", "episode_binding"],
    )
    result = telemetry.compare_identity_packets(left, right, comparison_contract=contract)
    assert result["eligible"] is True
    assert result["comparison_contract"]["design"] == "treatment_control"
    assert result["effect"] is None
    assert result["verdict"] is None


def test_forged_eligibility_is_recomputed_and_excluded() -> None:
    packet = project(make_receipt(incomplete_step="repair"))
    packet["eligibility"]["status"] = "eligible_identity_packet"
    packet["eligibility"]["reasons"] = []
    packet["packet_id"] = telemetry.canonical_sha256(
        {key: value for key, value in packet.items() if key != "packet_id"}
    )
    with pytest.raises(telemetry.TelemetryError, match="eligibility_not_recomputed"):
        telemetry.verify_packet_integrity(packet)

    # A forged digest must not turn into an eligible cohort observation.
    import profile_session_stages as module

    cohort = module.identity_episode_cohort([packet])
    assert cohort["eligible_count"] == 0
    assert cohort["excluded_count"] == 1


def test_authority_ceiling_cannot_be_forged_after_packet_digest_recompute() -> None:
    packet = project(make_receipt())
    packet["authority"]["proof"] = True
    packet["packet_id"] = telemetry.canonical_sha256(
        {key: value for key, value in packet.items() if key != "packet_id"}
    )

    with pytest.raises(telemetry.TelemetryError, match="authority_proof_must_remain_false"):
        telemetry.verify_packet_integrity(packet)


def test_owner_validator_marker_is_required_for_portable_episode_schema(tmp_path: Path) -> None:
    binding = strict_episode_binding()
    schema = json.loads(
        (REPO_ROOT / "schemas" / "identity-bound-session-telemetry.schema.json").read_text(encoding="utf-8")
    )
    admission = component_admission(binding, tmp_path)
    packet = telemetry.project_identity_bound_episode_packet(
        session_id="s1",
        session_ref="session:s1",
        source={"raw_sha256": "a" * 64, "raw_bytes": 100, "raw_line_count": 10},
        prefix_identity="sha256:" + "b" * 64,
        publish_id="sha256:" + "c" * 64,
        projection_status="current",
        review_status="reviewed",
        owner_receipt=None,
        episode_binding=binding,
        component_admission=admission,
    )
    assert list(Draft202012Validator(schema).iter_errors(packet)) == []
    missing = copy.deepcopy(dict(packet))
    missing["episode_binding"].pop("owner_validation")
    assert list(Draft202012Validator(schema).iter_errors(missing))

    reversed_binding = strict_episode_binding(from_line=8, to_line=3)
    binding_schema = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": "#/$defs/episodeBinding",
    }
    assert list(Draft202012Validator(binding_schema).iter_errors(reversed_binding)) == []
    with pytest.raises(telemetry.TelemetryError, match="event_range_invalid"):
        telemetry.validate_episode_binding(reversed_binding)


def test_public_alias_rejects_weak_configured_keys(tmp_path: Path) -> None:
    witness = alias_owner_root_witness(tmp_path / "alias-weak-config")
    with pytest.raises(telemetry.TelemetryError, match="explicit_key_not_owner_controlled"):
        telemetry.public_session_ref("fixture", alias_key="1" * 16, owner_root_witness=witness)


def test_public_alias_owner_constructor_is_not_importable_or_caller_selectable(tmp_path: Path) -> None:
    assert not hasattr(telemetry, "_OwnerAliasKey")
    assert not hasattr(telemetry, "_OWNER_ALIAS_KEY_TOKEN")
    witness = alias_owner_root_witness(tmp_path / "alias-constructor")
    with pytest.raises(telemetry.TelemetryError, match="explicit_key_not_owner_controlled"):
        telemetry.public_session_ref("fixture", alias_key=object(), owner_root_witness=witness)


def test_public_alias_ignores_legacy_environment_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "alias-source"
    witness = alias_owner_root_witness(root)
    expected = telemetry.public_session_ref("fixture", owner_root_witness=witness)
    monkeypatch.setenv("AOA_SESSION_MEMORY_PUBLIC_ALIAS_KEY", "1" * 32)
    assert telemetry.public_session_ref("fixture", owner_root_witness=witness) == expected

    monkeypatch.setenv("AOA_SESSION_MEMORY_PUBLIC_ALIAS_KEY", "0123456789abcdef" * 4)
    left = telemetry.public_session_ref("left", owner_root_witness=witness)
    right = telemetry.public_session_ref("right", owner_root_witness=witness)
    assert left != right
    assert "0123456789abcdef" not in left

def test_eligibility_keeps_missing_unknown_unobservable_excluded_and_eligible_distinct() -> None:
    missing_packet = project(None)
    unknown_packet = project(make_receipt(incomplete_step="repair"))
    excluded_packet = project(make_receipt(raw_sha256="b" * 64))
    unobservable_receipt = make_receipt(unobservable_timing="repair_latency_seconds")
    unobservable_packet = project(unobservable_receipt)
    eligible_packet = project(make_receipt())

    assert missing_packet["eligibility"]["status"] == "missing"
    assert unknown_packet["eligibility"]["status"] == "unknown"
    assert excluded_packet["eligibility"]["status"] == "excluded"
    assert unobservable_packet["eligibility"]["status"] == "unobservable"
    assert eligible_packet["eligibility"]["status"] == "eligible_identity_packet"
    for packet in (missing_packet, unknown_packet, excluded_packet, unobservable_packet, eligible_packet):
        assert packet["eligibility"]["effect_verdict"] is None
        assert packet["eligibility"]["proof"] is False
        assert packet["eligibility"]["acceptance"] is False
